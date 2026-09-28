import re
from slrag.core.config import get_controller_config

def patch_intent_set():
    with open('src/slrag/decompose/intent_set.py', 'r', encoding='utf-8') as f:
        text = f.read()
    
    # We replace `async def add_intents(self, new_candidates: list[SubIntent]) -> list[SubIntent]:`
    # and the whole body up to `def get_pending(self) -> list[SubIntent]:`
    
    import re
    match = re.search(r'async def add_intents.*?def get_pending', text, flags=re.DOTALL)
    if not match:
        print("Could not find add_intents")
        return
        
    replacement = """async def add_intents(self, new_candidates: list[SubIntent], prefix: str = "") -> list[SubIntent]:
        \"\"\"Add genuinely new intents to the session, returning only the novel ones.

        Implements deterministic supersession rule:
        If a candidate has the same facet as an active intent, shares >= 1 slot key,
        and has a different value, mark the older one superseded unless an additive
        marker appears in the current window.
        \"\"\"
        model = _get_embedding_model(self.embedding_model_name)
        novel_intents = []
        
        from slrag.core.config import get_controller_config
        config = get_controller_config()
        additive_markers = config.get("additive_markers", ["also", "as well", "too", "in addition", "and for"])
        
        has_additive = any(m in prefix.lower() for m in additive_markers)

        async with self._lock:
            for candidate in new_candidates:
                candidate_emb = self._get_embedding(candidate.search_string, model)
                is_duplicate = False
                
                # Check for LLM-emitted supersedes
                for old_id in candidate.supersedes:
                    if old_id in self.session.intent_set:
                        old_intent = self.session.intent_set[old_id]
                        if old_intent.status != IntentStatus.superseded:
                            old_intent.status = IntentStatus.superseded
                            old_intent.superseded_by = candidate.intent_id
                            candidate.facet = old_intent.facet  # Inherit facet

                for existing_intent in self.session.intent_set.values():
                    if existing_intent.status == IntentStatus.superseded:
                        continue
                        
                    # Deterministic Slot Conflict
                    if existing_intent.facet == candidate.facet:
                        shared_keys = set(candidate.slots.keys()) & set(existing_intent.slots.keys())
                        conflict = False
                        for k in shared_keys:
                            if candidate.slots[k] != existing_intent.slots[k]:
                                conflict = True
                                break
                                
                        if conflict:
                            if not has_additive:
                                existing_intent.status = IntentStatus.superseded
                                # candidate hasn't got an ID yet, we'll set superseded_by later
                                existing_intent.superseded_by = "pending_" + str(len(novel_intents))
                                candidate.facet = existing_intent.facet
                            continue # Don't deduplicate if conflicting, either it supersedes or both live
                    
                    # Deduplication
                    if existing_intent.facet == candidate.facet:
                        existing_emb = self._get_embedding(
                            existing_intent.search_string, model
                        )
                        sim = self._compute_similarity(candidate_emb, existing_emb)

                        if sim > self.similarity_threshold:
                            cand_nums = set(re.findall(r'\\d+', candidate.search_string))
                            exist_nums = set(re.findall(r'\\d+', existing_intent.search_string))
                            if cand_nums != exist_nums:
                                logger.info(f"Skipping dedup for changed numbers: {cand_nums} vs {exist_nums}")
                                continue

                            is_duplicate = True
                            logger.info(
                                f"Intent deduplicated (sim={sim:.3f}): "
                                f"'{candidate.search_string}' matches existing "
                                f"'{existing_intent.search_string}'"
                            )
                            break

                if not is_duplicate:
                    new_id = self._generate_intent_id()
                    candidate.intent_id = new_id
                    candidate.novel = True
                    candidate.status = IntentStatus.pending

                    self.session.intent_set[new_id] = candidate
                    novel_intents.append(candidate)
                    logger.debug(
                        f"Added novel intent: {new_id} ({candidate.search_string})"
                    )
                    
            # Fix up pending superseded_by
            for intent in self.session.intent_set.values():
                if intent.superseded_by and intent.superseded_by.startswith("pending_"):
                    idx = int(intent.superseded_by.split("_")[1])
                    if idx < len(novel_intents):
                        intent.superseded_by = novel_intents[idx].intent_id
                        
                        # Telemetry: intent_superseded
                        from slrag.telemetry.bus import get_bus
                        import time
                        from slrag.core.events import EVT_INTENT_ADDED
                        
                        bus = get_bus()
                        try:
                            # Actually we don't have a specific EVT_INTENT_SUPERSEDED in events.py, we can just emit it
                            # Instruction says "Emit an intent_superseded telemetry event with old/new ids, slot diff, and the triggering text window."
                            import asyncio
                            from slrag.api.ws_server import _emit_telemetry
                            
                            diff = {
                                "old": intent.slots,
                                "new": novel_intents[idx].slots
                            }
                            
                            te = _emit_telemetry(
                                session_id=self.session.session_id,
                                turn_id=self.session.turn_id,
                                ts_stream_s=time.time(), # approximate
                                component="intent_set",
                                event_type="intent_superseded",
                                payload={
                                    "old_id": intent.intent_id,
                                    "new_id": novel_intents[idx].intent_id,
                                    "slot_diff": diff,
                                    "text_window": prefix
                                }
                            )
                            # Create task so it doesn't block
                            asyncio.create_task(bus.emit(te))
                        except Exception as e:
                            logger.warning(f"Failed to emit intent_superseded telemetry: {e}")

        return novel_intents

    def get_pending"""
    
    text = text[:match.start()] + replacement + text[match.end()-len("def get_pending"):]
    
    with open('src/slrag/decompose/intent_set.py', 'w', encoding='utf-8') as f:
        f.write(text)

patch_intent_set()
