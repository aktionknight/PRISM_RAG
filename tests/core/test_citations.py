import pytest

from slrag.core.citations import (
    find_markers,
    format_marker,
    label_for_chunk,
    label_for_chunk_id,
    labels_for_chunks,
    make_chunk_id,
    make_label,
    normalize_label,
    parse_chunk_id,
    parse_label,
)
from tests.helpers import load_corpus


def test_chunk_id_round_trip():
    chunk_id = make_chunk_id("Doc_12", "2", 0)
    assert chunk_id == "Doc_12#2#0"
    assert parse_chunk_id(chunk_id) == ("Doc_12", "2", 0)
    assert label_for_chunk_id(chunk_id) == "Doc_12 §2"


def test_label_round_trip_over_fixture_corpus():
    for chunk in load_corpus().values():
        label = label_for_chunk(chunk)
        assert parse_label(label) == (chunk.doc_id, chunk.section_id)
        assert make_label(*parse_label(label)) == label
        assert label_for_chunk_id(chunk.chunk_id) == label


def test_dotted_sections_and_normalisation():
    assert parse_label("Doc_7 §3.2") == ("Doc_7", "3.2")
    assert normalize_label("Doc_12  §  2") == "Doc_12 §2"
    assert normalize_label("Doc_12 section 2") is None
    with pytest.raises(ValueError):
        parse_label("no section sign")


def test_labels_for_chunks_is_ordered_and_unique():
    corpus = load_corpus()
    chunks = [corpus["Doc_31#4#0"], corpus["Doc_12#2#0"], corpus["Doc_31#4#0"]]
    assert labels_for_chunks(chunks) == ["Doc_31 §4", "Doc_12 §2"]


def test_find_markers_catches_well_formed_and_malformed():
    text = "Venue A holds 40 [Doc_12 §2]. Refunds [Doc_31 §4; Doc_99 §1]. Odd [Source §3]. Plain [note]."
    found = find_markers(text)
    assert [labels for _, labels in found] == [["Doc_12 §2"], ["Doc_31 §4", "Doc_99 §1"], ["Source §3"]]
    assert format_marker(["Doc_12 §2", "Doc_31 §4"]) == "[Doc_12 §2; Doc_31 §4]"
    assert format_marker([]) == ""
