"""A3: delta refinement vs full restart on the golden refinement scenarios."""

from bench.ablate_refinement import ablate


async def test_delta_refinement_beats_restart_on_retrieval_evidence_and_staleness():
    report = await ablate(repeat=1)
    assert set(report) == {"example2_refinement", "edge_self_correction_mixed"}
    for name, row in report.items():
        delta, restart = row["delta"], row["restart"]
        assert delta["retrieval_calls"] < restart["retrieval_calls"], name
        assert delta["evidence_chunks"] < restart["evidence_chunks"], name
        assert delta["stale_claims"] == [], name
        assert (delta["answer_version"], restart["answer_version"]) == (2, 1)       # restart loses lineage
    ex2 = report["example2_refinement"]
    assert (ex2["delta"]["retrieval_calls"], ex2["restart"]["retrieval_calls"]) == (2, 4)
    # The naive restart re-asserts the domestic rule after "the trip was international".
    assert any(text.startswith("Domestic trips") for text in ex2["restart"]["stale_claims"])
