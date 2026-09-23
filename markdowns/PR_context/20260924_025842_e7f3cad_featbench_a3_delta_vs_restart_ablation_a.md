# Commit Context: e7f3cad — feat(bench): A3 delta-vs-restart ablation and live local-LLM latency harness (roadmap 5.5, audit I-8)

## Metadata
- **Commit SHA**: `e7f3cad4b27e370a8168a3b6106063c0ac22df2b` (`e7f3cad`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-24T02:58:42+05:30`
- **Branch**: `sivansh`

## Commit Message
```text
feat(bench): A3 delta-vs-restart ablation and live local-LLM latency harness (roadmap 5.5, audit I-8)

bench/ablate_refinement.py runs each golden refinement two ways against the same fixture evidence: the shipped delta path, and a naive restart that re-decomposes the whole conversation and re-retrieves every sub-intent. It reports retrieval calls, evidence chunks and prompt size for the real refine/synthesize templates (via LLMGenerator.render_prompt, 4 chars/token), Component 4 latency, citation continuity, lineage, and stale claims (final claims whose own text scopes them to a constraint value that no longer holds).

Results on the goldens:
- example2_refinement: 2 vs 4 retrieval calls, 2 vs 6 evidence chunks (3x); delta 0 stale claims vs restart 1 (it re-asserts the domestic-trip rule after "the trip was international"); delta keeps V1->V2 lineage.
- edge_self_correction_mixed: 3 vs 6 retrieval calls, 2 vs 4 evidence chunks.
- Whole-prompt size is only ~1.1x smaller on this tiny fixture corpus because template text dominates, and Component 4 latency is equal on the deterministic backend. The saving shows up in retrieval calls and evidence volume, not yet in a 3-5x token ratio.

bench/latency_llm.py measures first_draft_ms, first PROVISIONAL sentence, generation time, LLM calls and retractions per turn type against the configured local OpenAI-compatible server (Ollama/vLLM, SSE on or --no-stream). It exits 2 with setup instructions when no server is reachable. Not run for real here: no local model on this machine. The plumbing is tested against the repo's fake SSE transport.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- Component 4: Session Refinement & Corpus Grounding
- General / Infrastructure
- Tests & Verification

## File Changes
- **Added**: `bench/ablate_refinement.py`
- **Added**: `bench/latency_llm.py`
- **Added**: `tests/bench/test_ablation.py`
- **Added**: `tests/bench/test_latency_llm.py`

## Diff Statistics
```text
bench/ablate_refinement.py      | 207 ++++++++++++++++++++++++++++++++++++++++
 bench/latency_llm.py            | 137 ++++++++++++++++++++++++++
 tests/bench/test_ablation.py    |  18 ++++
 tests/bench/test_latency_llm.py |  55 +++++++++++
 4 files changed, 417 insertions(+)
```

## Description & Context
bench/ablate_refinement.py runs each golden refinement two ways against the same fixture evidence: the shipped delta path, and a naive restart that re-decomposes the whole conversation and re-retrieves every sub-intent. It reports retrieval calls, evidence chunks and prompt size for the real refine/synthesize templates (via LLMGenerator.render_prompt, 4 chars/token), Component 4 latency, citation continuity, lineage, and stale claims (final claims whose own text scopes them to a constraint value that no longer holds).

Results on the goldens:
- example2_refinement: 2 vs 4 retrieval calls, 2 vs 6 evidence chunks (3x); delta 0 stale claims vs restart 1 (it re-asserts the domestic-trip rule after "the trip was international"); delta keeps V1->V2 lineage.
- edge_self_correction_mixed: 3 vs 6 retrieval calls, 2 vs 4 evidence chunks.
- Whole-prompt size is only ~1.1x smaller on this tiny fixture corpus because template text dominates, and Component 4 latency is equal on the deterministic backend. The saving shows up in retrieval calls and evidence volume, not yet in a 3-5x token ratio.

bench/latency_llm.py measures first_draft_ms, first PROVISIONAL sentence, generation time, LLM calls and retractions per turn type against the configured local OpenAI-compatible server (Ollama/vLLM, SSE on or --no-stream). It exits 2 with setup instructions when no server is reachable. Not run for real here: no local model on this machine. The plumbing is tested against the repo's fake SSE transport.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
