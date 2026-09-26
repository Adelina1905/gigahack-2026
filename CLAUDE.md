# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Smart-city municipal Q&A assistant (hackathon project) for Chișinău. Request flow:

```
React UI (:5173) ──► Java gateway (:8081) ──► Python LLM/RAG service (127.0.0.1:8000) ──► OpenRouter
                         │                          │
                     PostgreSQL (:5433)         Qdrant (:6333)
```

- The **Java backend is the gateway** and owns session state. LLM chats are ephemeral: the browser generates a chat UUID, and Java keeps that chat's history in memory (TTL eviction, bounded length) and sends it with each turn.
- The **Python service** answers with cited municipal documents when a Qdrant index exists (`municipal_rag.answering.answer`, RAG v3). When there's no index, or the RAG returns NOT_FOUND/UNAVAILABLE, it falls back to plain LLM chat. It **must never ingest/embed documents while serving**; indexing is an offline `run_all.py` job.
- All components read the single root `.env` (template: `.env.example`). Setup details are in `SETUP.md`.
- The team develops on Windows (docs use PowerShell, `mvnw.cmd`, `npm.cmd`); on Linux use `./mvnw` and `npm`. Port 8080 is often taken locally, which is why the backend defaults to 8081.

## Components and commands

### Databases (repo root)
```
docker compose up -d        # postgres:5433 + qdrant:6333 (localhost only)
docker compose down -v      # wipe volumes
```

### Python LLM/RAG service + data pipeline (`Manage Data/`)
```
uv venv --python 3.13 .venv && uv pip install --python .venv/bin/python -r requirements.txt -r requirements-server.txt
.venv/bin/uvicorn --factory municipal_rag.server:create_default_app --host 127.0.0.1 --port 8000
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m unittest tests.test_chat_service.<TestClass>.<test_method>
.venv/bin/python run_all.py --execute --qdrant-url http://localhost:6333   # offline indexing
```
- Service wiring is dependency-injected: `server.create_app(chat_service, rag, llm_configured)`; `create_default_app()` builds the real `QdrantRagService` + `OpenRouterChatModel` + `ChatService`. Routing logic (RAG vs LLM fallback) lives in `chat_service.ChatService`. Tests pass hand-written implementations; **don't monkeypatch**.
- HTTP contract: `POST /v1/chat {chatId, message, history[{role,content}]}` → `{mode, status, answer, citations[{title,url,exactQuote,documentId}], clarificationChoices}`; 503 `{detail}` when the LLM is unavailable; `GET /health` → `{llmConfigured, ragAvailable}`.
- RAG v3 config (models, thresholds, Qdrant aliases `municipal_evidence_current` / `municipal_catalog_current`) is in `config/rag.v3.json`; OpenRouter calls go through `municipal_rag/api.py` (`request_json` handles retries).
- Pipeline: numbered stages (`python NN_*.py --help`) emit JSON on stdout; `run_pipeline.py` chains 1–6, `run_corpus_pipeline.py` runs a corpus, `run_all.py` = corpus pipeline + `prepare_ai_database.py` (embeddings + Qdrant import + alias publish). The corpus (`Original Data/municipal_corpus`, `chisinau-corpus-*`) and generated `data/` stages are git-ignored.
- Pipeline invariants to preserve: outputs are content-addressed (SHA-256 suffix) and never overwritten; `citationText` is exact source wording (never cite `searchText`); facts are deterministic extractions; incomplete provenance goes to review, never production; format-specific logic lives only in stage 2; the corpus is Romanian (questions may be RO or RU).

### Java gateway (`backend/`): Spring Boot 4.1, Java 25, Maven
```
./mvnw spring-boot:run            # reads ../.env via spring.config.import; listens on SERVER_PORT (8081)
./mvnw test                       # BackendApplicationTests needs Postgres running
./mvnw test -Dtest=ClassName#method
```
- Packages are per feature (`Chat`, `Response`, `Document`, `Llm`), each with Controller → Service → (Repository), `dto/` records, and `exceptions/` with `@ResponseStatus`.
- `Llm` package: `POST /api/llm/chats/{chatId}/messages {text}` and `DELETE /api/llm/chats/{chatId}`. `LlmChatService` depends on the `LlmGateway` interface (implemented by `LlmServiceClient` over `RestClient`); history lives in `LlmSessionStore` and is only appended after a successful call. Settings are under `app.llm.*` in `application.yaml`.
- The older DB-backed endpoints (`/api/chats`, `/api/chats/{id}/responses`, `/api/documents`) remain; they scope rows by the `smart_city_client_id` cookie (`AnonymousClientCookie`). `AiResponseProvider` now delegates to `LlmGateway` without history.
- The schema is owned by Flyway (`db/migration/V*__*.sql`) with `ddl-auto: validate`, so entity changes need a new migration.
- `SecurityConfig` permits everything and allows credentialed CORS only from `app.frontend-origin` (default `http://localhost:5173`).

### Frontend (`frontend/`): React 19 + Vite + Tailwind v4, mixed JSX/TS
```
npm install
npm run dev | lint | typecheck | build
```
- Single page: `App.jsx` → `pages/Playground.tsx` → `hooks/useChat.ts`, which generates the chat UUID and calls `sendLlmMessage` in `src/api/client.ts` (base `VITE_API_BASE_URL`, default `http://localhost:8081/api`).
- `src/api/datasetServices.ts` and `hooks/useMockChat.ts` are legacy/mock paths.

### Other Python prototypes
- `test.py` (root): standalone FastAPI + Ollama prototype, not used by the system.
- `src/tesseract_convertor.py`: batch OCR of `src/tesseract_Images_To_Convert/` into `src/teeseract_Converted_Text/` (the misspelled folder name is existing).

## Repo gotchas
- A Windows `.venv/` is committed at the repo root. Don't use it; the Linux venv is `Manage Data/.venv` (git-ignored).
- `README.md` is UTF-16 encoded.
- `frontend/.env` is committed and holds only non-secret settings.
