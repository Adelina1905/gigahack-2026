# Local development setup

## Database

The project uses PostgreSQL 18 through Docker Compose. Database files are kept
in the Docker volume `gigahack-postgres18-data`, not in the repository.

### First-time setup

Copy the environment template and choose a local password:

```powershell
Copy-Item .env.example .env
```

Start PostgreSQL from the repository root:

```powershell
docker compose up -d
docker compose ps
```

### Run the backend

From the `backend` directory, load the database settings from `.env` and start
Spring Boot:

```powershell
Get-Content ..\.env | ForEach-Object {
    if ($_ -match '^([^#][^=]*)=(.*)$') {
        Set-Item -Path "Env:$($matches[1])" -Value $matches[2]
    }
}
.\mvnw.cmd spring-boot:run
```

Flyway creates and updates the database schema automatically when the backend
starts.

### Verify the database

From the repository root:

```powershell
docker compose exec postgres psql -U smart_city_app -d smart_city -c "\dt"
```

### Common commands

```powershell
docker compose up -d       # Start PostgreSQL
docker compose down        # Stop PostgreSQL and keep its data
docker compose logs postgres
docker compose down -v     # Delete the local database volume
```

Never commit `.env`. Only `.env.example` belongs in Git.
