import subprocess
import tempfile
from pathlib import Path

import typer
from rich.console import Console

from backend import analyzer, generator, health

app = typer.Typer()
console = Console()


@app.command()
def scan(
    github_url: str,
    os_name: str = typer.Option("linux", "--os", help="Target OS: linux, macos, windows"),
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
