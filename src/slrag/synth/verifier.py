"""Claim verifier — S-6 constrained citation vocabulary + S-5 two-pass streaming.

Roadmap 4.7 (S-6 layer 3, the unconditional backstop): every ``[... §...]``
marker a draft carries is checked against the closed allowlist — the labels of
exactly the chunks in this turn's context — and anything outside it is stripped
and counted. Nothing the verifier emits can cite a fabricated label; CI asserts
``fabricated_id_count == 0`` via ``ClaimVerifier.output_fabricated_count``.

Roadmap 4.8 (S-5): each generated sentence is emitted PROVISIONAL at once and
verified in a worker thread while the next one is generated — citation validity,
entailment (cited chunk |= sentence), negation polarity against the entailing
clause, and a numeral/entity copy check. A sentence
that cited a fabricated ID is RETRACTED (demoted to uncertainty, A §4.4); any other
failing sentence is re-attributed to an in-context chunk that supports it, else
RETRACTED. No regeneration on retract (HC-5), no LLM calls, no persistence
(HC-4); thresholds come from ``config/synth.yaml`` ``verifier:`` (HC-2).
"""

from __future__ import annotations

import asyncio
import math
import re
import threading
import time
from collections import deque
from typing import Any, AsyncIterable, AsyncIterator, Callable, Iterable, Protocol, Sequence

from slrag.core.citations import find_markers, label_for_chunk, normalize_label
from slrag.core.schemas import RetrievedChunk
from slrag.synth.config import load_synth_config, resolve_path
from slrag.synth.lexicon import WordNet, negation_regex
from slrag.synth.text import (
    content_tokens,
    extract_numerals,
    extract_proper_nouns,
    overlap,
    split_clauses,
    split_sentences,
    stopwords_from,
)
from slrag.synth.types import DraftClaim, StreamEvent, VerificationResult

_WS_RE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([.,;:!?)])")
_END = object()          # immutable end-of-stream sentinel for the draft iterator
_POSSESSIVE_RE = re.compile(r"['’]s?$")
_WORD_RE = re.compile(r"[a-z]+(?:-[a-z]+)*")


def _config(config: dict[str, Any] | None) -> dict[str, Any]:
    return config if config is not None else load_synth_config()


def _tidy(text: str) -> str:
    return _SPACE_BEFORE_PUNCT_RE.sub(r"\1", _WS_RE.sub(" ", text)).strip()


# ---------------------------------------------------------------------------
# S-6: closed citation allowlist + post-hoc stripper
# ---------------------------------------------------------------------------
class CitationAllowlist:
    """The only labels a sentence may cite: those of the chunks actually in context (S-6 layer 1)."""

    def __init__(self, chunks: Iterable[RetrievedChunk] = ()) -> None:
        self._chunks: list[RetrievedChunk] = []
        self._by_label: dict[str, list[RetrievedChunk]] = {}
        seen: set[str] = set()
        for chunk in chunks:
            if chunk.chunk_id in seen:
                continue
            seen.add(chunk.chunk_id)
            self._chunks.append(chunk)
            self._by_label.setdefault(label_for_chunk(chunk), []).append(chunk)
        self._labels = frozenset(self._by_label)

    @classmethod
    def from_chunks(cls, chunks: Iterable[RetrievedChunk]) -> CitationAllowlist:
        return cls(chunks)

    @property
    def labels(self) -> frozenset[str]:
        return self._labels

    @property
    def chunks(self) -> list[RetrievedChunk]:
        return list(self._chunks)

    def chunks_for(self, label: str) -> list[RetrievedChunk]:
        canonical = normalize_label(label)
        return list(self._by_label.get(canonical, ())) if canonical else []

    def __contains__(self, label: object) -> bool:
        return isinstance(label, str) and normalize_label(label) in self._labels

    def enum(self) -> list[str]:
        """Sorted labels for a JSON-schema ``enum`` on citation fields (S-6 layer 2)."""
        return sorted(self._labels)

    def filter(self, labels: Iterable[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """(kept canonical labels in order, fabricated labels), both de-duplicated (S-6 layer 3)."""
        kept: dict[str, None] = {}
        fabricated: dict[str, None] = {}
        for label in labels:
            raw = str(label).strip()
            if not raw:
                continue
            canonical = normalize_label(raw)
            if canonical in self._labels:
                kept[canonical] = None
            else:
                fabricated[canonical or raw] = None
        return tuple(kept), tuple(fabricated)

    def strip_markers(self, text: str) -> tuple[str, list[str], list[str]]:
        """Remove every citation marker; returns (clean_text, allowed_found, fabricated_found)."""
        markers = find_markers(text)
        if not markers:
            return text.strip(), [], []
        found: list[str] = []
        for raw, labels in markers:
            text = text.replace(raw, " ")
            found.extend(labels or [raw])
        kept, fabricated = self.filter(found)
        return _tidy(text), list(kept), list(fabricated)


# ---------------------------------------------------------------------------
# Entailment scorers
# ---------------------------------------------------------------------------
class EntailmentScorer(Protocol):
    """``premise |= hypothesis`` in [0, 1]. Optionally also ``score_batch(pairs) -> list[float]``."""

    def score(self, premise: str, hypothesis: str) -> float: ...


class LexicalEntailmentScorer:
    """Deterministic default: share of the hypothesis' content tokens present in the premise."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._stopwords = stopwords_from(_config(config))

    def score(self, premise: str, hypothesis: str) -> float:
        return overlap(content_tokens(hypothesis, self._stopwords), content_tokens(premise, self._stopwords))


class CrossEncoderNLIScorer:
    """NLI cross-encoder (``entailment_backend: cross_encoder``), local build-time-baked model only.

    The model path is checked before ``sentence_transformers`` is imported; weights
    are never downloaded at runtime (G1).
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = _config(config).get("verifier", {}).get("cross_encoder", {})
        model_path = cfg.get("model_path")
        path = resolve_path(model_path) if model_path else None
        if path is None or not path.exists():
            raise FileNotFoundError(
                f"NLI cross-encoder model not found at {path or '<unset>'} (verifier.cross_encoder.model_path). "
                "Bake it into the image at build time — it is never downloaded at runtime — "
                "or set verifier.entailment_backend: lexical."
            )
        labels = [str(label).lower() for label in cfg.get("labels", ("contradiction", "entailment", "neutral"))]
        missing = {"entailment", "contradiction"} - set(labels)
        if missing:
            raise ValueError(f"verifier.cross_encoder.labels is missing {sorted(missing)}")
        self._entailment = labels.index("entailment")
        self._contradiction = labels.index("contradiction")
        from sentence_transformers import CrossEncoder  # lazy: optional heavy dependency

        self._model = CrossEncoder(str(path), max_length=int(cfg.get("max_length", 256)))
        self._lock = threading.Lock()   # fast tokenizers are not safe under concurrent threads
        self._window = int(cfg.get("premise_window_sentences", 2))

    def probabilities(self, pairs: Sequence[tuple[str, str]]) -> list[list[float]]:
        """Softmax over the label logits, one row per (premise, hypothesis) pair, config label order."""
        if not pairs:
            return []
        with self._lock:
            logits = self._model.predict([list(pair) for pair in pairs], show_progress_bar=False)
        return [_softmax([float(x) for x in row]) for row in logits]

    def score(self, premise: str, hypothesis: str) -> float:
        return self.score_batch([(premise, hypothesis)])[0]

    def score_batch(self, pairs: Sequence[tuple[str, str]]) -> list[float]:
        """Entailment per pair = max over the premise's sentence windows, in one ``predict`` call.

        A short claim scored against a whole multi-sentence chunk is often judged
        neutral or contradicted by the chunk's other sentences ("Venue A holds up to
        40 people." vs a three-sentence chunk: P(entail) ~ 0.001), so each window of
        up to ``premise_window_sentences`` consecutive sentences is scored too.
        """
        expanded: list[tuple[str, str]] = []
        owners: list[int] = []
        for n, (premise, hypothesis) in enumerate(pairs):
            for window in premise_windows(premise, self._window):
                expanded.append((window, hypothesis))
                owners.append(n)
        best = [0.0] * len(pairs)
        for owner, row in zip(owners, self.probabilities(expanded)):
            best[owner] = max(best[owner], row[self._entailment])
        return best

    def contradiction(self, premise: str, hypothesis: str) -> float:
        """P(contradiction) — reusable by Component 3's contradiction gating."""
        return self.probabilities([(premise, hypothesis)])[0][self._contradiction]


def premise_windows(premise: str, size: int) -> list[str]:
    """The whole premise, then every run of 1..``size`` consecutive sentences (deduplicated)."""
    sentences = split_sentences(premise)
    windows = [premise]
    for width in range(1, max(0, size) + 1):
        for start in range(len(sentences) - width + 1):
            windows.append(" ".join(sentences[start:start + width]))
    return list(dict.fromkeys(windows))


def _softmax(logits: Sequence[float]) -> list[float]:
    peak = max(logits)
    exps = [math.exp(x - peak) for x in logits]
    total = sum(exps)
    return [e / total for e in exps]


def threshold_for(config: dict[str, Any] | None = None) -> float:
    """Entailment threshold for the configured backend.

    NLI probabilities and lexical overlap live on different scales, so the
    cross-encoder may set its own ``verifier.cross_encoder.entailment_threshold``
    (calibrated by ``bench/calibrate_nli.py``); otherwise ``entailment_threshold``.
    """
    cfg = _config(config).get("verifier", {})
    own = (cfg.get("cross_encoder") or {}).get("entailment_threshold")
    if cfg.get("entailment_backend") == "cross_encoder" and own is not None:
        return float(own)
    return float(cfg.get("entailment_threshold", 0.6))


def make_scorer(config: dict[str, Any] | None = None) -> EntailmentScorer:
    config = _config(config)
    backend = config.get("verifier", {}).get("entailment_backend", "lexical")
    if backend == "lexical":
        return LexicalEntailmentScorer(config)
    if backend == "cross_encoder":
        return CrossEncoderNLIScorer(config)
    raise ValueError(f"unknown verifier.entailment_backend {backend!r} (expected 'lexical' or 'cross_encoder')")


# ---------------------------------------------------------------------------
# Copy check + claim verification
# ---------------------------------------------------------------------------
EntityExtractor = Callable[[str], Sequence[str]]


class SpacyEntityExtractor:
    """Regex proper nouns plus spaCy NER spans (``verifier.entity_backend: spacy``, audit W-6).

    The regex heuristic skips a lone sentence-initial word, so "Marriott holds up to
    40 people." escaped the copy check; NER catches such names. The model is loaded
    from ``verifier.spacy.model_path`` (baked at build time, never downloaded).
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = _config(config).get("verifier", {}).get("spacy", {}) or {}
        model_path = cfg.get("model_path")
        path = resolve_path(model_path) if model_path else None
        if path is None or not path.exists():
            raise FileNotFoundError(
                f"spaCy model not found at {path or '<unset>'} (verifier.spacy.model_path). Bake it with "
                "scripts/bake_nli_model.py --spacy, or set verifier.entity_backend: regex."
            )
        import spacy  # lazy: optional dependency

        self._nlp = spacy.load(str(path), disable=["parser", "lemmatizer"])
        self._labels = frozenset(str(label) for label in cfg.get("labels", ()))
        self._lock = threading.Lock()

    def __call__(self, text: str) -> list[str]:
        with self._lock:
            doc = self._nlp(text)
        found = list(extract_proper_nouns(text))
        for ent in doc.ents:
            name = _POSSESSIVE_RE.sub("", ent.text).strip()        # "Venue B's" names "Venue B"
            if ent.label_ in self._labels and name and name not in found:
                found.append(name)
        return found


def make_entity_extractor(config: dict[str, Any] | None = None) -> EntityExtractor:
    backend = _config(config).get("verifier", {}).get("entity_backend", "regex")
    if backend == "regex":
        return extract_proper_nouns
    if backend == "spacy":
        return SpacyEntityExtractor(config)
    raise ValueError(f"unknown verifier.entity_backend {backend!r} (expected 'regex' or 'spacy')")


def copy_check(sentence: str, premises: Sequence[str], entities: EntityExtractor = extract_proper_nouns) -> tuple[str, ...]:
    """Hard values of ``sentence`` absent from ALL premises (numerals, names). Empty = pass."""
    available = {numeral for premise in premises for numeral in extract_numerals(premise)}
    lowered = [premise.lower() for premise in premises]
    missing: dict[str, None] = {}
    for numeral in extract_numerals(sentence):
        if numeral not in available:
            missing[numeral] = None
    for noun in entities(sentence):
        pattern = re.compile(r"(?<!\w)" + r"\s+".join(map(re.escape, noun.lower().split())) + r"(?!\w)")
        if not any(pattern.search(premise) for premise in lowered):
            missing[noun] = None
    return tuple(missing)


class PolarityCheck:
    """Catches a sentence that reuses a chunk's words with the opposite polarity (audit W-4, N-1).

    Lexical entailment drops "not"/"no" as stopwords, so "card statements are
    accepted" scores 1.0 against "card statements alone are not accepted". Each
    clause of the sentence is aligned to the premise clause covering most of its
    content tokens, and the two must agree on polarity. When several premise
    clauses tie as best match, the sentence passes if any of them agrees.

    Polarity = parity of negation cues (NLTK's ``nltk.sentiment.util.NEGATION`` list plus
    ``verifier.negation_extra``), minus exempt phrases that are not negations ("not
    only", "no more than"), XOR the parity of antonym swaps: a clause word whose WordNet
    antonym is in the aligned premise clause while the word itself is not ("rejected" vs
    "accepted", "excludes" vs "includes", "optional" vs "mandatory"). So "rejected"
    still agrees with "not accepted". No word list is specific to any corpus; add
    ``verifier.extra_antonym_pairs`` only for vocabulary WordNet lacks.
    Clauses split at sentence ends, ``;`` / ``:`` and ``verifier.clause_splitters``.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = _config(config)
        cfg = config.get("verifier", {})
        self._negation_re = negation_regex(config)
        exempt = [str(p) for p in cfg.get("negation_exempt", ())]
        self._exempt_re = re.compile("|".join(exempt), re.IGNORECASE) if exempt else None
        splitters = [str(p) for p in cfg.get("clause_splitters", ())]
        self._splitter_re = re.compile("|".join(splitters), re.IGNORECASE) if splitters else None
        self._wordnet = WordNet(config)
        self._extra: dict[str, set[str]] = {}
        for a, b in cfg.get("extra_antonym_pairs") or ():
            a, b = self._wordnet.lemma(str(a)), self._wordnet.lemma(str(b))
            self._extra.setdefault(a, set()).add(b)
            self._extra.setdefault(b, set()).add(a)
        self._stopwords = stopwords_from(config)

    def negated(self, text: str) -> bool:
        if self._exempt_re is not None:
            text = self._exempt_re.sub(" ", text)
        return len(self._negation_re.findall(text)) % 2 == 1

    def swaps(self, clause: str, premise_clause: str) -> int:
        """Words of ``clause`` whose WordNet antonym is in ``premise_clause`` (and not vice versa)."""
        mine, theirs = self._lemmas(clause), self._lemmas(premise_clause)
        count = 0
        for word in mine - theirs:
            opposites = self._wordnet.antonyms(word) | self._extra.get(word, set())
            if (opposites & theirs) - mine:
                count += 1
        return count

    def _lemmas(self, text: str) -> set[str]:
        return {self._wordnet.lemma(w) for w in _WORD_RE.findall(text.lower()) if w not in self._stopwords}

    def clauses(self, text: str) -> list[str]:
        out = split_clauses(text)
        if self._splitter_re is not None:
            out = [part for clause in out for part in self._splitter_re.split(clause) if part and part.strip()]
        return out

    def flipped(self, premise: str, sentence: str) -> bool:
        premise_clauses = [(c, set(content_tokens(c, self._stopwords)), self.negated(c)) for c in self.clauses(premise)]
        if not premise_clauses:
            return False
        for clause in self.clauses(sentence):
            tokens = set(content_tokens(clause, self._stopwords))
            if not tokens:
                continue
            coverage = [overlap(tokens, premise_tokens) for _, premise_tokens, _ in premise_clauses]
            best = max(coverage)
            negated = self.negated(clause)
            if all(
                (negated ^ (self.swaps(clause, text) % 2 == 1)) != premise_negated
                for (text, _, premise_negated), cov in zip(premise_clauses, coverage)
                if cov == best
            ):
                return True
        return False


class ClaimVerifier:
    """Per-sentence grounding check (S-5) behind the closed allowlist (S-6). Thread-safe."""

    def __init__(
        self,
        allowlist: CitationAllowlist,
        *,
        config: dict[str, Any] | None = None,
        scorer: EntailmentScorer | None = None,
        entities: EntityExtractor | None = None,
    ) -> None:
        self.allowlist = allowlist
        self.config = _config(config)
        cfg = self.config.get("verifier", {})
        self.threshold = threshold_for(self.config)
        self.copy_check_enabled = bool(cfg.get("copy_check", True))
        self.reattribute_on_failure = bool(cfg.get("reattribute_on_failure", True))
        self.demote_on_fabricated = bool(cfg.get("demote_on_fabricated", True))
        self.polarity = PolarityCheck(self.config) if cfg.get("polarity_check", True) else None
        self.scorer = scorer if scorer is not None else make_scorer(self.config)
        self.entities = entities if entities is not None else make_entity_extractor(self.config)
        self._lock = threading.Lock()
        self.fabricated_ids_stripped = 0
        self.verified = 0
        self.committed = 0
        self.retracted = 0

    def verify(self, draft: DraftClaim) -> VerificationResult:
        started = time.perf_counter()
        text, in_text, in_text_fabricated = self.allowlist.strip_markers(draft.text)
        kept, fabricated = self.allowlist.filter((*draft.citations, *in_text, *in_text_fabricated))
        cited = [chunk for label in kept for chunk in self.allowlist.chunks_for(label)]

        reasons: list[str] = []
        citations: tuple[str, ...] = kept
        best: float | None = None
        missing: tuple[str, ...] = ()
        supporting: tuple[str, ...] = ()
        if not cited:
            reasons.append("no_valid_citation")
        else:
            scores = self._scores(cited, text)
            best = max(scores)
            entailing = [c for c, s in zip(cited, scores) if s >= self.threshold]
            supporting = tuple(c.chunk_id for c in entailing if not self._flipped(c.text, text))
            if not entailing:
                reasons.append("entailment_below_threshold")
            elif not supporting:
                reasons.append("negation_mismatch")
            if self.copy_check_enabled:
                missing = copy_check(text, [c.text for c in cited], self.entities)
                if missing:
                    reasons.append("copy_check_failed:" + ",".join(missing))

        # A §4.4 / S-6 layer 3: a fabricated ID is stripped AND its sentence demoted to
        # uncertainty — a model that invented a source is not trusted on that sentence.
        demote = bool(fabricated) and self.demote_on_fabricated
        if demote:
            reasons.insert(0, "fabricated_citation")
        ok, reattributed = not reasons, False
        if not ok and self.reattribute_on_failure and not demote:
            cited_ids = {c.chunk_id for c in cited}
            candidates = [c for c in self.allowlist.chunks if c.chunk_id not in cited_ids]
            passing, candidate_best = self._reattribute(text, candidates)
            if passing:
                ok = reattributed = True
                citations = tuple(dict.fromkeys(label_for_chunk(c) for c, _ in passing))
                best = max(s for _, s in passing)
                missing = ()
                supporting = tuple(c.chunk_id for c, _ in passing)
                reasons.append("reattributed")
            elif candidates:
                best = candidate_best if best is None else max(best, candidate_best)
                reasons.append("reattribution_failed")
        if not ok:
            supporting = ()

        with self._lock:
            self.verified += 1
            self.fabricated_ids_stripped += len(fabricated)
            if ok:
                self.committed += 1
            else:
                self.retracted += 1
        return VerificationResult(
            draft=draft,
            ok=ok,
            text=text,
            citations=citations,
            fabricated=fabricated,
            entailment=best,
            missing_values=missing,
            reattributed=reattributed,
            supporting_chunk_ids=supporting,
            reasons=tuple(reasons),
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )

    def output_fabricated_count(self, citations: Iterable[str]) -> int:
        """Emitted labels outside the allowlist (exact canonical match) — the CI metric, must be 0."""
        return sum(1 for label in citations if label not in self.allowlist.labels)

    def _scores(self, chunks: Sequence[RetrievedChunk], sentence: str) -> list[float]:
        pairs = [(chunk.text, sentence) for chunk in chunks]
        batch = getattr(self.scorer, "score_batch", None)
        if callable(batch):
            return [float(s) for s in batch(pairs)]
        return [float(self.scorer.score(premise, hypothesis)) for premise, hypothesis in pairs]

    def _reattribute(
        self, sentence: str, candidates: Sequence[RetrievedChunk]
    ) -> tuple[list[tuple[RetrievedChunk, float]], float]:
        """Candidates (allowlist order) passing entailment, polarity AND copy check, plus the best score seen."""
        if not candidates:
            return [], 0.0
        scores = self._scores(candidates, sentence)
        passing = [
            (chunk, score)
            for chunk, score in zip(candidates, scores)
            if score >= self.threshold
            and not self._flipped(chunk.text, sentence)
            and not (self.copy_check_enabled and copy_check(sentence, [chunk.text], self.entities))
        ]
        return passing, max(scores)

    def _flipped(self, premise: str, sentence: str) -> bool:
        return self.polarity is not None and self.polarity.flipped(premise, sentence)


# ---------------------------------------------------------------------------
# S-5: two-pass provisional/committed streaming
# ---------------------------------------------------------------------------
class TwoPassStreamer:
    """PROVISIONAL on arrival; COMMITTED/RETRACTED in arrival order as verification lands."""

    def __init__(self, verifier: ClaimVerifier) -> None:
        self.verifier = verifier
        self._results: list[VerificationResult] = []

    @property
    def results(self) -> list[VerificationResult]:
        return list(self._results)

    def committed_results(self) -> list[VerificationResult]:
        return [result for result in self._results if result.ok]

    async def run(self, drafts: AsyncIterable[DraftClaim] | Iterable[DraftClaim]) -> AsyncIterator[StreamEvent]:
        self._results = []
        iterator = _aiter(drafts)
        pending: deque[tuple[DraftClaim, asyncio.Task[VerificationResult]]] = deque()
        next_draft: asyncio.Task[Any] | None = asyncio.create_task(_next(iterator))
        try:
            while next_draft is not None or pending:
                waiting = {next_draft} if next_draft is not None else set()
                if pending:
                    waiting.add(pending[0][1])
                await asyncio.wait(waiting, return_when=asyncio.FIRST_COMPLETED)
                while pending and pending[0][1].done():
                    draft, task = pending.popleft()
                    yield self._final(draft, task.result())
                if next_draft is not None and next_draft.done():
                    draft = next_draft.result()
                    if draft is _END:
                        next_draft = None
                        continue
                    # Verify sentence N and generate N+1 concurrently, then show N dimmed.
                    pending.append((draft, asyncio.create_task(asyncio.to_thread(self.verifier.verify, draft))))
                    next_draft = asyncio.create_task(_next(iterator))
                    yield self._provisional(draft)
        finally:
            if next_draft is not None:
                next_draft.cancel()
            for _, task in pending:
                task.cancel()

    def _provisional(self, draft: DraftClaim) -> StreamEvent:
        allowlist = self.verifier.allowlist
        text, in_text, _ = allowlist.strip_markers(draft.text)
        citations, _ = allowlist.filter((*draft.citations, *in_text))
        return StreamEvent(
            kind="provisional",
            seq=draft.seq,
            text=text,
            citations=citations,
            facet=draft.facet,
            intent_id=draft.intent_id,
        )

    def _final(self, draft: DraftClaim, result: VerificationResult) -> StreamEvent:
        self._results.append(result)
        return StreamEvent(
            kind="committed" if result.ok else "retracted",
            seq=draft.seq,
            text=result.text,
            citations=result.citations,
            facet=draft.facet,
            intent_id=draft.intent_id,
            verification=result,
        )


async def verify_all(
    verifier: ClaimVerifier, drafts: AsyncIterable[DraftClaim] | Iterable[DraftClaim]
) -> tuple[list[StreamEvent], list[VerificationResult]]:
    streamer = TwoPassStreamer(verifier)
    events = [event async for event in streamer.run(drafts)]
    return events, streamer.results


def _aiter(drafts: AsyncIterable[DraftClaim] | Iterable[DraftClaim]) -> AsyncIterator[DraftClaim]:
    if hasattr(drafts, "__aiter__"):
        return drafts.__aiter__()
    return _from_iterable(drafts)


async def _from_iterable(items: Iterable[DraftClaim]) -> AsyncIterator[DraftClaim]:
    for item in items:
        yield item


async def _next(iterator: AsyncIterator[DraftClaim]) -> Any:
    try:
        return await iterator.__anext__()
    except StopAsyncIteration:
        return _END
