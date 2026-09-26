# gigahack-2026

## Start the app locally

### Prerequisites

- Docker Desktop
- Node.js and npm
- Python 3.13 and [uv](https://docs.astral.sh/uv/)
- JDK 25

### First-time setup

From the repository root, create the local environment file and add your
PostgreSQL password and OpenRouter API key:

```powershell
Copy-Item .env.example .env
```

Install the Python service dependencies:

```powershell
Set-Location "Manage Data"
uv venv --python 3.13 .venv
uv pip install --python ".venv\Scripts\python.exe" -r requirements.txt -r requirements-server.txt
Set-Location ..
```

Install the frontend dependencies:

```powershell
Set-Location frontend
npm install
Set-Location ..
```

### Run the app

Start the databases from the repository root:

```powershell
docker compose up -d
```

Then open three terminals and run one service in each.

Terminal 1 — Python LLM/RAG service:

```powershell
Set-Location "Manage Data"
.\.venv\Scripts\uvicorn.exe --factory municipal_rag.server:create_default_app --host 127.0.0.1 --port 8000
```

Terminal 2 — Java gateway:

```powershell
Set-Location backend
.\mvnw.cmd spring-boot:run
```

Terminal 3 — React frontend:

```powershell
Set-Location frontend
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

### Test chat while the AI is being prepared

Before starting Python, set `$env:CHAT_MODE = "demo"` in that terminal
(Linux/macOS: `export CHAT_MODE=demo`). Demo mode requires only
`requirements-server.txt`; it needs no AI key or Qdrant index. Keep Java and
PostgreSQL running normally and keep `VITE_USE_MOCK=false` in the frontend.
Every answer is labeled **Demo response** and is saved through the real backend.
Its example website link is explicitly a demonstration, not a supporting source.

Set `CHAT_MODE=live` and restart Python to connect the real AI. Live is the default;
an AI outage never silently switches to demo replies.

Messages are saved before generation starts. Pending and failed replies survive
reloads; **Retry** fills the same saved turn. Failed regeneration keeps the previous
answer and sources. Website links and citations remain clickable in saved chats.
See [SETUP.md](SETUP.md) for the API contract and isolated database tests.

The app uses these local endpoints:

| Component | Address |
|---|---|
| Frontend | `http://localhost:5173` |
| Java gateway | `http://localhost:8081` |
| Python service | `http://127.0.0.1:8000` |
| PostgreSQL | `localhost:5433` |
| Qdrant | `http://localhost:6333` |

To stop the databases without deleting their data, run this from the repository
root:

```powershell
docker compose down
```

For indexing, health checks, Linux/macOS commands, and other details, see
[SETUP.md](SETUP.md).
