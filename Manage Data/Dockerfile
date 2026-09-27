# syntax=docker/dockerfile:1
# Serves the LLM/RAG API only; indexing stays an offline run_all.py job.
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt requirements-server.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt -r requirements-server.txt
COPY config config
COPY municipal_rag municipal_rag
# Query traces are written to data/10_traces.
RUN useradd --system app && mkdir -p data/10_traces && chown -R app data
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
CMD ["uvicorn", "--factory", "municipal_rag.server:create_default_app", "--host", "0.0.0.0", "--port", "8000"]
