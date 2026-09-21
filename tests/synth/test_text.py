from slrag.synth.config import load_synth_config
from slrag.synth.text import (
    content_tokens,
    extract_numerals,
    extract_proper_nouns,
    overlap,
    split_sentences,
    stopwords_from,
    tokenize,
)

STOP = stopwords_from(load_synth_config())


def test_tokenize_stems_and_normalises_numerals():
    assert tokenize("Cancellations forfeit the 25% deposit of INR 45,000") == [
        "cancellation", "forfeit", "the", "25%", "deposit", "of", "inr", "45000",
    ]
    assert tokenize("on-site catering policies") == ["on-site", "catering", "policy"]


def test_content_tokens_drop_stopwords_and_single_letters():
    assert content_tokens("Venue B seats up to 60 people", STOP) == ["venue", "seat", "60", "people"]


def test_overlap_is_directional():
    a, b = ["venue", "seat"], ["venue", "seat", "capacity", "people"]
    assert overlap(a, b) == 1.0
    assert overlap(b, a) == 0.5
    assert overlap([], b) == 0.0


def test_split_sentences_and_values():
    text = "Venue A holds up to 40 people. Venue B charges INR 60,000 per day."
    assert split_sentences(text) == ["Venue A holds up to 40 people.", "Venue B charges INR 60,000 per day."]
    assert extract_numerals(text) == ["40", "60000"]
    assert extract_proper_nouns(text) == ["Venue A", "Venue B", "INR"]
    assert extract_proper_nouns("Cancellations made within 14 days.") == []


def test_config_lexicons_are_all_strings():
    """YAML 1.1 turns bare on/no/yes into booleans — guard every lexicon list."""
    config = load_synth_config()

    def walk(node, path):
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for item in node:
                assert not isinstance(item, bool), f"boolean in lexicon {path}"
                walk(item, path)

    walk(config, "synth")
    assert "on" in STOP and "no" in STOP
