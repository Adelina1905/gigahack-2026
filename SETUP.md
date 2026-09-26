# Local development setup

The system has three applications and two databases:

| Component | Port | How it runs |
|---|---|---|
| PostgreSQL 18 | 5433 | Docker Compose |
| Qdrant 1.19 (vector DB) | 6333 / 6334 (localhost only) | Docker Compose |
| Python LLM/RAG service (`Manage Data/municipal_rag`) | 127.0.0.1:8000 (internal) | uvicorn |
| Java gateway (`backend/`) | 8081 | Spring Boot |
| React UI (`frontend/`) | 5173 | Vite |

The browser only talks to the Java gateway. Java stores the chats in PostgreSQL,
scoped to an anonymous per-browser cookie (there are no user accounts). It forwards
each turn plus the chat's recent history to the Python service. The user prompt is
committed first, then the answer, structured AI metadata, and ordered citations are
saved on that same turn. Python failures preserve the prompt with a retryable status.
The Python service answers with retrieved,
cited municipal documents when a Qdrant index exists, and otherwise falls back to
plain LLM chat. It never indexes or embeds documents while running.

## 1. Secrets

Copy the template and set `POSTGRES_PASSWORD`. Live AI mode also needs
`OPENROUTER_API_KEY`; demo mode does not:

```bash
cp .env.example .env        # PowerShell: Copy-Item .env.example .env
```

All components read this single root `.env`: Docker Compose, Spring Boot (via
`spring.config.import`), and the Python service (via `municipal_rag.config.load_dotenv`).
Spring Boot also imports an optional `backend/.env` (template: `backend/.env.example`),
which overrides the root one. Never commit `.env`.

Voice mode uses that same OpenRouter key. Its model defaults can be overridden:

```properties
OPENROUTER_STT_MODEL=openai/whisper-large-v3-turbo
OPENROUTER_TTS_MODEL=microsoft/mai-voice-2-flash
OPENROUTER_TTS_VOICE=en-US-Harper:MAI-Voice-2
```

The browser records only after Voice mode is enabled and the microphone is pressed.
Microphone access requires `localhost` or HTTPS. Recordings pass through Java to the
internal Python service and are never written to disk or PostgreSQL. Generated MP3s
are cached only in the current browser session.

## 2. Databases

```bash
docker compose up -d        # postgres + qdrant
docker compose ps
docker compose exec postgres psql -U smart_city_app -d smart_city -c "\dt"
curl -s localhost:6333/collections
```

```bash
docker compose down         # stop, keep data
docker compose down -v      # delete both volumes
```

Flyway creates and updates the PostgreSQL schema when the backend starts.

## 3. Python LLM/RAG service

Requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
cd "Manage Data"
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements.txt -r requirements-server.txt
.venv/bin/uvicorn --factory municipal_rag.server:create_default_app --host 127.0.0.1 --port 8000
curl -s 127.0.0.1:8000/health    # {"mode": "live", "llmConfigured": true, "ragAvailable": false}
```

On Windows, use `.venv\Scripts\python.exe` and `.venv\Scripts\uvicorn.exe`
instead of `.venv/bin/...`.

For integration work before the main AI is ready, install just
`requirements-server.txt` and explicitly select demo mode:

```powershell
$env:CHAT_MODE = "demo"
.\.venv\Scripts\uvicorn.exe --factory municipal_rag.server:create_default_app --host 127.0.0.1 --port 8000
```

On Linux/macOS, prefix the command with `CHAT_MODE=demo`. Demo mode never calls
OpenRouter or Qdrant and does not require a key. `/health` includes `mode: "demo"`,
`llmConfigured: false`, and `ragAvailable: false`. Demo replies carry `mode: "demo"`
and `status: "DEMO"`; the UI retains that label after reload. Use `CHAT_MODE=live`
and restart Python when the real chatbot is ready. Unknown mode values fail startup.
Live failures remain errors, never demo fallbacks. Health flags indicate configuration
and index availability, not that a paid model request has succeeded.

`ragAvailable` becomes `true` once the `municipal_evidence_current` alias exists in
Qdrant. Build the index offline, never while the service is serving users:

```bash
.venv/bin/python run_all.py --execute --qdrant-url http://localhost:6333
```

## 4. Java gateway

Requires JDK 25 (`sudo apt install openjdk-25-jdk-headless` on Debian).

```bash
cd backend
./mvnw spring-boot:run      # Windows: .\mvnw.cmd spring-boot:run
```

## 5. Frontend

```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173
```

## Smoke test

```bash
CHAT=$(curl -s -c /tmp/jar -b /tmp/jar -X POST localhost:8081/api/chats \
  -H 'Content-Type: application/json' -d '{}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
curl -s -c /tmp/jar -b /tmp/jar -X POST localhost:8081/api/chats/$CHAT/responses \
  -H 'Content-Type: application/json' -d '{"text":"Salut! Ce poți face?"}'
```

After setting `OPENROUTER_API_KEY`, transcription can be checked through Java:

```bash
curl -b /tmp/jar -c /tmp/jar -F "audio=@sample.webm;type=audio/webm" \
  localhost:8081/api/voice/transcriptions
```

This call spends OpenRouter credits. Automated tests mock the provider and never use
the configured key.

## Durable chat API

The browser uses Java's `/api/chats` endpoints, with `credentials: include` for
the anonymous ownership cookie. Use the same cookie when reopening a chat.
The older `/api/llm/chats` route is an ephemeral diagnostic API, not the application
chat API. Python `/v1/chat` remains internal and does not write to PostgreSQL.

- `POST /api/chats`: `{name?, requestId?}`. A browser-generated UUID deduplicates
  creation, including after a lost HTTP response or a later rename.
- `POST /api/chats/{chatId}/responses`: `{text, requestId?}`. Text is trimmed and
  must contain 1–8,000 characters. Reuse the UUID after an uncertain network result.
  Reusing it with different text returns `409 REQUEST_CONFLICT`.
- Response views retain the existing fields and add `requestId`, `generationStatus`
  (`PENDING`, `COMPLETED`, `FAILED`), `generationVersion`, `errorCode`, and `aiReply`.
  `aiReply` preserves Python's answer, mode/status, exact citation quotes and order,
  source identifiers, and clarification choices. `text` is null before a first answer.
- A new turn returns `201` even if AI fails: the prompt was saved, and clients must
  inspect `generationStatus`. Replays return `200`, or `202` while still pending.
  Replaying a failed submission does not call the model again.
- `PUT /api/chats/{chatId}/responses/{responseId}` retries or regenerates in place.
  Send `{requestId, expectedGenerationVersion}` with a new operation UUID and the
  version from the saved response. Reuse that operation UUID after network failure.
  Stale versions return `409 STALE_GENERATION`. Legacy empty-body calls remain supported
  but cannot provide operation-level retry deduplication.
- Only one generation per chat is accepted at once; another gets `409 CHAT_BUSY`.
  The UI retains its unsent draft. Different chats can generate independently.
- Pending generations expire after five minutes. Startup and 30-second recovery
  checks mark expired attempts `FAILED / GENERATION_INTERRUPTED`; users explicitly
  retry them. Late completions cannot overwrite a newer attempt or resurrect a deleted chat.

GET history includes pending and failed turns. The active UI polls every two seconds
while awaiting a response. IndexedDB retains unsent drafts and operation IDs, but
acknowledged server history is authoritative. Failed regeneration keeps the previous
answer and citations. Links accept only HTTP(S); absent or invalid URLs show plain titles.

Vite proxies `/api` to Java. `VITE_API_BASE_URL=/api` is the recommended local setting;
an existing frontend `.env` can override it. Java permits both `localhost:5173` and
`127.0.0.1:5173` by default; an explicit `FRONTEND_ORIGINS` overrides those defaults.

## Tests without touching application data

Python server tests use controlled AI/RAG services and do not spend API credits:

```powershell
Set-Location "Manage Data"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_server.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_chat_service.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_rag_service.py
```

For Java database tests, create a separate PostgreSQL database whose name ends in
`_test` or `_integration`. These tests commit data and must never target an application
database. Configure its credentials in the process environment:

```powershell
$env:CHAT_TEST_JDBC_URL = "jdbc:postgresql://127.0.0.1:55433/chat_integration"
$env:CHAT_TEST_DB_USERNAME = "chat_test"
# Set CHAT_TEST_DB_PASSWORD to the dedicated database's password if required.
Set-Location backend
.\mvnw.cmd test
```

Without `CHAT_TEST_JDBC_URL`, database tests are explicitly skipped; unit tests still
run. Test configuration does not import application `.env` files. Database tests cover
committed pending prompts, concurrency, idempotency, metadata, expiry, stale writes,
ownership, and deletion. In `frontend`, run `npm test`, `npm run typecheck`,
`npm run lint`, and `npm run build`.
