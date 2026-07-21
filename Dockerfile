FROM python:3.12-slim

WORKDIR /app

# Install deps first for layer caching (pandas/numpy/etc. ship wheels — no build tools needed).
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Runtime code only (tests/docs/examples are excluded via .dockerignore).
COPY app ./app

EXPOSE 8000

# Railway and most PaaS inject $PORT; default to 8000 locally.
# .env is not baked in — OPENAI_API_KEY and overrides come from the environment.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
