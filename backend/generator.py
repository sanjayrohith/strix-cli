import os
import json
from pathlib import Path
from typing import Dict, Any

from dotenv import load_dotenv
from groq import Groq

from backend.utils import colors

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

# ---------------------------------------------------------------------------
# Load system prompt
# ---------------------------------------------------------------------------
_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "generate_artifacts_prompt.txt"
try:
    SYSTEM_PROMPT = _PROMPT_PATH.read_text()
except FileNotFoundError:
    SYSTEM_PROMPT = (
        "You are an expert DevOps engineer. Given a repository profile, "
        "generate a production-ready Dockerfile, a docker-compose.dev.yml for "
        "local development, a .env.example listing required environment variables, "
        "and a PROJECT.md that explains how to build and run the project.\n\n"
        "Return your answer as a JSON object with exactly four keys:\n"
        '  "Dockerfile", "docker-compose.dev.yml", ".env.example", "PROJECT.md"\n'
        "Each value must be the full file content as a string."
    )

# ---------------------------------------------------------------------------
# Groq-powered generation
# ---------------------------------------------------------------------------

def _build_user_prompt(profile: Dict[str, Any]) -> str:
    """Serialise the repo profile into a prompt the LLM can reason about."""
    MAX_README = 3000
    readme = profile.get("readme", "")
    if len(readme) > MAX_README:
        readme = readme[:MAX_README] + "\n... (truncated)"

    config_summaries = ""
    for fname, content in profile.get("config_files", {}).items():
        snippet = content[:2000] if len(content) > 2000 else content
        config_summaries += f"\n--- {fname} ---\n{snippet}\n"

    return f"""
Repository: {profile.get('name', 'N/A')}
Description: {profile.get('description', 'N/A')}
Target OS: {profile.get('os', 'linux')}
Languages: {json.dumps(profile.get('languages', {}), indent=2)}
Detected frameworks: {profile.get('frameworks', [])}
Detected ports: {profile.get('ports', [])}
Local clone path: {profile.get('local_path', 'N/A')}
Default branch: {profile.get('default_branch', 'main')}

--- README (excerpt) ---
{readme}

--- Configuration files found in repo ---
{config_summaries}
"""


def generate(profile: Dict[str, Any]) -> Dict[str, str]:
    """Send the repo profile to Groq and return generated artifacts.

    Returns a dict with keys: Dockerfile, docker-compose.dev.yml,
    .env.example, PROJECT.md.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print(f"{colors.YELLOW}GROQ_API_KEY not set – returning placeholder artifacts.{colors.END}")
        return _fallback_artifacts(profile)

    client = Groq(api_key=api_key)
    user_prompt = _build_user_prompt(profile)

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=4096,
        )
        raw = completion.choices[0].message.content or ""

        # Try to parse as JSON
        try:
            artifacts = json.loads(raw)
            if isinstance(artifacts, dict) and "Dockerfile" in artifacts:
                return artifacts
        except json.JSONDecodeError:
            pass

        # If the model didn't return valid JSON, wrap everything in PROJECT.md
        print(f"{colors.YELLOW}AI did not return structured JSON – saving raw output to PROJECT.md{colors.END}")
        return {
            "Dockerfile": "# AI could not generate a Dockerfile – see PROJECT.md\n",
            "docker-compose.dev.yml": "# AI could not generate compose – see PROJECT.md\n",
            ".env.example": "# AI could not generate env – see PROJECT.md\n",
            "PROJECT.md": raw,
        }

    except Exception as e:
        print(f"{colors.RED}Groq API error: {e}{colors.END}")
        return _fallback_artifacts(profile)


def _fallback_artifacts(profile: Dict[str, Any]) -> Dict[str, str]:
    """Deterministic placeholder artifacts when AI is unavailable."""
    name = profile.get("name", "app")
    port = profile.get("ports", [8000])[0] if profile.get("ports") else 8000

    return {
        "Dockerfile": (
            f"# Dockerfile for {name}\n"
            "FROM node:20-alpine AS build\n"
            "WORKDIR /app\n"
            "COPY package*.json ./\n"
            "RUN npm ci\n"
            "COPY . .\n"
            "RUN npm run build\n"
            f"EXPOSE {port}\n"
            'CMD ["npm", "start"]\n'
        ),
        "docker-compose.dev.yml": (
            "version: '3.8'\n"
            "services:\n"
            f"  {name}:\n"
            "    build: .\n"
            f"    ports:\n"
            f'      - "{port}:{port}"\n'
            "    volumes:\n"
            "      - .:/app\n"
            "      - /app/node_modules\n"
            "    environment:\n"
            "      - NODE_ENV=development\n"
        ),
        ".env.example": (
            f"# Environment variables for {name}\n"
            "NODE_ENV=development\n"
            f"PORT={port}\n"
        ),
        "PROJECT.md": (
            f"# {name}\n\n"
            f"{profile.get('description', '')}\n\n"
            "## Quick Start\n\n"
            "```bash\n"
            "docker compose -f docker-compose.dev.yml up --build\n"
            "```\n"
        ),
    }


# ---------------------------------------------------------------------------
# Write artifacts to disk
# ---------------------------------------------------------------------------

def write_artifacts(target_dir: str, artifacts: Dict[str, str]) -> None:
    """Write each artifact file into the target directory."""
    path = Path(target_dir)
    path.mkdir(parents=True, exist_ok=True)
    for name, content in artifacts.items():
        file_path = path / name
        file_path.write_text(content)
        print(f"{colors.GREEN}  wrote {file_path}{colors.END}")
