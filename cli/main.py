import subprocess
import tempfile
from pathlib import Path

import typer
import shlex
import json
from rich.console import Console

from backend import analyzer, generator, health, commands

app = typer.Typer()
console = Console()


@app.command()
def scan(
    github_url: str,
    os_name: str = typer.Option("linux", "--os", help="Target OS: linux, macos, windows"),
    auto_install: bool = typer.Option(False, "--auto-install", help="Run the detected install command after writing artifacts"),
):
    """Scan a GitHub repository URL, generate config files, and optionally start Docker."""

    console.print("[bold green]Starting analysis of repository:[/]", github_url)

    # 1. Clone & analyse locally
    try:
        with console.status("[bold yellow]Cloning and analysing repo..."):
            profile = analyzer.analyze_repo(github_url, user_os=os_name)
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        console.print(f"[bold red]Analysis failed:[/] {exc}")
        raise typer.Exit(code=1)

    console.print(
        f"[bold cyan]Detected languages:[/] {list(profile.get('languages', {}).keys())}  "
        f"[bold cyan]Frameworks:[/] {profile.get('frameworks', [])}"
    )

    # 2. Generate artifacts via AI
    console.print("[bold green]Generating artifacts via AI...[/]")
    with console.status("[bold yellow]Contacting Groq..."):
        artifacts = generator.generate(profile)

    # 3. Write artifacts into the cloned repo directory
    output_dir = Path(profile.get("local_path", Path.cwd() / "strix-output" / profile.get("name", "repo")))
    console.print(f"[bold blue]Writing files to {output_dir}...[/]")
    generator.write_artifacts(str(output_dir), artifacts)

    # Infer commands and write them to the output directory
    try:
        cmd_res = commands.infer_commands(profile)
        script = cmd_res.get("script", "")
        meta = cmd_res.get("meta", {})
        generator.write_artifacts(str(output_dir), {"RUN_COMMANDS.sh": script, "commands.json": json.dumps(meta, indent=2)})
        try:
            (output_dir / "RUN_COMMANDS.sh").chmod(0o755)
        except Exception:
            pass
    except Exception:
        pass

    # Optionally run install command (safe opt-in)
    if auto_install:
        try:
            install_cmd = meta.get("install") if isinstance(meta, dict) else None
            node_modules_present = meta.get("node_modules_present", False) if isinstance(meta, dict) else False
            if install_cmd:
                if node_modules_present:
                    console.print("[bold yellow]node_modules detected — skipping install.[/]")
                else:
                    console.print(f"[bold green]Running install command:[/] {install_cmd}")
                    with console.status("[bold yellow]Installing dependencies...[/]"):
                        try:
                            subprocess.run(shlex.split(install_cmd), cwd=str(output_dir), check=True)
                            console.print("[bold green]Install completed successfully.[/]")
                        except subprocess.CalledProcessError as e:
                            console.print(f"[bold red]Install failed:[/] {e}")
            else:
                console.print("[bold yellow]No install command detected; skipping auto-install.[/]")
        except Exception as e:
            console.print(f"[bold red]Auto-install error:[/] {e}")

    # 4. Run docker compose
    compose_file = output_dir / "docker-compose.dev.yml"
    if compose_file.exists():
        console.print("[bold green]Starting docker compose...[/]")
        compose_result = generator.run_compose(str(output_dir), artifacts)
        if compose_result["running"]:
            ports = compose_result["ports"]
            if ports:
                console.print(f"[bold green]Containers running on port(s):[/] {ports}")
            else:
                console.print("[bold green]Containers are running (no host ports detected).[/]")
        else:
            console.print(f"[bold red]Docker compose failed:[/] {compose_result.get('error', 'unknown error')}")

    console.print("[bold magenta]Done! Check the output in:[/]", str(output_dir))


@app.command()
def gui(port: int = 8000):
    """Start the Strix backend API (default port 8000)."""
    console.print(f"[bold green]Starting Strix API at[/] http://localhost:{port}")
    try:
        subprocess.run(
            ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", str(port), "--reload"],
            check=True,
        )
    except KeyboardInterrupt:
        console.print("\n[bold yellow]GUI stopped.[/]")
    except FileNotFoundError:
        console.print("[bold red]uvicorn not found – run: pip install uvicorn[/]")
        raise typer.Exit(code=1)


@app.command()
def doctor():
    """Check health of running application and services."""
    console.print("[bold blue]Running health checks...[/]")
    ok = health.check_all()
    if ok:
        console.print("[bold green]All systems healthy![/]")
    else:
        console.print("[bold red]Some services are unhealthy. See logs above.[/]")


if __name__ == "__main__":
    app()


def main():
    app()
