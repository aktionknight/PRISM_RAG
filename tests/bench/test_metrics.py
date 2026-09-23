"""G4/G5 scorers (roadmap 4.11) over run records, plus the golden replay gate CI runs."""

from __future__ import annotations

import copy
import json

import pytest

from bench.metrics import (
    corpus_by_label,
    fabricated_ids,
    gate_failures,
    load_jsonl,
    main,
    make_judge,
    score_g5,
    score_uncertainty,
    summarise,
)
from bench.replay_c4 import replay_all
from tests.helpers import FIXTURES

CORPUS = corpus_by_label(load_jsonl(FIXTURES / "fixture_chunks.jsonl"))


def _claim(claim_id, text, *citations):
    return {"claim_id": claim_id, "facet": "f", "text": text, "citations": list(citations)}


def _record(turn_id, *, claims=(), citations=None, answer="", turn_type="NEW_INTENT", version=1,
            retrieval_events=(), context=None, telemetry=()):
    claims = list(claims)
    citations = citations if citations is not None else sorted({c for claim in claims for c in claim["citations"]})
    record = {"session_id": "s", "turn_id": turn_id, "turn_type": turn_type,
              "output": {"answer": answer, "citations": citations, "claims": claims, "answer_version": version,
                         "retrieval_events": list(retrieval_events)},
              "telemetry": list(telemetry)}
    if context is not None:
        record["context_labels"] = context
    return record


@pytest.fixture(scope="module")
def golden():
    import asyncio

    return asyncio.run(replay_all())


def test_golden_replay_passes_every_g4_g5_gate(golden):
    judge, threshold = make_judge("lexical")
    summary = summarise(golden, CORPUS, judge=judge, threshold=threshold,
                        gold=load_jsonl("bench/data/c4_gold.jsonl"))
    assert gate_failures(summary) == []
    g4, g5 = summary["g4"], summary["g5"]
    assert g4["fabricated_id_count"] == 0 and g4["citation_support_rate"] == 1.0
    assert g4["uncertainty_precision"] == 1.0 and g4["uncertainty_recall"] == 1.0
    assert g5["refinements"] == 2 and g5["full_corpus_searches_on_refinement"] == 0
    # Example 2 retains 3 / supersedes 1; the self-correction edge case retains 4 / supersedes 3.
    assert g5["claims_retained_pct"] == pytest.approx(7 / 11)
    assert g5["delta_queries_per_refinement"] == 2
    assert g5["presentation"] == {"turns": 1, "retrieval_events": 0, "citation_subset_violations": [],
                                  "version_changes": []}


def test_records_are_json_and_carry_the_allowlist(golden):
    for record in golden:
        json.dumps(record)
        assert set(record["output"]["citations"]) <= set(record["context_labels"])


def test_fabricated_ids_count_every_emitted_label():
    record = _record(1, claims=[_claim("c1", "Venue A holds up to 40 people.", "Doc_12 §2", "Doc_77 §9")],
                     answer="Venue A holds up to 40 people. [Doc_12 §2; Doc_99 §1]", context=["Doc_12 §2"])
    assert fabricated_ids(record, CORPUS) == ["Doc_77 §9", "Doc_99 §1"]
    no_allowlist = _record(1, citations=["Doc_12 §2", "Doc_77 §9"])
    assert fabricated_ids(no_allowlist, CORPUS) == ["Doc_77 §9"]          # falls back to the corpus


def test_support_rate_judges_each_claim_once_per_session():
    judge, threshold = make_judge("lexical")
    supported = _claim("c1", "Venue A holds up to 40 people.", "Doc_12 §2")
    unsupported = _claim("c2", "Parking is free for all guests.", "Doc_12 §2")
    records = [_record(1, claims=[supported, unsupported]), _record(2, claims=[supported, unsupported], version=2)]
    g4 = summarise(records, CORPUS, judge=judge, threshold=threshold)["g4"]
    assert g4["claims_judged"] == 2 and g4["citation_support_rate"] == 0.5
    assert [row["claim_id"] for row in g4["unsupported"]] == ["c2"]
    assert any("citation_support_rate=0.500" in f for f in gate_failures(
        summarise(records, CORPUS, judge=judge, threshold=threshold)))


def test_g5_flags_presentation_turns_that_retrieve_or_add_sources():
    v1 = _record(1, citations=["Doc_12 §2"])
    bad = _record(2, turn_type="PRESENTATION_ONLY", citations=["Doc_12 §2", "Doc_31 §4"], version=2,
                  retrieval_events=[{"timestamp_s": 1.0, "query": "q", "trigger": "provisional"}])
    g5 = score_g5([v1, bad])
    assert g5["presentation"] == {"turns": 1, "retrieval_events": 1, "citation_subset_violations": ["s:2"],
                                  "version_changes": ["s:2"]}


def test_g5_flags_a_refinement_that_restarts():
    report = {"claims_retained": 0, "claims_superseded": 4, "delta_queries_issued": 5,
              "full_corpus_searches": 1, "session_cleared": True}
    record = _record(2, telemetry=[{"component": "synthesis.refinement", "payload": report}])
    judge, threshold = make_judge("lexical")
    failures = gate_failures(summarise([record], CORPUS, judge=judge, threshold=threshold))
    assert any("full_corpus_searches" in f for f in failures)
    assert any("cleared the session" in f for f in failures)


def test_uncertainty_precision_uses_gold_facets():
    coverage = {"rows": [{"facet": "a", "state": "uncovered"}, {"facet": "b", "state": "partial"},
                         {"facet": "c", "state": "covered"}]}
    record = _record(1, telemetry=[{"component": "synthesis.coverage", "payload": coverage}])
    scores = score_uncertainty([record], [{"session_id": "s", "turn_id": 1, "uncovered_facets": ["a", "c"]}])
    assert scores == {"uncertainty_flagged": 2, "uncertainty_precision": 0.5, "uncertainty_recall": 0.5}


def test_cli_gate_exit_code(tmp_path, golden, capsys):
    run = tmp_path / "run.jsonl"
    run.write_text("".join(json.dumps(r) + "\n" for r in golden), encoding="utf-8")
    corpus = str(FIXTURES / "fixture_chunks.jsonl")
    assert main(["--run", str(run), "--corpus", corpus, "--gate"]) == 0
    broken = copy.deepcopy(golden)
    broken[0]["output"]["citations"].append("Doc_77 §9")
    run.write_text("".join(json.dumps(r) + "\n" for r in broken), encoding="utf-8")
    assert main(["--run", str(run), "--corpus", corpus, "--gate"]) == 1
    assert "fabricated_id_count" in capsys.readouterr().out
