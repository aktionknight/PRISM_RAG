"""Language resources for Component 4 — standard corpora instead of hand-made word lists.

Everything lexical that the classifier, delta engine and verifier need comes from
general-purpose English resources, never from the documents or the brief's examples,
so the same code works on any new corpus:

* **NLTK stopwords** (``stopwords/english``) plus ``text.extra_stopwords`` (request
  words such as "please", "need" that NLTK omits);
* **NLTK negation cues** (``nltk.sentiment.util.NEGATION``, the Potts sentiment list)
  plus ``verifier.negation_extra`` (closed-class cues it omits: "without", "nor", ...);
* **WordNet** (``nltk.corpus.wordnet``) for lemmas, antonyms (direct lemma antonyms
  and their adjective satellites: "domestic" <-> "international", "mandatory" <->
  "optional") and supersenses (``noun.person`` makes "attendees", "guests" and "staff
  members" one countable / role class);
* **Porter stemmer** (``nltk.stem.PorterStemmer``) for the shared tokeniser;
* **spaCy** ``en_core_web_sm`` for dependency parses (constraint extraction) and NER.

Data is loaded from disk only (``text.nltk_data_path``, ``verifier.spacy.model_path``),
baked at build time by ``scripts/bake_nli_model.py --spacy --nltk``; nothing is
downloaded at runtime (HC-1 / G1). Loaded resources are immutable and cached per path.
"""

from __future__ import annotations

import re
import threading
from functools import lru_cache
from typing import Any

from slrag.synth.config import load_synth_config, resolve_path

_NLTK_LOCK = threading.Lock()


class LexiconUnavailable(RuntimeError):
    """A required language resource was not baked into the build."""


# ---------------------------------------------------------------------------
# Loaders (cached per path; the resources themselves are read-only)
# ---------------------------------------------------------------------------
def _config(config: dict[str, Any] | None) -> dict[str, Any]:
    return config if config is not None else load_synth_config()


def _nltk(config: dict[str, Any] | None):
    path = resolve_path((_config(config).get("text", {}) or {}).get("nltk_data_path", "models/nltk_data"))
    return _nltk_at(str(path))


@lru_cache(maxsize=4)
def _nltk_at(path: str):
    import nltk

    with _NLTK_LOCK:
        if path not in nltk.data.path:
            nltk.data.path.insert(0, path)
    try:
        from nltk.corpus import stopwords, wordnet

        stopwords.words("english")
        wordnet.ensure_loaded()
    except LookupError as exc:
        raise LexiconUnavailable(
            f"NLTK data (stopwords, wordnet) not found under {path}. Bake it at build time with "
            "`python scripts/bake_nli_model.py --nltk` (make setup); it is never downloaded at runtime."
        ) from exc
    return nltk


def spacy_model(config: dict[str, Any] | None = None):
    path = resolve_path((_config(config).get("verifier", {}).get("spacy", {}) or {}).get("model_path",
                                                                                        "models/en_core_web_sm"))
    return _spacy_at(str(path))


@lru_cache(maxsize=2)
def _spacy_at(path: str):
    from pathlib import Path

    if not Path(path).exists():
        raise LexiconUnavailable(
            f"spaCy model not found at {path}. Bake it with `python scripts/bake_nli_model.py --spacy` "
            "(make setup); it is never downloaded at runtime."
        )
    import spacy

    return _LockedNLP(spacy.load(path))


class _LockedNLP:
    """spaCy pipelines are not guaranteed thread-safe; verification runs in worker threads."""

    def __init__(self, nlp: Any) -> None:
        self._nlp, self._lock = nlp, threading.Lock()

    def __call__(self, text: str):
        with self._lock:
            return self._nlp(text)


# ---------------------------------------------------------------------------
# Word lists
# ---------------------------------------------------------------------------
def stopwords(config: dict[str, Any] | None = None) -> frozenset[str]:
    cfg = _config(config)
    extra = (cfg.get("text", {}) or {}).get("extra_stopwords", ())
    return _stopwords(str(resolve_path((cfg.get("text", {}) or {}).get("nltk_data_path", "models/nltk_data"))),
                      tuple(map(str, extra)))


@lru_cache(maxsize=8)
def _stopwords(path: str, extra: tuple[str, ...]) -> frozenset[str]:
    from nltk.corpus import stopwords as corpus

    _nltk_at(path)
    return frozenset(w.lower() for w in corpus.words("english")) | frozenset(w.lower() for w in extra)


def negation_regex(config: dict[str, Any] | None = None) -> re.Pattern[str]:
    """NLTK's negation cue list (``nltk.sentiment.util.NEGATION``) + ``verifier.negation_extra``."""
    cfg = _config(config)
    _nltk(cfg)
    from nltk.sentiment.util import NEGATION

    words = re.findall(r"[a-z]+", NEGATION.split("|n't")[0].replace("\n", " "))
    extra = [str(w) for w in cfg.get("verifier", {}).get("negation_extra", ())]
    cues = sorted(set(words) | set(extra))
    return re.compile(r"\b(?:" + "|".join(map(re.escape, cues)) + r")\b|n['’]t\b", re.IGNORECASE)


@lru_cache(maxsize=1)
def _porter():
    from nltk.stem import PorterStemmer

    return PorterStemmer()


# ---------------------------------------------------------------------------
# WordNet
# ---------------------------------------------------------------------------
class WordNet:
    """Lemmas, antonyms and noun classes from WordNet (read-only, cached)."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = _config(config)
        _nltk(cfg)
        from nltk.corpus import wordnet

        self._wn = wordnet
        text = cfg.get("text", {}) or {}
        self._irregular = {str(k).lower(): str(v).lower() for k, v in (text.get("irregular_nouns") or {}).items()}

    def lemma(self, word: str, pos: str | None = None) -> str:
        word = word.lower()
        if word in self._irregular:
            return self._irregular[word]
        tags = {"n": self._wn.NOUN, "v": self._wn.VERB, "a": self._wn.ADJ}
        for tag in ([tags[pos]] if pos in tags else [self._wn.NOUN, self._wn.VERB, self._wn.ADJ]):
            base = self._wn.morphy(word, tag)
            if base:
                return base
        return word

    def antonyms(self, word: str) -> frozenset[str]:
        return _antonyms(self._wn, word.lower())

    def is_person(self, noun: str) -> bool:
        """Does the noun name people (WordNet supersense ``noun.person``)? "attendees", "staff member"."""
        base = self.lemma(noun, "n")
        return _is_person(self._wn, base)


@lru_cache(maxsize=4096)
def _antonyms(wn: Any, word: str) -> frozenset[str]:
    out: set[str] = set()
    base = {wn.morphy(word, pos) for pos in (wn.NOUN, wn.VERB, wn.ADJ, wn.ADV)} - {None}
    for lemma_word in base | {word}:
        for synset in wn.synsets(lemma_word):
            heads = [synset] + (synset.similar_tos() if synset.pos() == "s" else [])
            for head in heads:
                for lemma in head.lemmas():
                    for antonym in lemma.antonyms():
                        out.add(antonym.name().lower())
                        for satellite in antonym.synset().similar_tos():
                            out.update(l.name().lower() for l in satellite.lemmas())
    return frozenset(w for w in out if "_" not in w and w != word)


@lru_cache(maxsize=4096)
def _is_person(wn: Any, noun: str) -> bool:
    synsets = wn.synsets(noun, wn.NOUN)
    return bool(synsets) and synsets[0].lexname() in ("noun.person",) or noun == "person"
