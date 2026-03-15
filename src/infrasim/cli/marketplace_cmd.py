"""CLI commands for the Chaos Experiment Marketplace."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.table import Table

from infrasim.cli.main import app, console


@app.command("marketplace")
def marketplace(
    action: str = typer.Argument(
        ..., help="Action: list | publish | download | rate"
    ),
    target: str = typer.Argument(
        default="", help="Manifest ID or scenario JSON path"
    ),
    category: str = typer.Option("", "--category", "-c", help="Filter by category"),
    domain: str = typer.Option("", "--domain", help="Filter by domain"),
    query: str = typer.Option("", "--query", "-q", help="Search query"),
    score: int = typer.Option(0, "--score", help="Rating score (1-5)"),
    comment: str = typer.Option("", "--comment", help="Rating comment"),
    author: str = typer.Option("anonymous", "--author", help="Author name"),
    top: int = typer.Option(0, "--top", "-n", help="Show top N rated"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Chaos Experiment Marketplace — browse, share, and rate chaos scenarios.

    Examples:
        # List all scenarios
        faultray marketplace list

        # List database scenarios
        faultray marketplace list --category database

        # Search by keyword
        faultray marketplace list --query "traffic spike"

        # Show top 5 rated scenarios
        faultray marketplace list --top 5

        # Publish a scenario
        faultray marketplace publish scenario.json

        # Download a scenario
        faultray marketplace download abc123

        # Rate a scenario
        faultray marketplace rate abc123 --score 5 --comment "Great scenario"
    """
    from infrasim.marketplace import ScenarioManifest, ScenarioMarketplace

    mp = ScenarioMarketplace()

    if action == "list":
        if top > 0:
            results = mp.top_rated(n=top)
        else:
            results = mp.search(query=query, category=category, domain=domain)

        if json_output:
            console.print_json(data=[m.to_dict() for m in results])
            return

        if not results:
            console.print("[yellow]No scenarios found.[/]")
            return

        table = Table(title="Chaos Experiment Marketplace", show_header=True)
        table.add_column("ID", style="cyan", width=14)
        table.add_column("Name", width=25)
        table.add_column("Category", width=12)
        table.add_column("Domain", width=12)
        table.add_column("Author", width=14)
        table.add_column("Rating", justify="right", width=8)
        table.add_column("Downloads", justify="right", width=10)

        for m in results:
            rating_str = f"{m.average_rating:.1f}" if m.ratings else "N/A"
            table.add_row(
                m.id[:12],
                m.name,
                m.category,
                m.domain,
                m.author,
                rating_str,
                str(m.downloads),
            )
        console.print(table)

    elif action == "publish":
        if not target:
            console.print("[red]Please provide a scenario JSON file path.[/]")
            raise typer.Exit(1)

        path = Path(target)
        if not path.exists():
            console.print(f"[red]File not found: {path}[/]")
            raise typer.Exit(1)

        data = json.loads(path.read_text(encoding="utf-8"))
        manifest = ScenarioManifest.from_dict(data)
        mid = mp.publish(manifest)
        console.print(f"[green]Published scenario '{manifest.name}' with ID: {mid}[/]")

    elif action == "download":
        if not target:
            console.print("[red]Please provide a manifest ID.[/]")
            raise typer.Exit(1)

        try:
            manifest = mp.download(target)
        except FileNotFoundError:
            console.print(f"[red]Manifest not found: {target}[/]")
            raise typer.Exit(1)

        if json_output:
            console.print_json(data=manifest.to_dict())
        else:
            console.print(f"[green]Downloaded: {manifest.name}[/]")
            console.print(f"  Category: {manifest.category}")
            console.print(f"  Domain: {manifest.domain}")
            console.print(f"  Blast radius: {manifest.blast_radius:.2f}")
            console.print(f"  Downloads: {manifest.downloads}")

    elif action == "rate":
        if not target:
            console.print("[red]Please provide a manifest ID.[/]")
            raise typer.Exit(1)
        if score < 1 or score > 5:
            console.print("[red]Score must be between 1 and 5.[/]")
            raise typer.Exit(1)

        try:
            mp.rate(target, author=author, score=score, comment=comment)
        except FileNotFoundError:
            console.print(f"[red]Manifest not found: {target}[/]")
            raise typer.Exit(1)

        console.print(f"[green]Rated scenario {target}: {score}/5[/]")

    else:
        console.print(f"[red]Unknown action: {action}. Use list|publish|download|rate[/]")
        raise typer.Exit(1)
