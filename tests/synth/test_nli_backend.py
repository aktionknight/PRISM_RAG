"""Component 4 on the real NLI cross-encoder (audit I-4). Opt-in: ``make setup-nli && make test-nli``.

Skipped unless ``SLRAG_NLI=1``, ``sentence_transformers`` is installed and the model is
baked at ``verifier.cross_encoder.model_path`` — the default suite stays offline.
"""

from __future__ import annotations

import asyncio
import copy
import os

import pytest

from bench.calibrate_nli import verifier_decisions
from bench.metrics import corpus_by_label, gate_failures, load_jsonl, make_judge, summarise
from bench.replay_c4 import replay_all
from slrag.synth.config import load_synth_config, resolve_path
from tests.helpers import FIXTURES

_CFG = load_synth_config()
_MODEL = resolve_path(_CFG["verifier"]["cross_encoder"]["model_path"])

pytestmark = pytest.mark.skipif(
    os.environ.get("SLRAG_NLI") != "1" or not _MODEL.exists(),
    reason="NLI backend is opt-in: SLRAG_NLI=1 with the model baked (make setup-nli)",
)


@pytest.fixture(scope="module")
def nli_config():
    pytest.importorskip("sentence_transformers")
    config = copy.deepcopy(_CFG)
    config["verifier"]["entailment_backend"] = "cross_encoder"
    return config


@pytest.fixture(scope="module")
def scorer(nli_config):
    from slrag.synth.verifier import make_scorer

    return make_scorer(nli_config)


def test_calibration_pairs_are_all_decided_correctly(nli_config, scorer):
    report = verifier_decisions(nli_config, scorer, load_jsonl("bench/data/nli_calibration.jsonl"))
    assert report["overall"]["false_accepts"] == 0, report["errors"]
    assert report["overall"]["false_rejects"] == 0, report["errors"]


def test_spacy_entities_keep_calibration_and_catch_new_names(nli_config, scorer):
    spacy_model = resolve_path(_CFG["verifier"]["spacy"]["model_path"])
    if not spacy_model.exists():
        pytest.skip("spaCy model not baked (scripts/bake_nli_model.py --spacy)")
    pytest.importorskip("spacy")
    config = copy.deepcopy(nli_config)
    config["verifier"]["entity_backend"] = "spacy"
    report = verifier_decisions(config, scorer, load_jsonl("bench/data/nli_calibration.jsonl"))
    assert report["overall"]["false_rejects"] == 0 and report["overall"]["false_accepts"] == 0, report["errors"]
    from slrag.synth.verifier import make_entity_extractor

    assert "Marriott" in make_entity_extractor(config)("Marriott holds up to 40 people.")


def test_golden_replay_passes_g4_g5_under_the_cross_encoder():
    records = asyncio.run(replay_all(backend="cross_encoder"))
    judge, threshold = make_judge("cross_encoder")
    summary = summarise(records, corpus_by_label(load_jsonl(FIXTURES / "fixture_chunks.jsonl")),
                        judge=judge, threshold=threshold, gold=load_jsonl("bench/data/c4_gold.jsonl"))
    assert gate_failures(summary) == []
    assert summary["g4"]["citation_support_rate"] >= 0.85
    by_turn = {(r["scenario"], r["turn_id"]): r["output"] for r in records}
    assert by_turn[("example1_multi_intent", 1)]["citations"] == ["Doc_12 §2", "Doc_31 §4", "Doc_09 §1"]
    assert by_turn[("example2_refinement", 2)]["citations"] == [
        "Doc_44 §2", "Doc_44 §5", "Doc_44 §6", "Doc_44 §7", "Doc_47 §2"]
