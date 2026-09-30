import re

with open('src/slrag/api/ws_server.py', 'r') as f:
    content = f.read()

pattern = r'# ── Stage 2: Decompose \+ Retrieve on RETRIEVE ──.*?(?=\n# ── Utterance End → Synthesis ────────────────────────────────────────)'

replacement = """# ── Stage 2: Decompose + Retrieve on RETRIEVE ──
    if decision == ControllerDecisionType.RETRIEVE or decision == "RETRIEVE":
        await ws.send_json({"type": "retrieval_started", "t_s": t_s})

        async def _background_work(prefix_snap, ts_snap, stage_snap):
            decomp_start = time.perf_counter()
            await bus.emit(_emit_telemetry(
                session_id=session.session_id,
                turn_id=session.turn_id,
                ts_stream_s=ts_snap,
                component="decomposer",
                event_type=EVT_DECOMPOSITION_STARTED,
                payload={"prefix_len": len(prefix_snap)},
            ))

            all_candidates = await session.decomposer.decompose(
                prefix=prefix_snap,
                existing_intents=session.state.intent_set,
                ts=ts_snap,
            )

            try:
                novel_intents = await session.intent_set.add_intents(all_candidates, prefix=prefix_snap)
            except Exception as e:
                logger.warning(f"IntentSet dedup failed ({e}), treating all as novel")
                novel_intents = all_candidates

            decomp_latency_ms = (time.perf_counter() - decomp_start) * 1000

            await bus.emit(_emit_telemetry(
                session_id=session.session_id,
                turn_id=session.turn_id,
                ts_stream_s=ts_snap,
                component="decomposer",
                event_type=EVT_DECOMPOSITION_COMPLETED,
                latency_ms=round(decomp_latency_ms, 2),
                payload={
                    "total_candidates": len(all_candidates),
                    "novel_intents": len(novel_intents),
                    "existing_intents": len(session.state.intent_set),
                },
            ))

            session.current_candidates = all_candidates
            session.sub_queries = list(dict.fromkeys(intent.query_nl for intent in all_candidates))
            
            session.classification = session.engine.classify(
                utterance=prefix_snap,
                controller_decisions=session.controller_decisions,
                sub_intents=all_candidates
            )

            await ws.send_json({
                "type": "subqueries_updated",
                "t_s": ts_snap,
                "sub_queries": session.sub_queries,
                "new_intents": [
                    {"facet": i.facet, "query_nl": i.query_nl, "intent_id": i.intent_id}
                    for i in novel_intents
                ],
                "total_intents": len(session.state.intent_set),
            })

            retrieval_start = time.perf_counter()

            async def _retrieve_and_pool(intent):
                if len(session.retrieval_events) == 0:
                    trigger = "provisional"
                else:
                    trigger = "multi_intent"

                retrieval_event = {
                    "timestamp_s": ts_snap,
                    "dispatch_s": time.time(),
                    "query": intent.search_string,
                    "trigger": trigger,
                }
                session.retrieval_events.append(retrieval_event)

                retriever = get_retriever()
                retrieved_chunks = await retriever.search(intent)

                from slrag.retrieve.pool import add_to_pool
                is_speculative = (stage_snap in (2, 3))
                
                branch_id = None
                if is_speculative:
                    branch_id = f"spec_{uuid.uuid4().hex[:8]}"
                    session.state.controller.active_speculations[branch_id] = {
                        "status": "pending",
                        "retrieved_chunks": []
                    }
                    
                for chunk in retrieved_chunks:
                    if is_speculative:
                        session.state.controller.active_speculations[branch_id]["retrieved_chunks"].append(
                            chunk.model_dump()
                        )
                    add_to_pool(
                        session=session.state,
                        chunk=chunk,
                        intent_id=intent.intent_id,
                        ts_stream_s=retrieval_event["dispatch_s"],
                        speculative=is_speculative
                    )

                session.intent_set.mark_dispatched(intent.intent_id)

                await bus.emit(_emit_telemetry(
                    session_id=session.session_id,
                    turn_id=session.turn_id,
                    ts_stream_s=ts_snap,
                    component="decomposer",
                    event_type=EVT_INTENT_ADDED,
                    payload={
                        "intent_id": intent.intent_id,
                        "facet": intent.facet,
                        "query_nl": intent.query_nl,
                        "search_string": intent.search_string,
                        "trigger": trigger,
                    },
                ))

                try:
                    from slrag.telemetry.metrics import record_retrieval
                    record_retrieval(trigger, 0.0)
                except Exception:
                    pass

            if novel_intents and session.classification.turn_type != "CONSTRAINT_REFINEMENT":
                import asyncio
                await asyncio.gather(*[_retrieve_and_pool(intent) for intent in novel_intents])

            from slrag.decompose.overlap import OverlapMerger
            from slrag.core.schemas import RetrievedChunk
            overlap_merger = OverlapMerger()
            results_by_intent = {}
            for entry in session.state.evidence_pool.values():
                for i_id, score in entry.scores_by_subquery.items():
                    if i_id not in results_by_intent:
                        results_by_intent[i_id] = []
                    results_by_intent[i_id].append(
                        RetrievedChunk(
                            chunk_id=entry.chunk_id, doc_id=entry.doc_id,
                            section_id=entry.section_id, text=entry.text,
                            score=score, citation_label=entry.citation_label
                        )
                    )
            for i_id in results_by_intent:
                results_by_intent[i_id].sort(key=lambda x: x.score, reverse=True)

            merged_pairs = overlap_merger.check_all_pairs(
                session.state,
                results_by_intent,
                jaccard_threshold=0.7,
            )
            
            for kept_id, merged_id in merged_pairs:
                session.intent_set.mark_merged(merged_id, kept_id)
                kept_intent = session.state.intent_set.get(kept_id)
                merged_intent = session.state.intent_set.get(merged_id)
                for event in session.retrieval_events:
                    if kept_intent and event.get("query") == kept_intent.search_string:
                        if event.get("trigger") == "provisional":
                            event["trigger"] = "final_confirm"
                    if merged_intent and event.get("query") == merged_intent.search_string:
                        if event.get("trigger") == "provisional":
                            event["trigger"] = "final_confirm"

            retrieval_latency_ms = (time.perf_counter() - retrieval_start) * 1000

            await bus.emit(_emit_telemetry(
                session_id=session.session_id,
                turn_id=session.turn_id,
                ts_stream_s=ts_snap,
                component="retriever",
                event_type=EVT_RETRIEVAL_COMPLETED,
                latency_ms=round(retrieval_latency_ms, 2),
                payload={
                    "events_count": len(session.retrieval_events),
                    "novel_dispatched": len(novel_intents),
                },
            ))

            await ws.send_json({
                "type": "retrieval_complete",
                "t_s": ts_snap,
                "events": session.retrieval_events,
            })

        task = asyncio.create_task(_background_work(session.prefix, t_s, stage))
        session.active_tasks.add(task)
        task.add_done_callback(session.active_tasks.discard)
"""

new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

with open('src/slrag/api/ws_server.py', 'w') as f:
    f.write(new_content)
