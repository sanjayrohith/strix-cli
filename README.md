# StrixReady CLI

**Instant dev environment from any GitHub URL — run it locally or containerise it.**

Give Strix a GitHub repo link — it clones the repo, analyses the stack, and uses AI to either:

- **Run** it instantly on localhost (AI infers install + dev commands, starts the dev server)
- **Generate** production-ready Docker config files (Dockerfile, docker-compose.yml, .dockerignore, .env.example)

## How It Works

### Run (local dev)
```
GitHub URL → Clone → Analyse (package.json / requirements.txt / README)
     → AI returns install + dev commands → Execute locally → App on localhost
```

### Generate (Docker)
```
GitHub URL → Clone → Analyse → AI generates Dockerfile + docker-compose.yml
     → Files written to cloned repo → Ready to docker compose up
```

## Quick Start

```bash
# Install
pip install -e .

# Set your Groq API key
echo "GROQ_API_KEY=gsk_your_key_here" > .env

# Run a repo locally
strix scan https://github.com/owner/repo

# Start the GUI backend (React frontend on port 8080 calls this)
strix gui
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `strix scan <url>` | Clone, detect stack, install deps, run dev server locally |
| `strix scan <url> --os macos` | Specify target OS |
| `strix gui` | Start the backend API (port 8000) for the React frontend |
| `strix doctor` | Health-check running services |

## API Endpoints (for React frontend)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/scan` | **Generate** — Clone + analyse + AI generates Docker config files |
| `GET` | `/scan/stream` | **Run** — Clone + analyse + execute locally with SSE live progress |
| `POST` | `/scan/analyze` | Clone + analyse only (preview commands, no execution) |
| `POST` | `/run` | Execute commands in a given local directory |

---

### POST /scan — Docker file generation (Generate button)

**Request:**
```json
{ "url": "https://github.com/owner/repo", "os": "linux" }
```

**Response:**
```json
{
  "profile": {
    "name": "repo",
    "languages": ["TypeScript", "JavaScript"],
    "frameworks": ["Vite", "React"],
    "local_path": "/tmp/strix_.../repo"
  },
  "artifacts": {
    "Dockerfile": "FROM node:20-alpine\n...",
    "docker-compose.yml": "services:\n  repo:\n...",
    ".dockerignore": "node_modules\n.git\n...",
    ".env.example": "# API keys\nVITE_API_URL=...",
    "notes": "Single-stage Vite build. Run: docker compose up"
  },
  "written_files": [
    "/tmp/strix_.../repo/Dockerfile",
    "/tmp/strix_.../repo/docker-compose.yml",
    "/tmp/strix_.../repo/.dockerignore",
    "/tmp/strix_.../repo/.env.example"
  ],
  "local_path": "/tmp/strix_.../repo"
}
```

---

### GET /scan/stream — Local dev server with live progress (Run button)

SSE stream — each event is a JSON object:

```
GET /scan/stream?url=https://github.com/owner/repo&os=linux
```

**Events:**
```
data: {"step": "clone",       "message": "Cloning repository...",           "data": null}
data: {"step": "analyze",     "message": "Analysis complete",               "data": {...}}
data: {"step": "ai",          "message": "AI returned commands",            "data": {...}}
data: {"step": "commands",    "message": "Setup plan ready",                "data": {"install_command": "npm i", "dev_command": "npm run dev", ...}}
data: {"step": "install",     "message": "Installing dependencies: npm i",  "data": null}
data: {"step": "install",     "message": "Dependencies installed.",         "data": null}
data: {"step": "dev",         "message": "Starting dev server: npm run dev","data": null}
data: {"step": "done",        "message": "App running at http://localhost:8081", "data": {"running": true, "port": 8081, "pid": 12345}}
data: {"step": "end",         "message": "Stream complete",                 "data": null}
```

Steps: `clone` → `analyze` → `ai` → `commands` → `pre_install` → `install` → `post_install` → `dev` → `done` → `end`

---

### POST /scan/analyze — Preview only (no execution)

**Request:**
```json
{ "url": "https://github.com/owner/repo", "os": "linux" }
```

**Response:**
```json
{
  "profile": { "name": "repo", "languages": ["Python"], "frameworks": ["FastAPI"] },
  "commands": {
    "install_command": "pip install -r requirements.txt",
    "dev_command": "uvicorn main:app --reload",
    "port": 8000,
    "env_vars": { "DATABASE_URL": "" },
    "env_notes": "Set DATABASE_URL to your Postgres connection string."
  }
}
```

---

### POST /run — Execute commands in a local directory

**Request:**
```json
{
  "local_path": "/tmp/strix_.../repo",
  "commands": {
    "install_command": "npm install",
    "dev_command": "npm run dev",
    "port": 5173
  }
}
```

**Response:**
```json
{ "result": { "running": true, "port": 5173, "pid": 12345, "error": null } }
```

---

## Project Structure

```
├── cli/main.py            # Typer CLI (scan, gui, doctor)
├── backend/
│   ├── main.py            # FastAPI app (port 8000)
│   ├── analyzer.py        # Clone repo + detect stack (with on_log callbacks)
│   ├── generator.py       # AI command/Docker generation + local execution
│   ├── commands.py        # Deterministic fallback command inference
│   ├── health.py          # Health checks
│   └── utils.py           # Shared colour constants
├── prompts/
│   ├── generate_artifacts_prompt.txt  # System prompt for local dev commands (Run)
│   └── generate_docker_prompt.txt     # System prompt for Docker file generation (Generate)
├── pyproject.toml
└── .env                   # GROQ_API_KEY
```

## Requirements

- Python 3.10+
- Git
- Node.js / npm (for JS/TS projects)
- Groq API key (free at [console.groq.com](https://console.groq.com))

## License

MIT
.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload