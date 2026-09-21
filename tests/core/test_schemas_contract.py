"""Pins core/schemas.py to C_TEAM_COORDINATION §2 exactly — any drift turns CI red."""

from typing import Literal, get_args, get_origin

import pytest

from slrag.core import schemas

FROZEN = {
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


def _same_type(actual, expected) -> bool:
    if get_origin(expected) is Literal:
        return get_origin(actual) is Literal and set(get_args(actual)) == set(get_args(expected))
    return actual == expected


@pytest.mark.parametrize("model_name", sorted(FROZEN))
def test_model_fields_match_frozen_contract(model_name):
    model = getattr(schemas, model_name)
    fields = [(name, info.annotation) for name, info in model.model_fields.items()]
    expected = FROZEN[model_name]
    assert [name for name, _ in fields] == [name for name, _ in expected]
    for (name, actual), (_, want) in zip(fields, expected):
        assert _same_type(actual, want), f"{model_name}.{name}: {actual!r} != {want!r}"
        assert model.model_fields[name].is_required(), f"{model_name}.{name} must stay required"


def test_no_extra_models_exported():
    models = {name for name, obj in vars(schemas).items() if isinstance(obj, type) and issubclass(obj, schemas.BaseModel)}
    assert models - {"BaseModel"} == set(FROZEN)


def test_answer_output_has_the_five_required_keys():
    required = {"retrieval_events", "sub_queries", "answer", "citations", "uncertainty"}
    assert required <= set(schemas.AnswerOutput.model_fields)
