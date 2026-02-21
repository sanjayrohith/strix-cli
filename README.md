# 🦉 Strix CLI & API

**Strix** is an intelligent, AI-powered tool that instantly transforms any GitHub repository into a ready-to-code development environment. By analyzing a repository's source code, Strix automatically infers its technology stack and uses AI to generate production-ready Docker configurations, spinning them up seamlessly.

---

## 🎯 Our Goal

The primary goal of Strix is to **eliminate the "it works on my machine" problem** and remove the tedious boilerplate of setting up local development environments. 

Whether you are onboarding a new developer, reviewing a pull request, or exploring an open-source project, Strix bridges the gap between raw code and a running application by automating containerization and environment configuration.

---

## ✨ Key Features

- **🧠 AI-Powered Generation**: Uses Groq (`llama-3.3-70b-versatile`) to intelligently generate `Dockerfile`, `docker-compose.dev.yml`, `.env.example`, and `PROJECT.md`.
- **🔍 Smart Repository Analysis**: Automatically clones and scans repositories to detect languages, frameworks (React, Vite, FastAPI, etc.), and exposed ports.
- **🐳 Auto-Deployment**: Automatically runs `docker compose up --build -d` and reports the exposed host ports.
- **💻 Dual Interface**: 
  - A beautiful, rich **CLI** for terminal power users.
  - A **FastAPI backend** with CORS enabled, designed to serve a React frontend.

---

## 🏗️ Architecture & Codebase Overview

The codebase is structured into two main packages: the CLI and the Backend API.

```text
StrixReady-CLI/
├── cli/
│   └── main.py          # Typer CLI entrypoint (commands: scan, gui, doctor)
├── backend/
│   ├── analyzer.py      # Git cloning & local file scanning (detects stack/ports)
│   ├── generator.py     # Groq AI integration, artifact parsing, and Docker execution
│   ├── health.py        # System and service health checks
│   ├── main.py          # FastAPI application (endpoints: /scan, /health)
│   └── utils.py         # Shared utilities (e.g., CLI color constants)
├── prompts/             # System prompts for the AI model
├── pyproject.toml       # Project metadata and dependencies
└── .env                 # Environment variables (e.g., GROQ_API_KEY)
```

### How it Works (The Pipeline)
1. **Input**: The user provides a GitHub URL and a target OS (via CLI or API).
2. **Clone & Analyze** (`analyzer.py`): Strix performs a shallow clone of the repo to a temporary directory and scans the files to build a "Profile" (languages, frameworks, configs).
3. **Generate** (`generator.py`): The profile is sent to Groq AI. The AI returns structured JSON containing the necessary Docker and environment files.
4. **Write & Run** (`generator.py`): Strix writes the generated artifacts into the cloned repository and executes `docker compose up --build -d`.
5. **Output**: The exposed ports and running status are returned to the user or frontend.

---

## 🚀 Getting Started

### Prerequisites
- **Python 3.13+**
- **Docker & Docker Compose**
- **Git**
- **Groq API Key**

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/StrixReady-CLI.git
   cd StrixReady-CLI
   ```

2. **Set up the virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -e .
   ```

4. **Configure Environment Variables:**
   Create a `.env` file in the root directory:
   ```env
   GROQ_API_KEY=your_groq_api_key_here
   ```

---

## 💻 Usage

### 1. Using the CLI

Scan a repository and spin it up:
```bash
strix scan https://github.com/sanjayrohith/ResQ-Desk --os linux
```

Start the API server:
```bash
strix gui --port 8000
```

Check system health:
```bash
strix doctor
```

### 2. Using the API

Start the FastAPI server:
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

**Endpoint:** `POST /scan`
```json
// Request
{
  "url": "https://github.com/sanjayrohith/ResQ-Desk",
  "os": "linux"
}

// Response
{
  "profile": { ... },
  "artifacts": {
    "Dockerfile": "...",
    "docker-compose.dev.yml": "...",
    ".env.example": "...",
    "PROJECT.md": "..."
  },
  "compose": {
    "running": true,
    "ports": [5173],
    "error": null
  }
}
```

---

## 🛠️ Future Improvements & Roadmap

While Strix is fully functional, there are several areas for enhancement:

1. **Testing Suite**: Implement comprehensive unit and integration tests using `pytest`, including mocks for the Groq API and Docker subprocesses.
2. **Cleanup Mechanism**: Add a routine to clean up temporary cloned directories (`/tmp/strix_*`) after a session ends or a container is spun down.
3. **Multi-LLM Support**: Abstract the AI generation layer to support OpenAI, Anthropic, or local models (like Ollama) as fallbacks to Groq.
4. **Advanced Health Checks**: Upgrade `health.py` to actively monitor the health status of the spun-up Docker containers, rather than just the Strix API.
5. **Monorepo Support**: Enhance the `analyzer.py` to detect and handle monorepos, generating multi-service compose files accordingly.
6. **WebSocket Streaming**: Stream the AI generation and Docker build logs back to the React frontend in real-time via WebSockets.
