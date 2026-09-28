import re

def patch_ws_server():
    with open('src/slrag/api/ws_server.py', 'r', encoding='utf-8') as f:
        text = f.read()

    # 1. Update session.sub_queries building in _process_chunk
    old_sub_queries = """        all_queries = [
            intent.query_nl
            for intent in session.state.intent_set.values()
        ]
        session.sub_queries = list(dict.fromkeys(all_queries))"""
    
    new_sub_queries = """        all_queries = [
            intent.query_nl
            for intent in session.state.intent_set.values()
            if intent.status.value != "superseded"
        ]
        session.sub_queries = list(dict.fromkeys(all_queries))"""
        
    text = text.replace(old_sub_queries, new_sub_queries)

    # 2. Add final reconciliation in _process_utterance_end
    # Right before SynthesisEngine is created
    
    old_engine = """    # "?"? Stage 3: Synthesis "?"?
    synthesis_telemetry = {}
    from slrag.synth.engine import SynthesisEngine, TurnInput

    engine = SynthesisEngine(session.session_id)
    from slrag.retrieve.pool import get_pool_chunks_for_intent

    turn_evidence = {
        intent.intent_id: get_pool_chunks_for_intent(session.state, intent.intent_id, top_k=10)
        for intent in session.state.intent_set.values()
    }"""
    
    new_engine = """    # "?"? Final Reconciliation ?"?"?
    # If any intent was superseded, run final_confirm decomposition
    was_superseded = any(i.status.value == "superseded" for i in session.state.intent_set.values())
    if was_superseded:
        logger.info("Running final reconciliation decomposition...")
        final_candidates = await session.decomposer.decompose(
            prefix=session.prefix,
            existing_intents=session.state.intent_set,
            ts=t_s
        )
        # Add to intent_set (will supersede anything not in final_candidates or conflicting)
        novel_final = await session.state.intent_set.add_intents(final_candidates, prefix=session.prefix)
        # Dispatch retrieval for any late-missing intents
        from slrag.retrieve.pool import add_to_pool
        # (Assuming the same mock retrieval pattern as _process_chunk)
        for intent in novel_final:
            logger.info(f"Dispatching LATE retrieval for intent: {intent.intent_id}")
            # Mock retrieval
            add_to_pool(
                session=session.state,
                chunk=None, # In real code, would await retriever
                intent_id=intent.intent_id,
                ts_stream_s=t_s,
                speculative=False
            )
            session.state.intent_set.mark_dispatched(intent.intent_id)
            
            # Emit RetrievalEvent
            re_evt = RetrievalEvent(
                event_id=_make_event_id(),
                timestamp_s=t_s,
                query=intent.search_string,
                trigger=RetrievalTrigger.final_confirm,
                sub_intent_id=intent.intent_id
            )
            session.retrieval_events.append(re_evt.model_dump())

    # Update sub_queries again after reconciliation
    all_queries = [
        intent.query_nl
        for intent in session.state.intent_set.values()
        if intent.status.value != "superseded"
    ]
    session.sub_queries = list(dict.fromkeys(all_queries))

    # "?"? Stage 3: Synthesis "?"?
    synthesis_telemetry = {}
    from slrag.synth.engine import SynthesisEngine, TurnInput

    engine = SynthesisEngine(session.session_id)
    from slrag.retrieve.pool import get_pool_chunks_for_intent

    # Exclude superseded intents from context assembly
    turn_evidence = {
        intent.intent_id: get_pool_chunks_for_intent(session.state, intent.intent_id, top_k=10)
        for intent in session.state.intent_set.values()
        if intent.status.value != "superseded"
    }"""
    
    text = text.replace(old_engine, new_engine)

    with open('src/slrag/api/ws_server.py', 'w', encoding='utf-8') as f:
        f.write(text)

patch_ws_server()
