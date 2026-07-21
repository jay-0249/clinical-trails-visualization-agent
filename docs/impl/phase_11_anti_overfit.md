# Phase 11: Anti-Overfit Gate

**File to create:** `tests/test_anti_overfit.py`

**Reference:** `tests/test_anti_overfit.md` (cases 6.1-6.10, 5.1-5.8, 7.1-7.4)

---

## Purpose

This phase is a **gate**, not a feature. It proves the system is generic: a set
of queries that are **not** in the problem-statement examples must each produce a
valid response **without any code change**.

> **The rule:** if making any of these queries work requires editing pipeline
> code (adding a branch, a field mapping, a special case), the system is
> **overfit** — stop and fix the generality, don't special-case the query.

A "valid response" means the endpoint returns either:
- **200** with `visualizations[]` (each a valid `VisualizationSpec` — a
  `type_category` in the 7-value set and a `data` list), **or**
- a **handled** structured error (400/422 with a `detail` body) for a query that
  is genuinely ambiguous or invalid.

What must NOT happen: an unhandled exception (500 from an unexpected crash), or a
query that only works after touching pipeline code.

---

## Anti-Overfit Queries (6.1-6.10)

These are integration tests (real ClinicalTrials.gov API + real LLM). Use a small
`max_studies` to keep them light — coverage, not data completeness, is the point.

| #    | Query                                                              | Exercises                          |
| ---- | ------------------------------------------------------------------ | ---------------------------------- |
| 6.1  | "How are Trastuzumab trials distributed across phases?"            | unfamiliar drug, same pipeline     |
| 6.2  | "Show trial trends for Crohn's disease since 2010"                 | temporal, no condition-specific path |
| 6.3  | "Enrollment distribution for Phase 3 cancer trials"               | distribution, raw_records          |
| 6.4  | "Sponsor types over time for diabetes"                            | matrix (heatmap)                   |
| 6.5  | "Break down breast cancer by sponsor_class > sponsor > drug"      | hierarchical                       |
| 6.6  | "Countries with most recruiting HIV trials"                       | spatial or categorical             |
| 6.7  | "Drugs that co-occur in lymphoma combination studies"             | relational, edge_list              |
| 6.8  | "Phase 3 Pembrolizumab by phase AND geographic distribution"      | compound: 2 tasks, shared data     |
| 6.9  | `query="show me", drug_name="Pembrolizumab", input_mode="override"` | vague override — reasonable default or handled error, no crash |
| 6.10 | "Most common study types for Alzheimer's trials"                  | `group_by=study_type` (unseen field) |

**Assertion per query:** the endpoint handles it (200 with a valid viz, or a
handled 4xx). 6.9 is deliberately underspecified, so a handled 422 there is
acceptable (the Stage-1 validator rejecting a degenerate plan is the guardrail
working, not overfitting). The others should return 200 with a visualization.

## Error Handling (7.1-7.4)

| #   | Scenario                                    | Expected                          |
| --- | ------------------------------------------- | --------------------------------- |
| 7.1 | Zero API results (nonexistent drug)         | 200, empty viz, noted in metadata |
| 7.2 | Query too short `{"query": "hi"}`           | 422 (request validation)          |
| 7.3 | Invalid enum `{"trial_phase": "PHASE99"}`   | 400 with `valid_values`           |
| 7.4 | Large result truncation                     | fetches up to cap, notes limitation |

## Input Modes (5.1-5.8)

Covered hermetically by `tests/test_orchestrator.py::test_*` (query_only /
override / supplement, comparison arm-targeting, conflict logging). No live LLM
needed for those — `merge_and_validate` is pure.

---

## How to run

```bash
pytest tests/test_anti_overfit.py -m integration -v
```

Deselected from the default hermetic suite (they hit the live API + LLM). If any
6.x query fails to be handled, diagnose whether it needs a *code change*: if yes,
the fix belongs in the generic pipeline (prompt, validator, aggregator), never a
per-query branch.
