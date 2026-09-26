# Local development setup

The system has three applications and two databases:

| Component | Port | How it runs |
|---|---|---|
| PostgreSQL 18 | 5433 | Docker Compose |
| Qdrant 1.19 (vector DB) | 6333 / 6334 (localhost only) | Docker Compose |
| Python LLM/RAG service (`Manage Data/municipal_rag`) | 127.0.0.1:8000 (internal) | uvicorn |
| Java gateway (`backend/`) | 8081 | Spring Boot |
| React UI (`frontend/`) | 5173 | Vite |

The browser only talks to the Java gateway. Java owns the chat sessions (ephemeral,
in memory, keyed by a UUID the browser generates) and forwards each turn plus its
history to the Python service. The Python service answers with retrieved,
cited municipal documents when a Qdrant index exists, and otherwise falls back to
plain LLM chat. It never indexes or embeds documents while running.

## 1. Secrets

Copy the template and fill in the secrets (at minimum `POSTGRES_PASSWORD` and
`OPENROUTER_API_KEY`):

```bash
cp .env.example .env        # PowerShell: Copy-Item .env.example .env
```

All components read this single root `.env`: Docker Compose, Spring Boot (via
`spring.config.import`), and the Python service (via `municipal_rag.config.load_dotenv`).
Never commit `.env`.

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
curl -s 127.0.0.1:8000/health    # {"llmConfigured": true, "ragAvailable": false}
```

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
CHAT=$(cat /proc/sys/kernel/random/uuid)
curl -s -X POST localhost:8081/api/llm/chats/$CHAT/messages \
  -H 'Content-Type: application/json' -d '{"text":"Salut! Ce poți face?"}'
```
