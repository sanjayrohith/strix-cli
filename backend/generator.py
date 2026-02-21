import os
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List

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

        # Strip markdown code fences the model often wraps around JSON
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            # Remove opening fence (```json or ```)
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        # Try to parse as JSON
        try:
            artifacts = json.loads(cleaned)
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


# ---------------------------------------------------------------------------
# Extract exposed ports from docker-compose.dev.yml
# ---------------------------------------------------------------------------

def _extract_ports_from_compose(compose_content: str) -> List[int]:
    """Parse host ports from the ports: section of a compose file.

    Handles formats like:
      - "3000:3000"
      - "8080:80"
      - 3000
    Returns a list of unique host-side ports as integers.
    """
    ports: set[int] = set()
    # Match quoted or unquoted port mappings: "HOST:CONTAINER" or just "PORT"
    for match in re.finditer(r'["\']?(\d+)(?::\d+)?["\']?', compose_content):
        # Only capture from lines that look like port specs (after a dash in ports section)
        pass

    # More reliable: look for the ports block and extract mappings
    in_ports = False
    for line in compose_content.splitlines():
        stripped = line.strip()
        if stripped.startswith("ports:"):
            in_ports = True
            continue
        if in_ports:
            if stripped.startswith("-"):
                # Extract the port value
                port_str = stripped.lstrip("- ").strip().strip("'\"")
                # "HOST:CONTAINER" → take HOST; plain "PORT" → take PORT
                host_port = port_str.split(":")[0]
                try:
                    ports.add(int(host_port))
                except ValueError:
                    pass
            elif stripped and not stripped.startswith("#"):
                # We've left the ports block
                in_ports = False

    return sorted(ports)


# ---------------------------------------------------------------------------
# Run docker compose
# ---------------------------------------------------------------------------

def run_compose(target_dir: str, artifacts: Dict[str, str]) -> Dict[str, Any]:
    """Run `docker compose up --build -d` in the target directory.

    Returns a dict with:
      - running: bool
      - ports: list of host ports exposed by the compose services
      - error: optional error message
    """
    compose_file = Path(target_dir) / "docker-compose.dev.yml"
    if not compose_file.exists():
        return {"running": False, "ports": [], "error": "docker-compose.dev.yml not found"}

    # Extract ports from the compose content
    compose_content = artifacts.get("docker-compose.dev.yml", "")
    if not compose_content and compose_file.exists():
        compose_content = compose_file.read_text()
    exposed_ports = _extract_ports_from_compose(compose_content)

    # Check if docker is available
    try:
        subprocess.run(
            ["docker", "info"],
            capture_output=True, check=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return {
            "running": False,
            "ports": exposed_ports,
            "error": "Docker is not installed or not running",
        }

    # Run docker compose up
    print(f"{colors.CYAN}Running docker compose up --build -d in {target_dir}...{colors.END}")
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", "docker-compose.dev.yml", "up", "--build", "-d"],
            cwd=target_dir,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout for build
        )
        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip()
            print(f"{colors.RED}docker compose failed: {error_msg}{colors.END}")
            return {
                "running": False,
                "ports": exposed_ports,
                "error": f"docker compose failed: {error_msg}",
            }

        print(f"{colors.GREEN}docker compose up succeeded!{colors.END}")

        # If no ports were extracted from the YAML, try `docker compose port`
        if not exposed_ports:
            try:
                ps_result = subprocess.run(
                    ["docker", "compose", "-f", "docker-compose.dev.yml", "ps", "--format", "json"],
                    cwd=target_dir,
                    capture_output=True, text=True, timeout=15,
                )
                if ps_result.returncode == 0 and ps_result.stdout.strip():
                    for line in ps_result.stdout.strip().splitlines():
                        try:
                            container = json.loads(line)
                            for pub in container.get("Publishers", []):
                                if pub.get("PublishedPort"):
                                    exposed_ports.append(pub["PublishedPort"])
                        except json.JSONDecodeError:
                            pass
                    exposed_ports = sorted(set(exposed_ports))
            except subprocess.SubprocessError:
                pass

        return {
            "running": True,
            "ports": exposed_ports,
            "error": None,
        }

    except subprocess.TimeoutExpired:
        return {
            "running": False,
            "ports": exposed_ports,
            "error": "docker compose build timed out after 5 minutes",
        }
    except Exception as e:
        return {
            "running": False,
            "ports": exposed_ports,
            "error": str(e),
        }
