# Commit Context: 2ab3aad — feat(synth): claim generator + synthesis/refine/present-only prompts (D2 PM)

## Metadata
- **Commit SHA**: `2ab3aadeaa92bf30691519ffeff77a408002c247` (`2ab3aad`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-22T11:34:21+05:30`
- **Branch**: `worktree-refine-ground-d1-d2`

## Commit Message
```text
feat(synth): claim generator + synthesis/refine/present-only prompts (D2 PM)

Roadmap 4.6 and S-6 layers 1–2. The only LLM call site in Component 4, and it
makes at most ONE call per turn (HC-5 budget: decompose + synthesise + optional
controller tie-break <= 3).

- The synthesis LLM emits the answer AS CLAIMS: one cited sentence each, typed
  by intent_id/facet, streamed as DraftClaim so the two-pass verifier checks
  sentence N while N+1 is consumed.
- PromptLibrary: jinja2 (StrictUndefined) over config/prompts/ — zero prompt
  text in src/ (HC-2; an ast test rejects long string literals in
  generator.py). synthesize.jinja / refine.jinja / present_only.jinja share
  one JSON output contract; the allowlist is built only from chunks in context
  (layer 1) and claims_json_schema() puts it in a citations enum so
  off-allowlist labels are undecodable under guided decoding (layer 2).
- ExtractiveGenerator (default backend): deterministic, offline, zero LLM
  calls — verbatim, relevance-filtered sentences from evidence above the score
  floor. Drives CI and the golden replay.
- LLMGenerator + OpenAICompatibleClient for local Qwen2.5-7B via
  Ollama/vLLM: stdlib urllib (no new deps), injectable transport for tests,
  tolerant parser (fences, bare list, JSON-lines, truncated output), transport
  failures degrade to zero claims (reported as uncertainty) instead of a
  crash, HC-1 guard refuses non-local endpoints unless allow_remote.

37 tests; golden Examples 1–2 draft sets reproduced without config changes.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- Component 4: Session Refinement & Corpus Grounding
- General / Infrastructure
- Tests & Verification

## File Changes
- **Added**: `config/prompts/present_only.jinja`
- **Added**: `config/prompts/refine.jinja`
- **Added**: `config/prompts/synthesize.jinja`
- **Added**: `src/slrag/synth/generator.py`
- **Added**: `tests/synth/test_generator.py`

## Diff Statistics
```text
config/prompts/present_only.jinja |  24 ++
 config/prompts/refine.jinja       |  46 ++++
 config/prompts/synthesize.jinja   |  38 +++
 src/slrag/synth/generator.py      | 557 ++++++++++++++++++++++++++++++++++++++
 tests/synth/test_generator.py     | 411 ++++++++++++++++++++++++++++
 5 files changed, 1076 insertions(+)
```

## Description & Context
Roadmap 4.6 and S-6 layers 1–2. The only LLM call site in Component 4, and it
makes at most ONE call per turn (HC-5 budget: decompose + synthesise + optional
controller tie-break <= 3).

- The synthesis LLM emits the answer AS CLAIMS: one cited sentence each, typed
  by intent_id/facet, streamed as DraftClaim so the two-pass verifier checks
  sentence N while N+1 is consumed.
- PromptLibrary: jinja2 (StrictUndefined) over config/prompts/ — zero prompt
  text in src/ (HC-2; an ast test rejects long string literals in
  generator.py). synthesize.jinja / refine.jinja / present_only.jinja share
  one JSON output contract; the allowlist is built only from chunks in context
  (layer 1) and claims_json_schema() puts it in a citations enum so
  off-allowlist labels are undecodable under guided decoding (layer 2).
- ExtractiveGenerator (default backend): deterministic, offline, zero LLM
  calls — verbatim, relevance-filtered sentences from evidence above the score
  floor. Drives CI and the golden replay.
- LLMGenerator + OpenAICompatibleClient for local Qwen2.5-7B via
  Ollama/vLLM: stdlib urllib (no new deps), injectable transport for tests,
  tolerant parser (fences, bare list, JSON-lines, truncated output), transport
  failures degrade to zero claims (reported as uncertainty) instead of a
  crash, HC-1 guard refuses non-local endpoints unless allow_remote.

37 tests; golden Examples 1–2 draft sets reproduced without config changes.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
