"""Opt-in verification with the real, locally baked cross-encoder."""

import os

import pytest

from slrag.synth.config import load_synth_config
from slrag.synth.verifier import make_scorer, threshold_for


@pytest.mark.skipif(os.environ.get("SLRAG_NLI") != "1", reason="requires setup-nli weights")
def test_baked_nli_distinguishes_supported_and_contradicted_claims():
    config = load_synth_config()
    config["verifier"]["entailment_backend"] = "cross_encoder"
    scorer = make_scorer(config)
    threshold = threshold_for(config)
    premise = "The sensor must be calibrated every 24 months."
    assert scorer.score(premise, "The sensor requires calibration every 24 months.") >= threshold
    assert scorer.score(premise, "The sensor never requires calibration.") < threshold
