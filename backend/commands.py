import json
import os
from pathlib import Path
from typing import Dict, Any, Optional


def _detect_node_commands(config_files: Dict[str, str]) -> Dict[str, Optional[str]]:
    pkg = config_files.get("package.json")
    # Simplified: if package.json exists, use npm install
    pm = None
    install = None
    build = None
    start = None
    test = None

    if pkg:
        pm = "npm"
        install = "npm install"
        try:
            pj = json.loads(pkg)
            scripts = pj.get("scripts", {})
            if "build" in scripts:
                build = "npm run build"
            if "start" in scripts:
                start = "npm start"
            if "dev" in scripts:
                if not start:
                    start = "npm run dev"
            if "test" in scripts:
                test = "npm test"
        except Exception:
            pass

    return {"package_manager": pm, "install": install, "build": build, "start": start, "test": test}


def _detect_python_commands(config_files: Dict[str, str]) -> Dict[str, Optional[str]]:
    # Simplified: if requirements.txt exists, use pip install -r requirements.txt
    pyproject = config_files.get("pyproject.toml", "")
    requirements = "requirements.txt" in config_files
    pip_install = None
    start = None
    test = None

    if requirements:
        pip_install = "python -m pip install -r requirements.txt"
    else:
        if config_files.get("setup.py") or pyproject:
            pip_install = None

    # detect common run commands by simple keyword scan
    deps_text = (config_files.get("requirements.txt") or "") + pyproject
    lower = deps_text.lower()
    if "uvicorn" in lower:
        start = "uvicorn main:app --reload"
    elif "flask" in lower:
        start = "flask run --host=0.0.0.0"
    elif "gunicorn" in lower:
        start = "gunicorn app:app -b 0.0.0.0:8000"

    return {"install": pip_install, "start": start, "test": test}


def infer_commands(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Return a dict with inferred commands and a shell script content.

    Keys returned:
      - script: shell script text
      - meta: dict of detected package manager and commands
    """
    config_files = profile.get("config_files", {})
    meta: Dict[str, Any] = {}

    # check for existing node_modules in the cloned repo
    local_path = profile.get("local_path")
    node_modules_present = False
    if local_path:
        try:
            node_modules_present = Path(local_path, "node_modules").exists()
        except Exception:
            node_modules_present = False

    # expose this in meta
    meta["node_modules_present"] = node_modules_present

    # Prefer Node detection
    if "package.json" in config_files or any(k in config_files for k in ("yarn.lock", "package-lock.json", "pnpm-lock.yaml")):
        node = _detect_node_commands(config_files)
        meta.update({"type": "node", **node})
    elif "requirements.txt" in config_files or "pyproject.toml" in config_files:
        py = _detect_python_commands(config_files)
        meta.update({"type": "python", **py})
    else:
        meta.update({"type": "unknown"})

    # Detect Docker-related files and suggest docker commands
    try:
        dockerfile_present = any(Path(k).name.lower() == "dockerfile" for k in config_files)
    except Exception:
        dockerfile_present = False
    compose_present = any(Path(k).name in ("docker-compose.yml", "docker-compose.yaml") for k in config_files)

    docker_build = None
    docker_up = None
    if dockerfile_present:
        docker_build = "docker build -t app ."
        docker_up = "docker run --rm -p 8000:8000 app"
    if compose_present:
        # Prefer modern `docker compose` CLI but keep simple command suggestion
        docker_up = "docker compose up --build"

    meta.update({
        "dockerfile_present": dockerfile_present,
        "compose_present": compose_present,
        "docker_build": docker_build,
        "docker_up": docker_up,
    })

    # Build a shell script
    lines = ["#!/usr/bin/env bash", "set -e"]
    if meta.get("install"):
        lines.append("# Install dependencies")
        # If node_modules already exists, avoid reinstalling unless necessary
        if node_modules_present and meta.get("type") == "node":
            lines.append("echo 'node_modules exists — skipping install (remove node_modules to reinstall)'")
        else:
            lines.append(meta["install"])
    if meta.get("build"):
        lines.append("\n# Build")
        lines.append(meta["build"])
    if meta.get("start"):
        lines.append("\n# Start")
        lines.append(meta["start"])
    else:
        # If no start found, prefer docker compose when present, otherwise suggest Dockerfile build/run
        if meta.get("compose_present"):
            lines.append("\n# Start with docker compose")
            lines.append(meta.get("docker_up") or "docker compose up --build")
        elif meta.get("dockerfile_present"):
            lines.append("\n# Build and run with Docker")
            if meta.get("docker_build"):
                lines.append(meta["docker_build"])
            if meta.get("docker_up"):
                lines.append(meta["docker_up"])

    script = "\n".join(lines) + "\n"
    return {"script": script, "meta": meta}
