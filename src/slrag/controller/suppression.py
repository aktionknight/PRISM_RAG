import json
import logging
from pathlib import Path
import re
from typing import Optional, Any

from slrag.core.schemas import ControllerDecision
from slrag.core.config import get_controller_config
from slrag.controller.content_floor import count_content_anchors

logger = logging.getLogger(__name__)

# Closed-class English function words + high-frequency generic auxiliary/reporting verbs
# (Purely grammatical function words; NO domain vocabulary, fully adhering to Rule 3)
STOPWORDS = frozenset({
    'the', 'a', 'an', 'is', 'am', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'to', 'at', 'in', 'for', 'on',
    'with', 'by', 'of', 'about', 'into', 'through', 'during', 'before', 'after',
    'above', 'below', 'from', 'up', 'down', 'out', 'off', 'over', 'under',
    'again', 'further', 'then', 'once', 'here', 'there', 'when', 'where', 'why',
    'how', 'all', 'any', 'both', 'each', 'few', 'more', 'most', 'other', 'some',
    'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too',
    'very', 'can', 'will', 'just', 'don', 'should', 'now', 'it', 'its', 'this',
    'that', 'these', 'those', 'i', 'me', 'my', 'myself', 'we', 'our', 'ours',
    'ourselves', 'you', 'your', 'yours', 'yourself', 'yourselves', 'he', 'him',
    'his', 'himself', 'she', 'her', 'hers', 'herself', 'they', 'them', 'their',
    'theirs', 'themselves', 'and', 'but', 'or', 'if', 'because', 'as', 'until',
    'while', 'tell', 'show', 'give', 'make', 'makes', 'made', 'say', 'says',
    'said', 'put', 'puts', 'get', 'gets', 'got', 'let', 'lets', 'see', 'also'
})

# Presentation/formatting vocabulary that represents the vehicle/style of the request,
# not domain content from the corpus.
PRESENTATION_VOCABULARY = frozenset({
    "repeat", "rephrase", "shorten", "summarize", "summarise", "bullets",
    "bullet", "points", "point", "translate", "tone", "reformat", "simplify",
    "elaborate", "expand", "shorter", "longer", "words", "word", "differently",
    "answer", "response", "table", "list", "summary", "terms", "term",
    "sentence", "sentences", "paragraph", "paragraphs", "line", "lines", "one", "two", "three", "four", "five",
    "findings", "finding", "results", "result"
})

_DOC_TERMS_CACHE: Optional[set[str]] = None


def reset_suppression_cache() -> None:
    """Clear cached indexed document terms."""
    global _DOC_TERMS_CACHE
    _DOC_TERMS_CACHE = None


def get_indexed_doc_terms() -> set[str]:
    """Dynamically extract title and identifier terms from each indexed document in the corpus."""
    global _DOC_TERMS_CACHE
    if _DOC_TERMS_CACHE is not None:
        return _DOC_TERMS_CACHE

    doc_terms: set[str] = set()

    # 1. Inspect .index/metadata.json for all indexed document IDs
    from slrag.core.paths import index_dir, corpus_dir as selected_corpus_dir
    meta_path = index_dir() / "metadata.json"
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            for key in meta.keys():
                doc_id = key.split("#")[0]
                for part in re.split(r"[-_ ]+", doc_id.lower()):
                    if len(part) > 2 and part not in STOPWORDS and part not in PRESENTATION_VOCABULARY:
                        doc_terms.add(part)
        except Exception as e:
            logger.debug(f"Could not load doc_ids from metadata.json: {e}")

    # 2. Inspect corpus directory files for any document stems
    corpus_dir = selected_corpus_dir()
    if corpus_dir.exists():
        try:
            for p in corpus_dir.glob("**/*.*"):
                if p.is_file() and p.suffix.lower() in (".md", ".txt", ".pdf"):
                    for part in re.split(r"[-_ ]+", p.stem.lower()):
                        if len(part) > 2 and part not in STOPWORDS and part not in PRESENTATION_VOCABULARY:
                            doc_terms.add(part)
        except Exception as e:
            logger.debug(f"Could not load doc_ids from corpus dir: {e}")

    _DOC_TERMS_CACHE = doc_terms
    return _DOC_TERMS_CACHE


def has_indexed_document_match(prefix: str, index_mock: Any = None) -> bool:
    """Checks whether the prefix matches any indexed document (via title/doc_id or BM25 content)."""
    prefix_lower = prefix.lower()
    doc_terms = get_indexed_doc_terms()

    # 1. Check if prefix explicitly contains document title/name terms
    prefix_words = set(re.findall(r"\b[a-zA-Z0-9_-]+\b", prefix_lower))
    if any(t in prefix_words for t in doc_terms):
        return True

    # 2. Check if non-stopword, non-presentation content words match indexed passages in BM25
    content_words = [
        w for w in prefix_words 
        if len(w) > 2 and w not in STOPWORDS and w not in PRESENTATION_VOCABULARY
    ]
    if not content_words:
        return False

    # Check mock index if provided
    if index_mock is not None:
        try:
            scores = index_mock.query(" ".join(content_words), k=3)
            if len(scores) > 0 and float(scores[0]) > 0.5:
                return True
        except Exception:
            pass
    else:
        # Check loaded BM25 probe
        try:
            from slrag.controller.probe import _load_bm25_probe
            bm25 = _load_bm25_probe()
            if bm25 is not None:
                import bm25s
                tokens = bm25s.tokenize([" ".join(content_words)], show_progress=False)
                docs, score_matrix = bm25.retrieve(tokens, k=3, show_progress=False)
                if len(score_matrix) > 0 and len(score_matrix[0]) > 0 and float(score_matrix[0][0]) > 0.5:
                    return True
        except Exception as e:
            logger.debug(f"Error querying BM25 in suppression check: {e}")

    return False


def count_domain_anchors(prefix: str) -> int:
    """Count substantive domain content anchors excluding generic presentation nouns."""
    try:
        from slrag.controller.content_floor import _get_nlp
        nlp = _get_nlp()
        doc = nlp(prefix)
    except Exception:
        return count_content_anchors(prefix)

    anchors = 0
    if not doc.has_annotation("ENT_IOB"):
        words = prefix.split()
        return sum(
            1 for w in words 
            if (len(w) > 4 or (len(w) > 3 and w[0].isupper())) 
            and w.lower() not in STOPWORDS 
            and w.lower() not in PRESENTATION_VOCABULARY
        )

    for ent in doc.ents:
        if ent.label_ in ["GPE", "ORG", "PRODUCT"]:
            anchors += 1
        elif ent.label_ == "CARDINAL":
            # If the cardinal modifies a presentation noun (e.g. "two bullets", "3 points"), it is a format count
            is_format_num = any(
                t.head.lemma_.lower() in PRESENTATION_VOCABULARY or t.lemma_.lower() in PRESENTATION_VOCABULARY
                for t in ent
            )
            if not is_format_num:
                anchors += 1

    for token in doc:
        if token.pos_ in ["NOUN", "PROPN"] and not token.ent_type_:
            token_clean = token.lemma_.lower()
            if token_clean not in PRESENTATION_VOCABULARY and token.text.lower() not in PRESENTATION_VOCABULARY:
                anchors += 1

    return anchors


def evaluate_suppression(
    prefix: str,
    t_s: float,
    index_mock: Any = None,
) -> Optional[ControllerDecision]:
    """
    Stage 0 — Suppression Gate.

    Detects true presentation restructuring requests (e.g. "repeat that in two bullets",
    "summarize your answer", "make it shorter") while ensuring queries targeting
    indexed documents are NEVER suppressed.
    """
    config = get_controller_config()
    prefix_lower = prefix.lower().strip()
    if not prefix_lower:
        return None

    # 1. Check for presentation directives/verbs
    presentation_verbs = config.get("presentation_verbs", [])
    has_presentation = any(
        re.search(r"\b" + re.escape(verb) + r"\b", prefix_lower)
        for verb in presentation_verbs
    )
    # Check for formatting phrases like "in bullets", "in a table", etc.
    if re.search(r"\b(in bullets|in bullet points|as a list|as bullets|in a table)\b", prefix_lower):
        has_presentation = True

    # 2. Check for explicit references to prior response
    explicit_prior_refs = [
        "your last answer",
        "your previous answer",
        "the previous answer",
        "the last answer",
        "your answer",
        "your response",
        "the response",
        "what you said",
        "what you just said",
        "the above",
        "your findings",
        "your results",
    ]
    has_prior_ref = any(
        re.search(r"\b" + re.escape(ref) + r"\b", prefix_lower)
        for ref in explicit_prior_refs
    )

    # Bare pronouns ('it', 'this', 'that') CANNOT trigger suppression on their own.
    # They only count as anaphora if directly paired with a presentation verb (e.g. "summarize it", "repeat that").
    bare_pronouns = ["it", "this", "that"]
    has_pronoun = any(
        re.search(r"\b" + re.escape(p) + r"\b", prefix_lower)
        for p in bare_pronouns
    )
    has_valid_anaphora = has_prior_ref or (has_presentation and has_pronoun)

    # 3. Suppression requires a genuine presentation restyle request:
    if not (has_presentation or has_valid_anaphora):
        return None

    # A prior-answer restyle with no substantive additions never needs a corpus probe.
    words = set(re.findall(r"\b[a-zA-Z0-9_-]+\b", prefix_lower))
    neutral = STOPWORDS | PRESENTATION_VOCABULARY | set(config.get("presentation_reference_words", ()))
    if has_valid_anaphora and all(word in neutral or word.isdigit() for word in words):
        return ControllerDecision(t_s=t_s, decision="NO_RETRIEVAL", reason="presentation_restructure",
                                  confidence=0.9, stage=0, stage_name="Stage 0: Suppression", threshold=0.0)

    # 4. Information Query Guard:
    # If the user is asking an information query ("why", "what", "where", "how", "tell me", "list out", "?"),
    # they are seeking substantive content from the documents, NOT a pure presentation restructure.
    is_question = "?" in prefix_lower
    has_question_cue = bool(
        re.search(r"\b(why|what|when|where|who|whom|which|how|tell me|list out|list all|compare|describe)\b", prefix_lower)
    )
    if is_question or has_question_cue:
        return None

    # 5. Indexed Document Grounding Guard:
    # If the prefix references any indexed document or matches content passages in the corpus, NEVER suppress.
    if has_indexed_document_match(prefix, index_mock=index_mock):
        return None

    # 6. Content Floor Guard:
    # If new content anchors exist (entities, proper nouns, domain nouns), do not suppress.
    anchors = count_domain_anchors(prefix)
    if anchors > 0:
        return None

    return ControllerDecision(
        t_s=t_s,
        decision="NO_RETRIEVAL",
        reason="presentation_restructure",
        confidence=0.9,
        stage=0,
        stage_name="Stage 0: Suppression",
        threshold=0.0,
    )

