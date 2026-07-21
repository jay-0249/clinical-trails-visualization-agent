# ClinicalTrials.gov Query-to-Visualization Agent

FastAPI backend that turns a natural-language question about clinical trials into a
structured **visualization specification**, backed by the ClinicalTrials.gov API v2.
A two-LLM pipeline interprets the query (Stage 1) and chooses the visualization
(Stage 4); deterministic code does all data retrieval and aggregation in between.

> **Minimal stub** — full request/response schema docs, design writeup, and
> tradeoffs to follow.

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Configure

```bash
cp .env.example .env
# then set OPENAI_API_KEY in .env
```

`.env` also selects the per-stage OpenAI models (`LLM_MODEL_QUERY_ANALYZER`,
`LLM_MODEL_VIZ_GENERATOR`, ...) and the CT.gov / pipeline limits.

## Run

```bash
uvicorn app.main:app --port 8000
```

```bash
# health
curl http://localhost:8000/health

# query
curl -X POST http://localhost:8000/api/v1/query \
  -H 'content-type: application/json' \
  -d '{"query": "How are Pembrolizumab trials distributed across phases?"}'
```

## Tests

```bash
pytest tests/            # hermetic, offline (default)
pytest -m integration    # live: needs OPENAI_API_KEY + network
```

## Examples

`examples/` contains 5 real query→response runs (phase distribution, time trend,
comparison, geographic, sponsor-drug network).

## Docs

- `docs/DESIGN.md` — architecture and data models
- `docs/DECISIONS.md` — design decisions (Chose / Over / Because / Tradeoff)
- `docs/PROBLEM_STATEMENT.md` — the assignment
