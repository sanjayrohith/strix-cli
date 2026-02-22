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
        "generate production-ready artifacts and an explicit set of install/build/run commands. "
        "Return your answer as a single JSON object with the following keys: \n"
        '  "Dockerfile", "docker-compose.dev.yml", ".env.example", "PROJECT.md", "RUN_COMMANDS.sh", "commands.json"\n'
        "Each value must be the full file content as a string. The RUN_COMMANDS.sh must be a POSIX shell script with idempotent install steps, and commands.json must contain explicit install/build/start/dev/test entries (or null)."
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
    # Short summaries of important config files (package.json, Dockerfile, compose)
    config_files = profile.get("config_files", {})
    config_summaries = []
    for fname, content in config_files.items():
        snippet = content[:1600] + ("\n... (truncated)" if len(content) > 1600 else "")
        config_summaries.append((fname, snippet))

    # Heuristic signals for the model
    has_package = "package.json" in config_files
    has_py = "requirements.txt" in config_files or "pyproject.toml" in config_files
    has_dockerfile = any(Path(n).name.lower() == "dockerfile" for n in config_files)
    has_compose = any(Path(n).name in ("docker-compose.yml", "docker-compose.yaml") for n in config_files)
    ports = profile.get("ports", [])

    # Detect whether this repo is a frontend (vite/react) by scanning package.json scripts / deps
    is_frontend = False
    if has_package:
        try:
            pj = json.loads(config_files.get("package.json", "{}"))
            scripts = pj.get("scripts", {})
            deps = {**pj.get("dependencies", {}), **pj.get("devDependencies", {})}
            if any(k in deps for k in ("vite", "react", "@vitejs/plugin-react", "next")):
                is_frontend = True
        except Exception:
            is_frontend = False

    # Build a structured user prompt that includes explicit metadata and any existing Dockerfiles
    cfg_text = "\n".join([f"--- {n} ---\n{c}" for n, c in config_summaries])

    return (
        f"Repository: {profile.get('name', 'N/A')}\n"
        f"Description: {profile.get('description', 'N/A')}\n"
        f"Target OS: {profile.get('os', 'linux')}\n"
        f"Languages: {json.dumps(profile.get('languages', {}))}\n"
        f"Detected frameworks: {profile.get('frameworks', [])}\n"
        f"Detected ports: {ports}\n"
        f"Is frontend (vite/react): {is_frontend}\n"
        f"Has package.json: {has_package}\n"
        f"Has python requirements/pyproject: {has_py}\n"
        f"Has Dockerfile: {has_dockerfile}\n"
        f"Has docker-compose: {has_compose}\n"
        f"Local clone path: {profile.get('local_path', 'N/A')}\n"
        f"Default branch: {profile.get('default_branch', 'main')}\n\n"
        f"--- README (excerpt) ---\n{readme}\n\n"
        f"--- Config files (snippets) ---\n{cfg_text}\n\n"
        "Guidance for the AI:\n"
        "- Prefer multi-stage Dockerfiles. For a frontend build (Vite/React), produce a builder stage that runs `npm ci` and `npm run build` and a runtime stage that serves the build output with `nginx:alpine`.\n"
        "- CRITICAL: For nginx-based frontends, ALWAYS expose port 80 (standard HTTP), NOT the dev server port (5173 for Vite, 3000 for React). The detected port is ONLY for development mode.\n"
        "- CRITICAL: When using nginx, ensure the Dockerfile includes: COPY nginx.conf /etc/nginx/conf.d/default.conf\n"
        "- CRITICAL: Do NOT use USER directive in nginx Dockerfiles. nginx must run as root (it drops privileges automatically).\n"
        "- For application containers (Node.js backends, Python apps), create a non-root runtime user.\n"
        "- Do NOT copy full `node_modules` from the build stage into the runtime. If using a Node runtime, install only production deps in runtime or use `npm ci --omit=dev`.\n"
        "- For backend (FastAPI) prefer a Python multi-stage build with a venv and run with Gunicorn+Uvicorn workers in production.\n"
        "- Include a comprehensive `.dockerignore` file and `nginx.conf` when serving static assets.\n"
        "- Provide both `docker-compose.dev.yml` (mount source, use hot-reload command with --host 0.0.0.0 for Vite, preserve container node_modules) and `docker-compose.yml` (production using built image).\n"
        "- Add `HEALTHCHECK` entries using wget (not curl, as Alpine doesn't include curl by default).\n"
        "- For nginx.conf, include SPA routing support: try_files $uri $uri/ /index.html;\n"
        "- If an existing Dockerfile or compose file is present, produce an improved version and a short `PROJECT.md` section called `AI_CHANGES` that lists exactly what you changed and why.\n"
        "- Return ONLY a single JSON object with keys: `Dockerfile`, `docker-compose.dev.yml`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `nginx.conf` (if applicable), `PROJECT.md`, `RUN_COMMANDS.sh`, and `commands.json`. Each value must be the complete file content as a string.\n"
    )


def _validate_and_fix_artifacts(artifacts: Dict[str, str], profile: Dict[str, Any]) -> Dict[str, str]:
    """Validate and auto-fix common AI mistakes in generated artifacts."""
    
    # Fix 1: Ensure nginx.conf is copied in Dockerfile
    if "nginx.conf" in artifacts and "Dockerfile" in artifacts:
        dockerfile = artifacts["Dockerfile"]
        if "nginx:alpine" in dockerfile and "COPY nginx.conf" not in dockerfile:
            # Insert COPY instruction after FROM nginx:alpine
            lines = dockerfile.split("\n")
            new_lines = []
            for line in lines:
                new_lines.append(line)
                if "FROM nginx:alpine" in line:
                    new_lines.append("COPY nginx.conf /etc/nginx/conf.d/default.conf")
            artifacts["Dockerfile"] = "\n".join(new_lines)
            print(f"{colors.YELLOW}  [AUTO-FIX] Added COPY nginx.conf to Dockerfile{colors.END}")
    
    # Fix 2: Remove USER directive from nginx containers
    if "Dockerfile" in artifacts:
        dockerfile = artifacts["Dockerfile"]
        if "nginx:alpine" in dockerfile and "USER " in dockerfile:
            lines = dockerfile.split("\n")
            filtered_lines = []
            for line in lines:
                if not line.strip().startswith("USER ") or "USER root" in line:
                    filtered_lines.append(line)
                else:
                    print(f"{colors.YELLOW}  [AUTO-FIX] Removed '{line.strip()}' from nginx Dockerfile{colors.END}")
            artifacts["Dockerfile"] = "\n".join(filtered_lines)
    
    # Fix 3: Ensure Vite dev command has --host 0.0.0.0
    if "docker-compose.dev.yml" in artifacts:
        compose = artifacts["docker-compose.dev.yml"]
        frameworks = profile.get("frameworks", [])
        if "Vite" in frameworks or "React" in frameworks:
            if "npm run dev" in compose and "--host 0.0.0.0" not in compose:
                compose = compose.replace("npm run dev", "npm run dev -- --host 0.0.0.0")
                artifacts["docker-compose.dev.yml"] = compose
                print(f"{colors.YELLOW}  [AUTO-FIX] Added --host 0.0.0.0 to Vite dev command{colors.END}")
    
    # Fix 4: Replace curl with wget in healthchecks (Alpine doesn't have curl)
    if "Dockerfile" in artifacts:
        dockerfile = artifacts["Dockerfile"]
        if "curl --fail" in dockerfile or "curl -f" in dockerfile:
            dockerfile = dockerfile.replace("curl --fail", "wget --no-verbose --tries=1 --spider")
            dockerfile = dockerfile.replace("curl -f", "wget --no-verbose --tries=1 --spider")
            artifacts["Dockerfile"] = dockerfile
            print(f"{colors.YELLOW}  [AUTO-FIX] Replaced curl with wget in healthcheck{colors.END}")
    
    # Fix 5: Ensure nginx listens on port 80, not dev port
    if "nginx.conf" in artifacts:
        nginx_conf = artifacts["nginx.conf"]
        # Check for wrong ports (5173 for Vite, 3000 for React/Next)
        if "listen 5173" in nginx_conf or "listen 3000" in nginx_conf:
            nginx_conf = re.sub(r"listen \d+;", "listen 80;", nginx_conf)
            artifacts["nginx.conf"] = nginx_conf
            print(f"{colors.YELLOW}  [AUTO-FIX] Changed nginx listen port to 80{colors.END}")
    
    # Fix 6: Ensure Dockerfile exposes port 80 for nginx, not dev port
    if "Dockerfile" in artifacts:
        dockerfile = artifacts["Dockerfile"]
        if "nginx:alpine" in dockerfile:
            if "EXPOSE 5173" in dockerfile or "EXPOSE 3000" in dockerfile:
                dockerfile = re.sub(r"EXPOSE \d+", "EXPOSE 80", dockerfile)
                artifacts["Dockerfile"] = dockerfile
                print(f"{colors.YELLOW}  [AUTO-FIX] Changed EXPOSE port to 80 in nginx Dockerfile{colors.END}")
    
    # Fix 7: Add SPA routing to nginx.conf if missing
    if "nginx.conf" in artifacts:
        nginx_conf = artifacts["nginx.conf"]
        if "try_files" not in nginx_conf and "location /" in nginx_conf:
            # Insert try_files after location /
            nginx_conf = nginx_conf.replace(
                "location / {",
                "location / {\n        try_files $uri $uri/ /index.html;"
            )
            artifacts["nginx.conf"] = nginx_conf
            print(f"{colors.YELLOW}  [AUTO-FIX] Added SPA routing (try_files) to nginx.conf{colors.END}")
        
        # Ensure root and index directives are present
        if "root /usr/share/nginx/html" not in nginx_conf:
            # Add root and index after server_name
            nginx_conf = nginx_conf.replace(
                "server_name localhost;",
                "server_name localhost;\n    \n    root /usr/share/nginx/html;\n    index index.html;"
            )
            artifacts["nginx.conf"] = nginx_conf
            print(f"{colors.YELLOW}  [AUTO-FIX] Added root and index directives to nginx.conf{colors.END}")
    
    # Fix 8: Ensure compose files use version 3.8
    for compose_file in ["docker-compose.dev.yml", "docker-compose.yml"]:
        if compose_file in artifacts:
            compose = artifacts[compose_file]
            if "version:" in compose and "version: '3.8'" not in compose:
                compose = re.sub(r"version:\s*['\"]?\d+(\.\d+)?['\"]?", "version: '3.8'", compose)
                artifacts[compose_file] = compose
                print(f"{colors.YELLOW}  [AUTO-FIX] Updated {compose_file} to version 3.8{colors.END}")
    
    return artifacts


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
                # Validate and auto-fix common mistakes
                print(f"{colors.CYAN}Validating and fixing generated artifacts...{colors.END}")
                artifacts = _validate_and_fix_artifacts(artifacts, profile)
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
