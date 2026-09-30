"""Accounting and frozen-output regressions with unrelated sensor documents."""
from types import SimpleNamespace

import pytest

from slrag.core.schemas import RetrievedChunk, SubIntent
from slrag.core.citations import label_for_chunk, make_label
from slrag.core.session import SessionState
from slrag.decompose.intent_set import IntentSet
from slrag.synth.config import load_synth_config
from slrag.synth.engine import SynthesisEngine, TurnInput, _Telemetry
from slrag.synth.types import DraftClaim, GenerationUsage
from slrag.synth.verifier import CitationAllowlist, ClaimVerifier, make_scorer
from slrag.telemetry.cost import make_cost_accumulator


@pytest.fixture(scope="module")
def grounding_scorer():
    return make_scorer(load_synth_config())


@pytest.mark.parametrize("premise,claim,supported", [
    ("The library lends measuring devices for up to 7 days.",
     "Measuring devices may be borrowed for up to 7 days.", True),
    ("The library lends measuring devices for up to 7 days.",
     "Measuring devices may be borrowed for up to 7 days according to the library reference.", True),
    ("The laboratory has room for 12 visitors.",
     "The laboratory can accommodate 12 visitors.", True),
    ("The hydraulic pressure must stay below 12 bar.",
     "The hydraulic pressure cannot exceed 12 bar.", True),
    ("The sensor requires annual calibration.",
     "The sensor supports underwater operation.", False),
    ("The library lends measuring devices for up to 7 days.",
     "Measuring devices may be borrowed for up to 9 days.", False),
    ("The sensor must not be used underwater.",
     "The sensor may be used underwater.", False),
    ("Lyra reviews the system. The project uses models for entity detection.",
     "Lyra is used for entity detection.", False),
])
def test_grounding_accepts_paraphrases_but_rejects_inventions(
    grounding_scorer, premise, claim, supported
):
    chunk = RetrievedChunk(
        chunk_id="heldout#1#0", doc_id="heldout", section_id="1", text=premise, score=1.0,
    )
    verifier = ClaimVerifier(
        CitationAllowlist([chunk]), config=load_synth_config(), scorer=grounding_scorer,
        exempt="According to the library reference, explain the policy.",
    )
    result = verifier.verify(DraftClaim(
        seq=0, facet="general", text=claim, citations=(label_for_chunk(chunk),),
    ))
    assert result.ok is supported, (result.entailment, result.reasons)


@pytest.mark.parametrize("claim,supported", [
    ("Measuring devices may be borrowed for up to 7 days according to the Northern Field Laboratory reference.", True),
    ("According to the Northern Field Laboratory reference, measuring devices may be borrowed for up to 7 days.", True),
    ("Measuring devices support underwater operation according to the Northern Field Laboratory reference.", False),
    ("Measuring devices may be borrowed for up to 9 days according to the Northern Field Laboratory reference.", False),
])
def test_query_source_attribution_does_not_hide_supported_facts(grounding_scorer, claim, supported):
    chunk = RetrievedChunk(
        chunk_id="field_notes#1#0", doc_id="field_notes", section_id="1", score=1.0,
        text="Researchers may borrow measuring devices for up to 7 days.",
    )
    verifier = ClaimVerifier(
        CitationAllowlist([chunk]), config=load_synth_config(), scorer=grounding_scorer,
        exempt="According to the Northern Field Laboratory reference, how long can devices be borrowed?",
    )
    result = verifier.verify(DraftClaim(seq=0, facet="general", text=claim, citations=(label_for_chunk(chunk),)))
    assert result.ok is supported, (result.entailment, result.reasons)
    if supported:
        assert "according to" not in result.text.lower()


def test_configured_model_pricing_supports_existing_table():
    pricing = {"models": {"sensor-model-1b": {
        "prompt_per_1k_tokens": 0.2, "completion_per_1k_tokens": 0.4}}}
    accumulator = make_cost_accumulator(pricing, model="sensor-model:1b")
    accumulator.add_llm_call(100, 50)
    assert accumulator.total_cost_usd == pytest.approx(0.04)
    assert accumulator.summary()["tokens"] == {"prompt": 100, "completion": 50}


def test_unknown_model_does_not_use_another_models_price():
    accumulator = make_cost_accumulator({"models": {"other": {
        "prompt_per_1k_tokens": 10, "completion_per_1k_tokens": 10}}}, model="unknown")
    accumulator.add_llm_call(100, 100)
    assert accumulator.total_cost_usd == 0
    assert accumulator.llm_calls == 1


def test_allowlisted_citation_does_not_bypass_failed_entailment():
    chunk = RetrievedChunk(
        chunk_id="sensor_manual#1", doc_id="sensor_manual", section_id="1",
        text="Annual calibration is required for the sensor.", score=1.0,
    )
    label = label_for_chunk(chunk)
    verifier = ClaimVerifier(
        CitationAllowlist.from_chunks([chunk]),
        config={"verifier": {"copy_check": False}},
        scorer=SimpleNamespace(score=lambda premise, hypothesis: 0.0),
        entities=lambda _: (),
    )
    result = verifier.verify(DraftClaim(
        seq=0, facet="calibration", text="Sensor calibration is required annually.",
        citations=(label,), intent_id="calibration",
    ))
    assert not result.ok
    assert result.citations == (label,)


@pytest.mark.asyncio
async def test_final_intent_set_retires_a_withdrawn_dispatched_intent():
    state = SessionState(session_id="heldout-intent-scope")
    withdrawn = SubIntent(
        intent_id="withdrawn", facet="equipment", query_nl="Find calibration intervals",
        search_string="calibration intervals", dispatched=True, status="dispatched",
    )
    retained = SubIntent(
        intent_id="retained", facet="equipment", query_nl="Find sensor materials",
        search_string="sensor materials", dispatched=True, status="dispatched",
    )
    state.intent_set.update({withdrawn.intent_id: withdrawn, retained.intent_id: retained})
    await IntentSet(state).retire_omitted_from_final_scope(
        observed_ids={withdrawn.intent_id, retained.intent_id},
        final_ids={retained.intent_id},
    )
    assert state.intent_set[withdrawn.intent_id].status == "superseded"
    assert state.intent_set[retained.intent_id].status == "dispatched"


@pytest.mark.asyncio
async def test_independent_new_intent_replaces_prior_answer_without_old_evidence():
    config = load_synth_config()
    calibration = RetrievedChunk(
        chunk_id="sensor_manual#1", doc_id="sensor_manual", section_id="1",
        text="The sensor requires annual calibration.", score=1.0,
    )
    pressure = RetrievedChunk(
        chunk_id="hydraulic_manual#1", doc_id="hydraulic_manual", section_id="1",
        text="The hydraulic assembly supports 12 bar.", score=1.0,
    )

    class Generator:
        usage = GenerationUsage(backend="heldout")

        async def generate(self, intents, evidence, **kwargs):
            for seq, intent in enumerate(intents):
                chunk = evidence[intent.intent_id][0]
                yield DraftClaim(
                    seq=seq, facet=intent.facet, text=chunk.text,
                    citations=(label_for_chunk(chunk),), intent_id=intent.intent_id,
                )

    engine = SynthesisEngine(
        "heldout-independent-query", config=config, facets={}, generator=Generator(),
        scorer=SimpleNamespace(score=lambda premise, hypothesis: 1.0), entities=lambda _: (),
    )
    sensor_intent = SubIntent(
        intent_id="sensor", facet="calibration", query_nl="Explain sensor calibration",
        search_string="sensor calibration",
    )
    first = await engine.handle_turn(TurnInput(
        turn_id=1, utterance="Explain sensor calibration", t_s_end=1,
        sub_intents=[sensor_intent], evidence={sensor_intent.intent_id: [calibration]},
    ))
    assert calibration.text in first.output.answer

    hydraulic_intent = SubIntent(
        intent_id="hydraulic", facet="pressure", query_nl="Explain hydraulic pressure limits",
        search_string="hydraulic pressure limit",
    )
    second = await engine.handle_turn(TurnInput(
        turn_id=2, utterance="Explain hydraulic pressure limits", t_s_end=2,
        sub_intents=[hydraulic_intent],
        evidence={sensor_intent.intent_id: [calibration], hydraulic_intent.intent_id: [pressure]},
    ))
    assert pressure.text in second.output.answer
    assert calibration.text not in second.output.answer
    assert [claim.text for claim in second.output.claims] == [pressure.text]
    assert first.output.claims[0].claim_id not in {claim.claim_id for claim in second.output.claims}


@pytest.mark.asyncio
async def test_supported_claim_survives_while_unverified_claim_goes_to_uncertainty(grounding_scorer):
    supported = "The sensor requires annual calibration."
    unsupported = "The sensor is also compatible with underwater operation."
    evidence = RetrievedChunk(
        chunk_id="sensor_manual#1", doc_id="sensor_manual", section_id="1",
        text=supported, score=1.0,
    )
    label = label_for_chunk(evidence)

    class Generator:
        usage = GenerationUsage(backend="heldout")

        async def generate(self, intents, evidence_by_intent, **kwargs):
            for seq, sentence in enumerate((supported, unsupported)):
                yield DraftClaim(
                    seq=seq, facet="calibration", text=sentence,
                    citations=(label,), intent_id="calibration",
                )

    engine = SynthesisEngine(
        "heldout-partial-grounding", config=load_synth_config(), facets={}, generator=Generator(),
        scorer=grounding_scorer, entities=lambda _: (),
    )
    intent = SubIntent(
        intent_id="calibration", facet="calibration", query_nl="Describe sensor calibration",
        search_string="sensor calibration",
    )
    result = await engine.handle_turn(TurnInput(
        turn_id=1, utterance="Describe sensor calibration", t_s_end=1,
        sub_intents=[intent], evidence={intent.intent_id: [evidence]},
    ))
    assert supported in result.output.answer
    assert unsupported not in result.output.answer
    assert unsupported in result.output.uncertainty


def test_legacy_pricing_and_per_turn_usage_remain_supported(monkeypatch):
    pricing = {"llm": {"prompt_per_1k": 0.2, "completion_per_1k": 0.4}}
    monkeypatch.setattr("slrag.telemetry.cost.load_pricing", lambda: pricing)
    summary = _Telemetry("heldout", TurnInput(turn_id=1, utterance="sensor calibration", t_s_end=1))
    summary.add("generation", 5, {"llm_calls": 1, "prompt_tokens": 100, "completion_tokens": 50})
    summary.add("render", 2, {"llm_calls": 1, "prompt_tokens": 20, "completion_tokens": 10})
    totals = summary.summary()
    assert totals["tokens"] == {"prompt": 120, "completion": 60}
    assert totals["cost_usd"] == pytest.approx(0.048)
    assert totals["llm_calls"] == 2
    assert totals["latency_ms"] == {"synthesis.generation": 5, "synthesis.render": 2}
    # Repeated serialization must not double-count calls.
    assert summary.summary() == totals
    empty = _Telemetry("heldout", TurnInput(turn_id=2, utterance="repeat that", t_s_end=2))
    assert empty.summary()["llm_calls"] == 0


@pytest.mark.asyncio
async def test_engine_preserves_answer_and_populates_existing_metadata(monkeypatch):
    pricing = {"models": {"sensor-model-1b": {
        "prompt_per_1k_tokens": 0.2, "completion_per_1k_tokens": 0.4}}}
    monkeypatch.setattr("slrag.telemetry.cost.load_pricing", lambda: pricing)
    config = load_synth_config()
    config["generator"]["openai_compatible"]["model"] = "sensor-model:1b"
    label = make_label("sensor_manual", "1")
    text = "The sensor requires annual calibration."

    class Generator:
        usage = GenerationUsage(llm_calls=1, prompt_tokens=100, completion_tokens=50, backend="mock")
        async def generate(self, intents, evidence, **kwargs):
            yield DraftClaim(seq=0, facet="calibration", text=text, citations=(label,), intent_id="calibration")

    class Client:
        async def complete(self, prompt):
            return SimpleNamespace(text=f"{text} [{label}]", prompt_tokens=20, completion_tokens=10)

    generator = Generator()
    generator.client = Client()
    engine = SynthesisEngine("heldout", config=config, facets={}, generator=generator,
        scorer=SimpleNamespace(score=lambda premise, hypothesis: 1.0), entities=lambda _: ())
    intent = SubIntent(intent_id="calibration", facet="calibration", query_nl="Explain sensor calibration", search_string="sensor calibration")
    evidence = RetrievedChunk(chunk_id="sensor_manual#1", doc_id="sensor_manual", section_id="1", text=text, score=1, citation_label=label)
    result = await engine.handle_turn(TurnInput(turn_id=1, utterance="Explain sensor calibration", t_s_end=1,
        sub_intents=[intent], evidence={intent.intent_id: [evidence]}))
    assert result.output.answer == f"{text} [{label}]"
    assert result.output.citations == [label]
    assert len(result.output.claims) == 1
    assert result.output.version_lineage.to_version == 1
    assert result.output.telemetry.tokens == {"prompt": 100, "completion": 50}
    assert result.output.telemetry.cost_usd == pytest.approx(0.04)
    assert result.extensions["telemetry"]["llm_calls"] == 1
    assert result.fabricated_id_count == 0
    presented = await engine.handle_turn(TurnInput(turn_id=2, utterance="repeat that in two bullets", t_s_end=2))
    assert presented.output.telemetry.tokens == {"prompt": 0, "completion": 0}
    assert presented.extensions["telemetry"]["llm_calls"] == 0
    assert presented.output.citations == [label]
