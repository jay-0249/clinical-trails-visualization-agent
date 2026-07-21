# CLAUDE.md (Project Root — Rules File)

This is the SHORT file that goes at the project root as `CLAUDE.md`. Claude Code reads it on every turn. Keep it under 60 lines.

---

```markdown
# CLAUDE.md

## Rules

1. **NO OVERFITTING.** No hardcoded drug names, conditions, query phrases, enum values, or if/elif routing to specific viz types in pipeline code. Build generic.
2. **LOG DECISIONS.** Every implementation decision goes in `docs/DECISIONS.md` with: Chose, Over, Because, Tradeoff.
3. **ASK BEFORE FIXING.** When tests fail: report what broke, diagnose why, propose fix, STOP and ASK. Never auto-correct.
4. **TEST EVERYTHING.** Run `pytest tests/ -v` after every phase. All previous tests must keep passing.

## Execution

Follow `docs/PLANNING.md` phase by phase. At each phase, read only `docs/impl/phase_N_*.md` for that phase. After each phase, complete the Due Diligence Protocol in PLANNING.md, then report and ask permission.

## Docs (read in order at Phase 0)

1. `docs/PROBLEM_STATEMENT.md` — assignment and grading
2. `docs/DESIGN.md` — architecture overview (~200 lines)
3. `docs/API_REFERENCE.md` — ClinicalTrials.gov API endpoints and response structure
4. `docs/PLANNING.md` — execution rail with checkpoints and due diligence
5. `tests/` — per-component test case files (read only the current phase's test file)

Read `docs/impl/phase_N_*.md` only at that phase. Prompt templates are in `app/prompts/*.py` (code files, not docs).

## Key Facts

- **API:** `https://clinicaltrials.gov/api/v2` — no key, ~50 req/min
- **Always `pageSize=1000`**, cursor pagination via `pageToken`
- **Dates are messy:** handle ISO, "January 2024", "January 15, 2024"
- **All fields can be null** — safe_get everywhere
- **`phases` is a list** — ["PHASE1", "PHASE2"] for combined
- **API versioning:** `/api/v1/` prefix, prompts versioned via comments + git
```
