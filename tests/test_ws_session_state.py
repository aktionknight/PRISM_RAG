"""Held-out live-session wiring checks, without model/network dependencies."""

from types import SimpleNamespace

import pytest

from slrag.api import ws_server
from slrag.core.citations import make_label
from slrag.core.schemas import RetrievedChunk, SubIntent
from slrag.retrieve.pool import add_to_pool
from slrag.synth import engine as synthesis


class Socket:
    def __init__(self):
        self.messages = []

    async def send_json(self, message):
        self.messages.append(message)


class Bus:
    async def emit(self, event):
        pass


@pytest.fixture
def engines(monkeypatch):
    created = []

    class Engine:
        def __init__(self, session_id, **kwargs):
            self.session_id = session_id
            self.kwargs = kwargs
            self.turns = []
            self.destroyed = False
            created.append(self)

        async def stream_turn(self, turn):
            self.turns.append(turn)
            if False:
                yield None

        def destroy(self):
            self.destroyed = True
            self.turns.clear()

    monkeypatch.setattr(synthesis, "SynthesisEngine", Engine)
    monkeypatch.setattr(ws_server, "get_bus", lambda: Bus())
    return created


@pytest.mark.asyncio
async def test_live_turns_reuse_engine_and_other_sessions_are_isolated(engines):
    manager = ws_server.SessionManager()
    first = manager.create("session-a")
    second = manager.create("session-b")
    socket = Socket()
    first.prefix = "What pressure does the hydraulic assembly support?"
    await ws_server._process_utterance_end(first, socket)
    first.prefix = "Repeat that in two bullets."
    await ws_server._process_utterance_end(first, socket)
    second.prefix = "What is the storage temperature for the reagent?"
    await ws_server._process_utterance_end(second, socket)

    assert len(engines) == 2
    assert [turn.turn_id for turn in engines[0].turns] == [1, 2]
    assert engines[0].turns[1].utterance == "Repeat that in two bullets."
    assert engines[1].session_id == "session-b"
    manager.end("session-a")
    assert engines[0].destroyed
    assert not engines[1].destroyed
    manager.reset_all()
    assert engines[1].destroyed


@pytest.mark.asyncio
async def test_refinement_callback_uses_dense_retriever_and_session_pool(engines, monkeypatch):
    manager = ws_server.SessionManager()
    session = manager.create("heldout")
    session.prefix = "What pressure does the hydraulic assembly support?"
    await ws_server._process_utterance_end(session, Socket())
    chunk = RetrievedChunk(chunk_id="hydraulic-1", doc_id="manual", section_id="limits",
                           citation_label=make_label("manual", "limits"), text="Operating pressure is 12 bar.", score=0.8)
    add_to_pool(session.state, chunk, "original", 0.0)
    calls = []

    async def search(query, top_k):
        calls.append((query, top_k))
        return [chunk]

    monkeypatch.setattr(ws_server, "get_retriever", lambda: SimpleNamespace(search=search))
    engine = engines[0]
    assert [c.chunk_id for c in engine.kwargs["pool"].chunks()] == ["hydraulic-1"]
    query = SubIntent(intent_id="target", facet="limits", query_nl="Pressure with a smaller assembly",
                      search_string="smaller assembly pressure", confidence=1.0)
    results = await engine.kwargs["retrieve_fn"](query)
    assert results == [chunk]
    assert calls == [("smaller assembly pressure", 10)]
    assert "target" in session.state.evidence_pool[chunk.chunk_id].scores_by_subquery
    assert session.retrieval_events[-1]["trigger"] == "late_constraint"
    manager.end(session.session_id)
    assert list(engine.kwargs["pool"].chunks()) == []


@pytest.mark.asyncio
async def test_live_presentation_uses_existing_claim_graph_without_generation(monkeypatch):
    from slrag.synth.config import load_synth_config
    config = load_synth_config()
    config["generator"]["backend"] = "extractive"
    real_engine = synthesis.SynthesisEngine
    monkeypatch.setattr(synthesis, "SynthesisEngine",
                        lambda sid, **kwargs: real_engine(sid, config=config, **kwargs))
    monkeypatch.setattr(ws_server, "get_bus", lambda: Bus())
    session = ws_server.SessionManager().create("presentation-heldout")
    engine = session.synthesis_engine
    chunk = RetrievedChunk(chunk_id="pump-1", doc_id="manual", section_id="limits",
                           citation_label=make_label("manual", "limits"), text="Operating pressure is 12 bar.", score=0.8)
    engine.graph.register_evidence([chunk])
    with engine.graph.revise() as revision:
        revision.add(facet="limits", text=chunk.text, citations=[chunk.citation_label])
    previous_ids = [claim.claim_id for claim in engine.graph.active()]
    session.prefix = "Repeat that in two bullets."
    socket = Socket()
    await ws_server._process_utterance_end(session, socket)
    assert "12 bar" in session.answer
    assert session.citations == [chunk.citation_label]
    assert [claim.claim_id for claim in engine.graph.active()] == previous_ids
    assert session.total_llm_calls == 0
    assert not session.retrieval_events


@pytest.mark.asyncio
async def test_live_refinement_updates_prior_claim_with_targeted_dense_evidence(monkeypatch):
    from slrag.synth.config import load_synth_config
    config = load_synth_config()
    config["generator"]["backend"] = "extractive"
    real_engine = synthesis.SynthesisEngine
    monkeypatch.setattr(synthesis, "SynthesisEngine",
                        lambda sid, **kwargs: real_engine(sid, config=config, **kwargs))
    monkeypatch.setattr(ws_server, "get_bus", lambda: Bus())
    manager = ws_server.SessionManager()
    session = manager.create("refinement-heldout")
    engine = session.synthesis_engine
    original = RetrievedChunk(chunk_id="pump-1", doc_id="manual", section_id="standard",
                              citation_label=make_label("manual", "standard"),
                              text="The assembly supports 12 bar.", score=0.9)
    revised = RetrievedChunk(chunk_id="pump-2", doc_id="manual", section_id="reinforced",
                             citation_label=make_label("manual", "reinforced"),
                             text="The assembly supports 20 bar.", score=0.9)
    engine.graph.register_evidence([original])
    with engine.graph.revise() as revision:
        old_id = revision.add(facet="limits", text=original.text, citations=[original.citation_label],
                              preconditions={"count:bar": "12"})
    engine.session_constraints["count:bar"] = "12"
    calls = []

    async def search(query, top_k):
        calls.append((query, top_k))
        return [revised]

    monkeypatch.setattr(ws_server, "get_retriever", lambda: SimpleNamespace(search=search))
    session.prefix = "Actually, make that 20 bar."
    await ws_server._process_utterance_end(session, Socket())
    assert len(calls) == 1
    assert "20 bar" in calls[0][0]
    assert "20 bar" in session.answer
    assert old_id not in [claim.claim_id for claim in engine.graph.active()]
    assert engine.graph.version == 2
    assert session.citations == [revised.citation_label]
    manager.end(session.session_id)


@pytest.mark.asyncio
async def test_dedup_failure_does_not_dispatch_all_candidates(monkeypatch):
    from slrag.controller import cascade
    monkeypatch.setattr(ws_server, "get_bus", lambda: Bus())
    decision = SimpleNamespace(decision="RETRIEVE", reason="utterance_end", confidence=1.0, stage=0)
    monkeypatch.setattr(cascade, "RetrievalController",
                        lambda **kwargs: SimpleNamespace(process_chunk=lambda chunk: decision))
    candidate = SubIntent(intent_id="pump", facet="limits", query_nl="Assembly pressure",
                          search_string="assembly pressure")

    async def decompose(**kwargs):
        return [candidate]

    async def add_intents(*args, **kwargs):
        raise RuntimeError("dedup unavailable")

    session = ws_server.SessionManager().create("dedup-heldout")
    session._decomposer = SimpleNamespace(decompose=decompose)
    session._intent_set = SimpleNamespace(add_intents=add_intents)
    with pytest.raises(RuntimeError, match="dedup unavailable"):
        await ws_server._process_chunk(session, {"text": "Assembly pressure", "is_final": True}, Socket())
    assert session.retrieval_events == []


@pytest.mark.asyncio
async def test_fresh_live_turn_then_presentation_then_refinement(monkeypatch):
    from slrag.controller import cascade
    from slrag.synth.config import load_synth_config
    config = load_synth_config()
    config["generator"]["backend"] = "extractive"
    real_engine = synthesis.SynthesisEngine
    monkeypatch.setattr(synthesis, "SynthesisEngine",
                        lambda sid, **kwargs: real_engine(sid, config=config, **kwargs))
    monkeypatch.setattr(ws_server, "get_bus", lambda: Bus())

    def process(chunk):
        return SimpleNamespace(decision="NO_RETRIEVAL" if "Repeat" in chunk.text else "RETRIEVE",
                               reason="presentation_restructure" if "Repeat" in chunk.text else "utterance_end",
                               confidence=1.0, stage=0)

    monkeypatch.setattr(cascade, "RetrievalController",
                        lambda **kwargs: SimpleNamespace(process_chunk=process))
    manager = ws_server.SessionManager()
    session = manager.create("full-heldout")
    intent = SubIntent(intent_id="assembly", facet="limits", query_nl="Assembly for 12 bar",
                       search_string="assembly 12 bar")

    async def decompose(**kwargs):
        return [intent]

    async def add_intents(candidates, **kwargs):
        if intent.intent_id in session.state.intent_set:
            return []
        session.state.intent_set[intent.intent_id] = intent
        return [intent]

    session._decomposer = SimpleNamespace(decompose=decompose)
    from slrag.decompose.intent_set import IntentSet
    session._intent_set = SimpleNamespace(
        add_intents=add_intents, mark_dispatched=lambda iid: None,
        retire_omitted_from_final_scope=IntentSet(session.state).retire_omitted_from_final_scope,
    )
    searches = []

    async def search(query, top_k):
        searches.append(query)
        value = 20 if "20" in query else 12
        section = "reinforced" if value == 20 else "standard"
        return [RetrievedChunk(chunk_id=f"pump-{value}", doc_id="manual", section_id=section,
                               citation_label=make_label("manual", section),
                               text=f"The assembly supports {value} bar.", score=0.9)]

    monkeypatch.setattr(ws_server, "get_retriever", lambda: SimpleNamespace(search=search))
    socket = Socket()
    await ws_server._process_chunk(session, {"text": "Assembly for 12 bar", "is_final": True}, socket)
    await ws_server._process_utterance_end(session, socket)
    engine = session.synthesis_engine
    assert "12 bar" in session.answer
    initial_ids = [claim.claim_id for claim in engine.graph.active()]
    assert searches == ["assembly 12 bar"]
    await ws_server._process_chunk(session, {"text": "Repeat that in two bullets.", "is_final": True}, socket)
    await ws_server._process_utterance_end(session, socket)
    assert session.synthesis_engine is engine
    assert [claim.claim_id for claim in engine.graph.active()] == initial_ids
    assert searches == ["assembly 12 bar"]
    await ws_server._process_chunk(session, {"text": "Actually, make that 20 bar.", "is_final": True}, socket)
    await ws_server._process_utterance_end(session, socket)
    assert session.synthesis_engine is engine
    assert len(searches) == 2
    assert "20 bar" in searches[-1]
    assert "20 bar" in session.answer
    assert not set(initial_ids) & {claim.claim_id for claim in engine.graph.active()}
    assert engine.graph.version == 2
    manager.end(session.session_id)


@pytest.mark.asyncio
async def test_real_dedup_final_chunk_keeps_first_turn_answer_and_presentation(monkeypatch):
    import numpy as np
    from slrag.controller import cascade
    from slrag.decompose import intent_set
    from slrag.synth.config import load_synth_config
    from slrag.synth.generator import ExtractiveGenerator
    from slrag.synth.verifier import LexicalEntailmentScorer
    config = load_synth_config()
    real_engine = synthesis.SynthesisEngine

    def make_engine(sid, **kwargs):
        return real_engine(sid, config=config, generator=ExtractiveGenerator(config),
                           scorer=LexicalEntailmentScorer(config), **kwargs)

    monkeypatch.setattr(synthesis, "SynthesisEngine", make_engine)
    monkeypatch.setattr(ws_server, "get_bus", lambda: Bus())
    monkeypatch.setattr(intent_set, "_get_embedding_model",
                        lambda name: SimpleNamespace(encode=lambda text, **kwargs: np.array([1.0, 0.0])))

    def process(chunk):
        return SimpleNamespace(decision="NO-RETRIEVAL" if "Repeat" in chunk.text else "RETRIEVE",
                               reason="presentation_restructure" if "Repeat" in chunk.text else "utterance_end",
                               confidence=1.0, stage=0)

    monkeypatch.setattr(cascade, "RetrievalController",
                        lambda **kwargs: SimpleNamespace(process_chunk=process))
    manager = ws_server.SessionManager()
    session = manager.create("canonical-heldout")
    emitted = []

    async def decompose(**kwargs):
        candidate = SubIntent(intent_id=f"fresh-{len(emitted)}", facet="limits",
                              query_nl="Assembly pressure", search_string="assembly pressure")
        emitted.append(candidate)
        return [candidate]

    session._decomposer = SimpleNamespace(decompose=decompose)
    chunk = RetrievedChunk(chunk_id="pump-1", doc_id="manual", section_id="standard",
                           citation_label=make_label("manual", "standard"),
                           text="The assembly supports 12 bar.", score=0.9)
    searches = []

    async def search(query, top_k):
        searches.append(query)
        return [chunk]

    monkeypatch.setattr(ws_server, "get_retriever", lambda: SimpleNamespace(search=search))
    socket = Socket()
    await ws_server._process_chunk(session, {"text": "Assembly", "t_s": 0.2}, socket)
    first_id = emitted[0].intent_id
    await ws_server._process_chunk(session, {"text": " pressure", "t_s": 0.5, "is_final": True}, socket)
    assert emitted[1].intent_id == first_id
    assert not emitted[1].novel
    assert len(searches) == 1
    assert first_id in session.state.evidence_pool[chunk.chunk_id].scores_by_subquery

    reference = make_engine("reference")
    expected = await reference.handle_turn(synthesis.TurnInput(
        turn_id=1, utterance=session.prefix, t_s_end=0.5,
        sub_intents=(emitted[0],), evidence={first_id: [chunk]}))
    await ws_server._process_utterance_end(session, socket)
    assert session.answer == expected.output.answer
    assert session.claims
    assert session.citations == [chunk.citation_label]
    engine = session.synthesis_engine
    initial_ids = [claim.claim_id for claim in engine.graph.active()]
    await ws_server._process_chunk(session, {"text": "Repeat that in two bullets.", "is_final": True}, socket)
    await ws_server._process_utterance_end(session, socket)
    assert session.synthesis_engine is engine
    assert [claim.claim_id for claim in engine.graph.active()] == initial_ids
    assert session.citations == [chunk.citation_label]
    assert len(searches) == 1
    assert session.total_llm_calls == 0
    manager.end(session.session_id)
