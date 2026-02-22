# StrixReady CLI

**Instant local dev environment from any GitHub URL.**

Give Strix a GitHub repo link — it clones the repo, analyses the stack, uses AI to figure out the exact setup commands, installs dependencies, and starts the dev server locally. Zero config.

## How It Works

```
GitHub URL → Clone → Analyse (package.json / requirements.txt / README)
     → AI returns install + dev commands → Execute locally → App on localhost
```

## Quick Start

```bash
# Install
pip install -e .

# Set your Groq API key
echo "GROQ_API_KEY=gsk_your_key_here" > .env

# Scan & run any repo
strix scan https://github.com/owner/repo
```

That's it. Strix clones the repo, asks AI for the right commands, installs deps, and starts the dev server.

## CLI Commands

| Command | Description |
|---------|-------------|
| `strix scan <url>` | Clone, detect stack, install deps, run dev server |
| `strix scan <url> --os macos` | Specify target OS |
| `strix gui` | Start the backend API (port 8000) for React frontend |
| `strix doctor` | Health-check running services |

## API Endpoints (for React frontend)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/scan` | Clone + analyse + execute (full flow) |
| `POST` | `/scan/analyze` | Clone + analyse only (preview commands) |
| `POST` | `/run` | Execute commands in a given directory |

### POST /scan
```json
{ "url": "https://github.com/owner/repo", "os": "linux" }
```

### Response
```json
{
  "profile": { "name": "repo", "languages": {...}, "frameworks": [...] },
  "commands": {
    "install_command": "npm install",
    "dev_command": "npm run dev",
    "port": 5173,
    "env_vars": {},
    "env_notes": "..."
  },
  "result": { "running": true, "port": 5173, "pid": 12345 }
}
```

## Project Structure

```
├── cli/main.py           # Typer CLI (scan, gui, doctor)
├── backend/
│   ├── main.py           # FastAPI app (port 8000)
│   ├── analyzer.py       # Clone repo + detect stack
│   ├── generator.py      # AI command generation + local execution
│   ├── commands.py       # Deterministic fallback command inference
│   ├── health.py         # Health checks
│   └── utils.py          # Shared constants
├── prompts/
│   └── generate_artifacts_prompt.txt
├── pyproject.toml
└── .env                  # GROQ_API_KEY
```

## Requirements

- Python 3.10+
- Git
- Node.js / npm (for JS/TS projects)
- Groq API key (free at [console.groq.com](https://console.groq.com))

## License

MIT
