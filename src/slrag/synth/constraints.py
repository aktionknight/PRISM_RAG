"""Corpus-independent constraint extraction from a dependency parse (S-4 step 2).

A constraint is a (key, value) pair read off the grammar of a sentence with spaCy,
never off a list of domain slots, so the delta engine works on any document set:

  pattern (spaCy dependency)                      example                         key           value
  ----------------------------------------------  ------------------------------  ------------  ----------------
  number modifying a noun (``nummod``)            "for 40 people"                 count:person  40
                                                  "5 books"                       count:book    5
  adjective / noun modifier of a noun             "domestic trips"                trip          domestic
    (``amod``, ``compound``) or predicate          "the trip was international"    trip          international
    adjective of its subject (``acomp``)
  prepositional phrase on a verb (``prep``)       "booked after travel"           book          after travel
  the user's role (``attr`` of I/we, or           "I'm a staff member"            role          staff member
    "as a <person>"), and person subjects         "Undergraduate students may"    role          undergraduate student
  place names (NER ``GPE`` / ``LOC``)             "in Pune"                       location      pune

Heads are WordNet lemmas; nouns whose WordNet supersense is ``noun.person`` ("people",
"attendees", "guests", "delegates") share the ``person`` class, so "30 people" and
"seats 30 attendees" talk about the same count. Counts are *user* constraints: a claim
never gets a count precondition from its own numbers ("holds up to 40 people" is a fact),
only from the session. A claim may carry several values for one key ("booked in
advance through the portal"); they are stored joined by ``|``.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable, Mapping

from slrag.synth.lexicon import WordNet, spacy_model, stopwords
from slrag.synth.text import extract_numerals
from slrag.synth.types import ConstraintDelta

SEP = "|"
COUNT = "count:"
ROLE = "role"
LOCATION = "location"
_USER = frozenset({"i", "we"})
_PLACE_LABELS = frozenset({"GPE", "LOC"})


@dataclass(frozen=True)
class Constraint:
    key: str
    value: str
    phrase: str                     # surface text for queries ("40 people", "international trip")

    @property
    def numeric(self) -> bool:
        return self.key.startswith(COUNT)


def values_of(value: Any) -> list[str]:
    return [v for v in str(value).split(SEP) if v]


class ConstraintExtractor:
    """Parse-based slot filling; same interface the delta engine and classifier use."""

    def __init__(self, config: dict | None = None, facets: dict | None = None) -> None:
        from slrag.synth.config import load_synth_config

        self.config = load_synth_config() if config is None else config
        self.facets = facets or {}
        self._nlp = lru_cache(maxsize=2048)(spacy_model(self.config))   # per-engine; parses are read-only
        self._wordnet = WordNet(self.config)
        self._stop = stopwords(self.config)
        self._locative = frozenset(map(str, (self.config.get("text", {}) or {}).get("locative_prepositions", ())))

    # -- parsing -----------------------------------------------------------------
    def parse(self, text: str, *, user: bool = True) -> list[Constraint]:
        """Constraints stated in ``text``. ``user=False`` (claims) skips counts and user roles."""
        doc = self._nlp(text)
        found: list[Constraint] = []
        for token in doc:
            head = token.head
            if token.dep_ == "nummod" and head.pos_ in ("NOUN", "PROPN") and user:
                number = extract_numerals(token.text)
                if number:
                    found.append(Constraint(COUNT + self._noun_class(head), number[0], f"{token.text} {head.text}"))
            elif token.dep_ in ("amod", "compound") and head.pos_ == "NOUN" and self._content(token):
                if self._wordnet.is_person(head.text):
                    if user or head.dep_ in ("nsubj", "nsubjpass"):
                        found.append(self._role(head))
                    continue
                found.append(Constraint(self._lemma(head, "n"), self._modifier(token), f"{token.text} {head.text}"))
            elif token.dep_ == "acomp" and self._content(token):
                subjects = [c for c in head.children if c.dep_ in ("nsubj", "nsubjpass") and c.pos_ in ("NOUN", "PROPN")]
                for subject in subjects:
                    found.append(Constraint(self._lemma(subject, "n"), self._modifier(token),
                                            f"{token.text} {subject.text}"))
            elif token.tag_ == "VBN" and token.dep_ == "ROOT" and self._content(token) and not any(
                    c.dep_ in ("agent", "dobj", "prep") for c in token.children):
                # "the laptop is refurbished": a bare passive participle describes its subject
                for subject in (c for c in token.children if c.dep_ == "nsubjpass" and c.pos_ == "NOUN"):
                    found.append(Constraint(self._lemma(subject, "n"), self._modifier(token),
                                            f"{token.text} {subject.text}"))
            elif token.dep_ == "prep" and head.pos_ == "VERB" and self._content(head):
                # "for 40 people" is already a count constraint; don't let it overwrite "after travel"
                objects = [c for c in token.children if c.dep_ == "pobj" and self._content(c)
                           and not any(g.dep_ == "nummod" for g in c.children) and not self._wordnet.is_person(c.text)]
                if objects:
                    value = f"{token.lower_} {self._lemma(objects[0], 'n')}"
                    found.append(Constraint(self._lemma(head, "v"), value, f"{head.text} {token.text} {objects[0].text}"))
            elif token.dep_ == "attr" and user and self._wordnet.is_person(token.text):
                if any(c.lower_ in _USER for c in head.children if c.dep_ == "nsubj"):
                    found.append(self._role(token))
            elif token.dep_ == "pobj" and user and head.lower_ == "as" and self._wordnet.is_person(token.text):
                found.append(self._role(token))
            elif token.dep_ in ("nsubj", "nsubjpass") and not user and self._wordnet.is_person(token.text):
                if any(c.dep_ in ("amod", "compound") for c in token.children):
                    continue                     # handled with its modifier above
                found.append(self._role(token))
        places = [ent for ent in doc.ents if ent.label_ in _PLACE_LABELS]
        seen = {t.i for ent in places for t in ent}
        for token in doc:   # NER misses some places ("in Bangalore" -> PERSON): proper noun after in/at/near
            if (token.pos_ == "PROPN" and token.dep_ == "pobj" and token.head.lower_ in self._locative
                    and token.i not in seen and not self._wordnet.is_person(token.text)):
                places.append(doc[token.left_edge.i:token.i + 1])
        for place in places:
            found.append(Constraint(LOCATION, place.text.lower(), place.text))
        return found

    def extract(self, text: str, slots: Iterable[str] | None = None) -> ConstraintDelta:
        """User constraints in an utterance (one value per key; the last mention wins)."""
        wanted = None if slots is None else set(slots)
        values: dict[str, str] = {}
        phrases: dict[str, str] = {}
        for constraint in self.parse(text, user=True):
            if wanted is not None and constraint.key not in wanted:
                continue
            values[constraint.key] = constraint.value
            phrases[constraint.key] = constraint.phrase
        return ConstraintDelta(slots=values, raw_text=text, phrases=phrases)

    def claim_scope(self, text: str) -> dict[str, str]:
        """What a claim's own text restricts it to (``{"trip": "domestic"}``)."""
        scope: dict[str, list[str]] = {}
        for constraint in self.parse(text, user=False):
            scope.setdefault(constraint.key, [])
            if constraint.value not in scope[constraint.key]:
                scope[constraint.key].append(constraint.value)
        return {key: SEP.join(values) for key, values in scope.items()}

    def derive_preconditions(self, claim_text: str, facet: str, session_constraints: Mapping[str, str]) -> dict[str, str]:
        """The claim's own scope, plus each session count whose unit the claim talks about."""
        out = self.claim_scope(claim_text)
        for key, value in session_constraints.items():
            if key.startswith(COUNT) and key not in out and self.mentions_key(key, claim_text):
                out[key] = str(value)
        return out

    # -- queries used by the delta engine and classifier ------------------------
    def is_numeric(self, slot: str) -> bool:
        return slot.startswith(COUNT)

    def mentions_key(self, key: str, text: str) -> bool:
        """Does ``text`` talk about the thing ``key`` constrains (its noun, verb, unit class, a role, a place)?"""
        doc = self._nlp(text)
        if key.startswith(COUNT):
            unit = key[len(COUNT):]
            return any(t.pos_ in ("NOUN", "PROPN") and self._noun_class(t) == unit for t in doc)
        if key == ROLE:
            return any(t.pos_ in ("NOUN", "PROPN") and self._wordnet.is_person(t.text) for t in doc)
        if key == LOCATION:
            return any(e.label_ in _PLACE_LABELS for e in doc.ents) or any(
                t.pos_ == "PROPN" and t.dep_ == "pobj" and t.head.lower_ in self._locative for t in doc)
        return any(
            self._lemma(t, "v") == key if t.pos_ == "VERB" else self._wordnet.related(self._lemma(t, "n"), key)
            for t in doc if t.is_alpha and t.pos_ in ("NOUN", "PROPN", "VERB")
        )

    def mentions(self, slot: str, value: str, text: str) -> bool:
        """Does ``text`` state ``slot=value``? Counts: the number and its unit both appear."""
        if slot.startswith(COUNT):
            return value in extract_numerals(text) and self.mentions_key(slot, text)
        scope = self.claim_scope(text)
        return value in values_of(scope.get(slot, ""))

    def value_phrase(self, slot: str, value: str, delta: ConstraintDelta | None = None) -> str:
        if delta is not None and delta.phrases.get(slot):
            return str(delta.phrases[slot])
        if slot.startswith(COUNT):
            return f"{value} {slot[len(COUNT):]}"
        if slot in (ROLE, LOCATION):
            return value
        return f"{value} {slot}"

    # -- helpers -------------------------------------------------------------------
    def _role(self, noun: Any) -> Constraint:
        modifiers = [c for c in noun.children if c.dep_ in ("amod", "compound") and self._content(c)]
        words = [self._modifier(m) if m.dep_ == "amod" else self._lemma(m, "n")
                 for m in sorted(modifiers, key=lambda t: t.i)]
        value = " ".join([*words, self._lemma(noun, "n")])
        phrase = " ".join([*(m.text for m in sorted(modifiers, key=lambda t: t.i)), noun.text])
        return Constraint(ROLE, value, phrase)

    def _noun_class(self, noun: Any) -> str:
        return "person" if self._wordnet.is_person(noun.text) else self._lemma(noun, "n")

    def _lemma(self, token: Any, pos: str) -> str:
        """spaCy's lemma (handles "terms" -> "term"), then WordNet morphology and irregular nouns."""
        lemma = (token.lemma_ or token.text).lower()
        return self._wordnet.lemma(lemma, pos)

    @staticmethod
    def _modifier(token: Any) -> str:
        """Modifiers keep their surface form so "refurbished laptop" and "is refurbished" agree."""
        return token.lower_

    def _content(self, token: Any) -> bool:
        return token.is_alpha and token.lower_ not in self._stop and len(token.text) > 1
