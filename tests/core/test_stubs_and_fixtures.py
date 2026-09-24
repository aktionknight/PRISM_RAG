"""Walking-skeleton stubs and golden fixtures must be schema-valid (C_TEAM_COORDINATION §3)."""

import json

from slrag.core.schemas import AnswerOutput, ControllerDecision, RetrievedChunk, SubIntent, TranscriptChunk
from slrag.stubs import fake_controller, fake_decompose, fake_retrieve, fake_synthesize
from tests.helpers import FIXTURES, load_corpus, load_scenarios, load_stream, split_turns, turn_evidence, turn_sub_intents


def test_stubs_return_schema_valid_output():
    from slrag.stubs.fake_controller import reset_stub

    reset_stub()
    stream = load_stream("golden_example.jsonl")
    decisions = [fake_controller(chunk) for chunk in stream]
    assert all(isinstance(d, ControllerDecision) for d in decisions)
    assert decisions[0].decision == "WAIT" and decisions[-1].decision == "RETRIEVE"
    intents = fake_decompose(stream[1].text)
    assert all(isinstance(i, SubIntent) for i in intents)
    chunks = fake_retrieve(intents[0])
    assert all(isinstance(c, RetrievedChunk) for c in chunks)
    output = fake_synthesize()
    assert isinstance(output, AnswerOutput)
    AnswerOutput.model_validate(json.loads(output.model_dump_json()))


def test_stub_retriever_chunk_matches_fixture_corpus_identity():
    """Stub chunks carry real fixture identities, so their citations resolve in the corpus."""
    intent = SubIntent(intent_id="i1", facet="venue_capacity", query_nl="q", search_string="q", novel=True)
    stub = fake_retrieve(intent)[0]              # the decomposer stub is stateful; ask the retriever directly
    fixture = load_corpus()[stub.chunk_id]
    assert (stub.doc_id, stub.section_id) == (fixture.doc_id, fixture.section_id)
    assert stub.citation_label == f"{fixture.doc_id} §{fixture.section_id}"


def test_golden_streams_are_schema_valid_and_monotonic_per_turn():
    for name in ("golden_example.jsonl", "golden_example2_refinement.jsonl", "golden_example3_presentation.jsonl"):
        for turn in split_turns(load_stream(name)):
            assert all(isinstance(c, TranscriptChunk) for c in turn)
            times = [c.t_s for c in turn]
            assert times == sorted(times)
            assert turn[-1].is_final


def test_scenarios_reference_known_chunks_and_facets():
    from slrag.synth.config import load_facets

    corpus, facets = load_corpus(), load_facets()
    for scenario in load_scenarios().values():
        assert (FIXTURES / scenario["stream"]).exists()
        for turn in scenario["turns"]:
            assert all(i.facet in facets for i in turn_sub_intents(turn))
            evidence = turn_evidence(turn)
            assert set(evidence) <= {i.intent_id for i in turn_sub_intents(turn)}
            for rows in turn.get("delta_evidence", {}).values():
                assert all(chunk_id in corpus for chunk_id, _ in rows)
