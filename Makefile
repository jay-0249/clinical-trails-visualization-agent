.PHONY: test lint run test-integration

# Hermetic tests only (offline; integration deselected via pyproject addopts).
test:
	pytest tests/ -q

# Live tests: real ClinicalTrials.gov API + OpenAI (needs OPENAI_API_KEY).
test-integration:
	pytest tests/ -q -m integration

lint:
	ruff check app tests

run:
	uvicorn app.main:app --host 0.0.0.0 --port 8000
