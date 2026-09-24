"""Pins core/schemas.py: the v1.0 freeze (C_TEAM_COORDINATION §2) plus the additive v1.1 merge.

v1.0 fields must stay first, in order, with the same types (a Literal may only gain values;
``retrieval_events`` may also hold typed ``RetrievalEvent`` items). Every v1.1 addition must
have a default, so a producer written against v1.0 still validates. Any other drift is red.
"""

from typing import Literal, Union, get_args, get_origin

import pytest

from slrag.core import schemas

FROZEN_V1_0 = {
    "TranscriptChunk": [("t_s", float), ("text", str), ("is_final", bool)],
    "ControllerDecision": [
        ("t_s", float),
        ("decision", Literal["WAIT", "RETRIEVE", "NO_RETRIEVAL"]),
        ("reason", str),
        ("confidence", float),
    ],
    "SubIntent": [("intent_id", str), ("facet", str), ("query_nl", str), ("search_string", str), ("novel", bool)],
    "RetrievedChunk": [("chunk_id", str), ("doc_id", str), ("section_id", str), ("text", str), ("score", float)],
    "Claim": [
        ("claim_id", str),
        ("facet", str),
        ("text", str),
        ("citations", list[str]),
        ("preconditions", dict),
        ("status", Literal["active", "superseded"]),
        ("introduced_in_version", int),
    ],
    "AnswerOutput": [
        ("retrieval_events", list[dict]),
        ("sub_queries", list[str]),
        ("answer", str),
        ("citations", list[str]),
        ("uncertainty", str),
        ("session_id", str),
        ("turn_id", int),
        ("answer_version", int),
    ],
    "TelemetryEvent": [
        ("event_id", str),
        ("session_id", str),
        ("turn_id", int),
        ("ts_stream_s", float),
        ("component", str),
        ("latency_ms", float),
        ("payload", dict),
    ],
}

# v1.1 (merge of the aakrit branch): additive models; all their optional fields default.
ADDED_MODELS = {"RetrievalEvent", "EvidencePoolEntry", "FusedContext", "VersionLineage", "TelemetrySummary"}

# v1.0 fields that v1.1 made optional (defaulted) — loosening only, never removal.
DEFAULTED_V1_0 = {
    ("TranscriptChunk", "is_final"), ("SubIntent", "novel"),
    ("Claim", "preconditions"), ("Claim", "status"), ("Claim", "introduced_in_version"),
    *(("AnswerOutput", name) for name, _ in FROZEN_V1_0["AnswerOutput"]),
    ("TelemetryEvent", "latency_ms"), ("TelemetryEvent", "payload"),
}


def _compatible(actual, frozen) -> bool:
    if get_origin(frozen) is Literal:
        return get_origin(actual) is Literal and set(get_args(frozen)) <= set(get_args(actual))
    if frozen == list[dict]:          # retrieval_events: plain dicts still accepted
        return actual == list[dict] or (get_origin(actual) is list and dict in get_args(get_args(actual)[0])
                                        and get_origin(get_args(actual)[0]) is Union)
    return actual == frozen


@pytest.mark.parametrize("model_name", sorted(FROZEN_V1_0))
def test_v1_0_fields_are_first_unchanged_and_additions_are_defaulted(model_name):
    model = getattr(schemas, model_name)
    fields = list(model.model_fields.items())
    frozen = FROZEN_V1_0[model_name]
    assert [name for name, _ in fields[:len(frozen)]] == [name for name, _ in frozen]
    for (name, info), (_, want) in zip(fields, frozen):
        assert _compatible(info.annotation, want), f"{model_name}.{name}: {info.annotation!r} vs {want!r}"
        if (model_name, name) not in DEFAULTED_V1_0:
            assert info.is_required(), f"{model_name}.{name} must stay required"
    for name, info in fields[len(frozen):]:
        assert not info.is_required(), f"v1.1 addition {model_name}.{name} must have a default"


def test_only_known_models_are_exported():
    models = {name for name, obj in vars(schemas).items() if isinstance(obj, type) and issubclass(obj, schemas.BaseModel)}
    assert models - {"BaseModel"} == set(FROZEN_V1_0) | ADDED_MODELS


def test_answer_output_has_the_five_required_keys():
    required = {"retrieval_events", "sub_queries", "answer", "citations", "uncertainty"}
    assert required <= set(schemas.AnswerOutput.model_fields)


def test_v1_0_producers_still_validate():
    """A v1.0-style payload (plain strings, 3-key retrieval events) validates unchanged."""
    decision = schemas.ControllerDecision(t_s=0.1, decision="WAIT", reason="translation", confidence=0.5)
    assert decision.reason == "translation"                    # open vocabulary, not the enum
    out = schemas.AnswerOutput(retrieval_events=[{"timestamp_s": 0.8, "query": "q", "trigger": "provisional"}],
                               sub_queries=["q"], answer="a", citations=[], uncertainty="",
                               session_id="s", turn_id=1, answer_version=1)
    assert out.model_dump()["retrieval_events"] == [{"timestamp_s": 0.8, "query": "q", "trigger": "provisional"}]
    chunk = schemas.RetrievedChunk(chunk_id="Doc_1#2#0", doc_id="Doc_1", section_id="2", text="t", score=0.5)
    assert chunk.citation_label == "Doc_1 §2"


def test_enums_interchange_with_v1_0_strings():
    d = schemas.ControllerDecision(t_s=0.0, decision=schemas.ControllerDecisionType.RETRIEVE,
                                   reason=schemas.ControllerReason.stub, confidence=1.0)
    assert d.decision == "RETRIEVE" and d.reason == "stub"
    c = schemas.Claim(claim_id="c1", facet="f", text="t", citations=[], status=schemas.ClaimStatus.retracted)
    assert c.status == "retracted" == schemas.ClaimStatus.retracted
