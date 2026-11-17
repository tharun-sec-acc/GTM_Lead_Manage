# Session Context

Updated: 2026-11-13

## Project

- Workspace: `C:\Users\SI1107\Denso\GTM_prospect_mvp`
- A local-only GTM prospecting pilot with a Next.js frontend, FastAPI backend, PostgreSQL, Redis, Celery worker/scheduler, and Docker Compose.
- See [README.md](./README.md) for setup, configuration, architecture, and limitations.

## Work completed in this session

- Checked the Compose configuration and project setup instructions.
- Docker was available. The project `.env` file was present when Compose was started; its contents were not read or printed.
- Ran `docker compose up --build -d`. All six services started: `api`, `frontend`, `db`, `redis`, `worker`, and `scheduler`.
- Verified the API health endpoint, API docs, and frontend each returned HTTP 200:
  - `http://localhost:8000/health`
  - `http://localhost:8000/docs`
  - `http://localhost:3000`
- Later ran `docker compose down`. The containers and Compose network were removed, while named database and Redis volumes were preserved. `docker compose ps` showed no containers afterward.
- No application source files or configuration files were changed in this session. This context file was added at the user's request.

## Current runtime state

The Compose services are **stopped**. Existing PostgreSQL and Redis named volumes were preserved.

From the project directory in PowerShell, start the services:

```powershell
docker compose up --build -d
```

Check status:

```powershell
docker compose ps
```

Stop the services and preserve data:

```powershell
docker compose down
```

Do not use `docker compose down -v` unless you intend to delete the named data volumes.

## Bedrock credential security

- AWS access-key credentials were pasted into the chat during this session. Their values are intentionally not recorded here.
- Treat those credentials as exposed: deactivate/rotate the access key in AWS and use a replacement through an approved private credential configuration.
- The credentials from chat were not copied into project files by the assistant. The existing `.env` contents were not inspected, so check it privately if needed.
- The project README says Bedrock is optional and requires `AWS_REGION` and `BEDROCK_MODEL_ID`, as well as credentials available inside the API and worker containers. Keep all secrets out of chat and source control.
