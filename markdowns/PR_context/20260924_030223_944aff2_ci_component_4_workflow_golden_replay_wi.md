# Commit Context: 944aff2 — ci: Component 4 workflow - golden replay with G4/G5 gates, fabricated-ID assertion (D3 AM)

## Metadata
- **Commit SHA**: `944aff20dc3694185211230f59e4f3ade4b6869c` (`944aff2`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-24T03:02:23+05:30`
- **Branch**: `sivansh`

## Commit Message
```text
ci: Component 4 workflow - golden replay with G4/G5 gates, fabricated-ID assertion (D3 AM)

.github/workflows/c4-ci.yml, on pushes to sivansh/main and on PRs:
- offline: pytest, then bench.replay_c4 -> bench.metrics --gate on the lexical backend. fabricated_id_count != 0, full_corpus_searches != 0, a cleared session, citation support < 0.85 or a presentation-only turn that retrieves / adds sources fails the build.
- nli: CPU torch, the [nli,ner] extras, and models baked by scripts/bake_nli_model.py --spacy (cached by model id; never downloaded at runtime). It runs the opt-in NLI tests, the golden replay on the cross-encoder verifier gated with an independent cross-encoder judge, and the calibration report. Gate reports are uploaded as artifacts.

Every step of the nli job was run locally with the baked models: gates pass, 32/32 claims supported, 0 fabricated IDs. The workflow itself has not run on GitHub yet: pushing needs Sivansh's credentials. Matangi's harness can fold these steps into the team-wide `slrag replay` CI when it lands.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- General / Infrastructure

## File Changes
- **Added**: `.github/workflows/c4-ci.yml`

## Diff Statistics
```text
.github/workflows/c4-ci.yml | 63 +++++++++++++++++++++++++++++++++++++++++++++
 1 file changed, 63 insertions(+)
```

## Description & Context
.github/workflows/c4-ci.yml, on pushes to sivansh/main and on PRs:
- offline: pytest, then bench.replay_c4 -> bench.metrics --gate on the lexical backend. fabricated_id_count != 0, full_corpus_searches != 0, a cleared session, citation support < 0.85 or a presentation-only turn that retrieves / adds sources fails the build.
- nli: CPU torch, the [nli,ner] extras, and models baked by scripts/bake_nli_model.py --spacy (cached by model id; never downloaded at runtime). It runs the opt-in NLI tests, the golden replay on the cross-encoder verifier gated with an independent cross-encoder judge, and the calibration report. Gate reports are uploaded as artifacts.

Every step of the nli job was run locally with the baked models: gates pass, 32/32 claims supported, 0 fabricated IDs. The workflow itself has not run on GitHub yet: pushing needs Sivansh's credentials. Matangi's harness can fold these steps into the team-wide `slrag replay` CI when it lands.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
