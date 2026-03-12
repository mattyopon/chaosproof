"""CLI interface for InfraSim."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console

from infrasim.discovery.scanner import scan_local
from infrasim.model.graph import InfraGraph
from infrasim.reporter.report import print_infrastructure_summary, print_simulation_report
from infrasim.simulator.engine import SimulationEngine

app = typer.Typer(
    name="infrasim",
    help="Virtual infrastructure chaos engineering simulator",
    no_args_is_help=True,
)
console = Console()

DEFAULT_MODEL_PATH = Path("infrasim-model.json")


@app.command()
def scan(
    output: Path = typer.Option(DEFAULT_MODEL_PATH, "--output", "-o", help="Output model file path"),
    hostname: str | None = typer.Option(None, "--hostname", help="Override hostname"),
    prometheus_url: str | None = typer.Option(
        None, "--prometheus-url", help="Prometheus server URL (e.g. http://localhost:9090)"
    ),
) -> None:
    """Scan local system and build infrastructure model."""
    if prometheus_url:
        from infrasim.discovery.prometheus import PrometheusClient

        console.print(f"[cyan]Discovering infrastructure from Prometheus at {prometheus_url}...[/]")
        client = PrometheusClient(url=prometheus_url)
        graph = asyncio.run(client.discover_components())
    else:
        console.print("[cyan]Scanning local infrastructure...[/]")
        graph = scan_local(hostname=hostname)

    print_infrastructure_summary(graph, console)

    graph.save(output)
    console.print(f"\n[green]Model saved to {output}[/]")


@app.command()
def simulate(
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path"),
    html: Path | None = typer.Option(None, "--html", help="Export HTML report to this path"),
) -> None:
    """Run chaos simulation against infrastructure model."""
    if not model.exists():
        console.print(f"[red]Model file not found: {model}[/]")
        console.print("Run [cyan]infrasim scan[/] first to create a model.")
        raise typer.Exit(1)

    console.print("[cyan]Loading infrastructure model...[/]")
    graph = InfraGraph.load(model)

    console.print(f"[cyan]Running chaos simulation ({len(graph.components)} components)...[/]")
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    print_simulation_report(report, console)

    if html:
        from infrasim.reporter.html_report import save_html_report

        save_html_report(report, graph, html)
        console.print(f"\n[green]HTML report saved to {html}[/]")


@app.command()
def show(
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path"),
) -> None:
    """Show infrastructure model summary."""
    if not model.exists():
        console.print(f"[red]Model file not found: {model}[/]")
        raise typer.Exit(1)

    graph = InfraGraph.load(model)
    print_infrastructure_summary(graph, console)

    console.print("\n[bold]Components:[/]")
    for comp in graph.components.values():
        deps = graph.get_dependencies(comp.id)
        dep_str = f" -> {', '.join(d.name for d in deps)}" if deps else ""
        util = comp.utilization()
        if util > 80:
            util_color = "red"
        elif util > 60:
            util_color = "yellow"
        else:
            util_color = "green"
        console.print(
            f"  [{util_color}]{comp.name}[/] ({comp.type.value}) "
            f"[dim]replicas={comp.replicas} util={util:.0f}%{dep_str}[/]"
        )


@app.command()
def load(
    yaml_file: Path = typer.Argument(..., help="Path to YAML infrastructure definition"),
    output: Path = typer.Option(DEFAULT_MODEL_PATH, "--output", "-o", help="Output model file path"),
) -> None:
    """Load infrastructure model from a YAML file."""
    from infrasim.model.loader import load_yaml

    console.print(f"[cyan]Loading infrastructure from {yaml_file}...[/]")

    try:
        graph = load_yaml(yaml_file)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)
    except ValueError as exc:
        console.print(f"[red]Invalid YAML: {exc}[/]")
        raise typer.Exit(1)

    print_infrastructure_summary(graph, console)

    graph.save(output)
    console.print(f"\n[green]Model saved to {output}[/]")


@app.command()
def tf_import(
    tf_state: Path = typer.Option(
        None, "--state", "-s", help="Path to terraform.tfstate file"
    ),
    tf_dir: Path = typer.Option(
        None, "--dir", "-d", help="Terraform project directory (runs 'terraform show -json')"
    ),
    output: Path = typer.Option(DEFAULT_MODEL_PATH, "--output", "-o", help="Output model file path"),
) -> None:
    """Import infrastructure from Terraform state."""
    from infrasim.discovery.terraform import load_tf_state_cmd, load_tf_state_file

    if tf_state:
        console.print(f"[cyan]Importing from Terraform state file: {tf_state}...[/]")
        graph = load_tf_state_file(tf_state)
    elif tf_dir:
        console.print(f"[cyan]Running 'terraform show -json' in {tf_dir}...[/]")
        try:
            graph = load_tf_state_cmd(tf_dir)
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(1)
    else:
        console.print("[cyan]Running 'terraform show -json' in current directory...[/]")
        try:
            graph = load_tf_state_cmd()
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(1)

    print_infrastructure_summary(graph, console)

    graph.save(output)
    console.print(f"\n[green]Model saved to {output}[/]")
    console.print(f"Run [cyan]infrasim simulate -m {output}[/] to analyze risks.")


@app.command()
def tf_plan(
    plan_file: Path = typer.Argument(..., help="Path to Terraform plan file (terraform plan -out=plan.out)"),
    tf_dir: Path = typer.Option(
        None, "--dir", "-d", help="Terraform project directory"
    ),
    html: Path | None = typer.Option(None, "--html", help="Export HTML report to this path"),
) -> None:
    """Analyze a Terraform plan for change impact and cascade risks.

    Usage:
      terraform plan -out=plan.out
      infrasim tf-plan plan.out
    """
    from infrasim.discovery.terraform import load_tf_plan_cmd

    console.print(f"[cyan]Analyzing Terraform plan: {plan_file}...[/]")

    try:
        result = load_tf_plan_cmd(plan_file=plan_file, tf_dir=tf_dir)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)

    changes = result["changes"]
    after_graph = result["after"]

    # Show changes
    if changes:
        console.print(f"\n[bold]Terraform Changes ({len(changes)}):[/]\n")
        from rich.table import Table

        table = Table(show_header=True)
        table.add_column("Risk", style="bold", width=6)
        table.add_column("Action", width=10)
        table.add_column("Resource", style="cyan")
        table.add_column("Changed Attributes")

        for change in changes:
            risk = change["risk_level"]
            if risk >= 8:
                risk_str = f"[bold red]{risk}/10[/]"
            elif risk >= 5:
                risk_str = f"[yellow]{risk}/10[/]"
            else:
                risk_str = f"[green]{risk}/10[/]"

            actions = "+".join(change["actions"])
            attrs = ", ".join(
                f"{a['attribute']}: {a['before']} → {a['after']}"
                for a in change["changed_attributes"][:3]
            )
            if len(change["changed_attributes"]) > 3:
                attrs += f" (+{len(change['changed_attributes']) - 3} more)"

            table.add_row(risk_str, actions, change["address"], attrs)

        console.print(table)
    else:
        console.print("[green]No changes detected in plan.[/]")
        return

    # Run simulation on the "after" state
    if len(after_graph.components) > 0:
        console.print(f"\n[cyan]Simulating chaos on planned infrastructure ({len(after_graph.components)} components)...[/]")
        engine = SimulationEngine(after_graph)
        sim_report = engine.run_all_defaults()
        print_simulation_report(sim_report, console)

        if html:
            from infrasim.reporter.html_report import save_html_report

            save_html_report(sim_report, after_graph, html)
            console.print(f"\n[green]HTML report saved to {html}[/]")


@app.command()
def report(
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path"),
    output: Path = typer.Option(Path("report.html"), "--output", "-o", help="Output HTML file path"),
) -> None:
    """Generate an HTML report from a saved model (runs simulation automatically)."""
    from infrasim.reporter.html_report import save_html_report

    if not model.exists():
        console.print(f"[red]Model file not found: {model}[/]")
        console.print("Run [cyan]infrasim scan[/] or [cyan]infrasim load[/] first.")
        raise typer.Exit(1)

    console.print("[cyan]Loading infrastructure model...[/]")
    graph = InfraGraph.load(model)

    console.print(f"[cyan]Running chaos simulation ({len(graph.components)} components)...[/]")
    engine = SimulationEngine(graph)
    sim_report = engine.run_all_defaults()

    print_simulation_report(sim_report, console)

    save_html_report(sim_report, graph, output)
    console.print(f"\n[green]HTML report saved to {output}[/]")


@app.command()
def serve(
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path"),
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host"),
    port: int = typer.Option(8080, "--port", "-p", help="Bind port"),
) -> None:
    """Launch web dashboard."""
    import uvicorn

    from infrasim.api.server import set_graph

    if model.exists():
        console.print(f"[cyan]Loading model from {model}...[/]")
        graph = InfraGraph.load(model)
        set_graph(graph)
    else:
        console.print("[yellow]No model file found. Visit /demo in the browser to load demo data.[/]")

    console.print(f"[green]Starting InfraSim dashboard at http://{host}:{port}[/]")
    uvicorn.run("infrasim.api.server:app", host=host, port=port, log_level="info")


@app.command()
def demo(
    web: bool = typer.Option(False, "--web", "-w", help="Launch web dashboard after building demo"),
    host: str = typer.Option("0.0.0.0", "--host", help="Web dashboard bind host"),
    port: int = typer.Option(8080, "--port", "-p", help="Web dashboard bind port"),
) -> None:
    """Run simulation with a demo infrastructure (no scanning required)."""
    from infrasim.model.demo import create_demo_graph

    console.print("[cyan]Building demo infrastructure...[/]")

    graph = create_demo_graph()

    # Show infrastructure
    print_infrastructure_summary(graph, console)

    # Run simulation
    console.print("\n[cyan]Running chaos simulation...[/]")
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    print_simulation_report(report, console)

    # Launch web dashboard if requested
    if web:
        import uvicorn

        from infrasim.api.server import set_graph

        set_graph(graph)
        console.print(f"\n[green]Starting InfraSim dashboard at http://{host}:{port}[/]")
        uvicorn.run("infrasim.api.server:app", host=host, port=port, log_level="info")


# ---------------------------------------------------------------------------
# Feed commands - auto-update scenarios from security news
# ---------------------------------------------------------------------------


@app.command()
def feed_update(
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file for component-aware scenario generation"),
    timeout: float = typer.Option(15.0, "--timeout", "-t", help="HTTP timeout per feed (seconds)"),
) -> None:
    """Fetch security news feeds and generate new chaos scenarios.

    Fetches articles from security news RSS/Atom feeds, analyzes them for
    infrastructure incident patterns, and generates chaos scenarios that are
    stored locally for future simulations.
    """
    from infrasim.feeds.analyzer import analyze_articles, incidents_to_scenarios
    from infrasim.feeds.fetcher import fetch_all_feeds
    from infrasim.feeds.sources import get_enabled_sources
    from infrasim.feeds.store import save_feed_scenarios

    sources = get_enabled_sources()
    console.print(f"[cyan]Fetching {len(sources)} security news feeds...[/]")

    # Fetch all feeds
    articles = asyncio.run(fetch_all_feeds(sources, timeout=timeout))
    console.print(f"  Fetched [bold]{len(articles)}[/] articles from {len(sources)} sources")

    if not articles:
        console.print("[yellow]No articles fetched. Check network connection.[/]")
        return

    # Analyze articles for incident patterns
    console.print("[cyan]Analyzing articles for incident patterns...[/]")
    incidents = analyze_articles(articles)
    console.print(f"  Matched [bold]{len(incidents)}[/] incident patterns")

    if not incidents:
        console.print("[green]No new incident patterns detected.[/]")
        return

    # Show matched patterns
    from rich.table import Table

    table = Table(title="Detected Incident Patterns", show_header=True)
    table.add_column("Pattern", style="cyan", width=30)
    table.add_column("Source", width=20)
    table.add_column("Confidence", width=10)
    table.add_column("Keywords", style="dim")

    for inc in incidents[:20]:  # Show top 20
        conf = inc.confidence
        if conf > 0.7:
            conf_str = f"[green]{conf:.0%}[/]"
        elif conf > 0.4:
            conf_str = f"[yellow]{conf:.0%}[/]"
        else:
            conf_str = f"[dim]{conf:.0%}[/]"

        table.add_row(
            inc.pattern.name,
            inc.article.source_name,
            conf_str,
            ", ".join(inc.matched_keywords[:3]),
        )

    console.print(table)

    # Generate scenarios
    component_ids: list[str] = []
    components = None
    if model.exists():
        graph = InfraGraph.load(model)
        component_ids = list(graph.components.keys())
        components = graph.components
        console.print(f"[cyan]Mapping to infrastructure model ({len(component_ids)} components)...[/]")
    else:
        console.print("[yellow]No model file found. Generating generic scenarios.[/]")
        component_ids = ["generic-target"]

    scenarios = incidents_to_scenarios(incidents, component_ids, components)

    # Save to store
    articles_meta = [
        {
            "title": inc.article.title,
            "link": inc.article.link,
            "source": inc.article.source_name,
            "published": inc.article.published,
            "pattern": inc.pattern.id,
            "confidence": inc.confidence,
        }
        for inc in incidents
    ]
    store_path = save_feed_scenarios(scenarios, articles_meta)

    console.print(f"\n[green]Generated {len(scenarios)} new scenarios from security feeds[/]")
    console.print(f"[dim]Store: {store_path}[/]")
    console.print(f"\nRun [cyan]infrasim simulate[/] to include feed scenarios in simulation.")


@app.command()
def feed_list() -> None:
    """Show stored feed-generated scenarios and statistics."""
    from infrasim.feeds.store import get_store_stats, load_store_raw

    stats = get_store_stats()
    raw = load_store_raw()

    if not stats["last_updated"]:
        console.print("[yellow]No feed data yet. Run [cyan]infrasim feed-update[/] first.[/]")
        return

    console.print(f"\n[bold]Feed Scenario Store[/]")
    console.print(f"  Last updated: [cyan]{stats['last_updated']}[/]")
    console.print(f"  Scenarios: [bold]{stats['scenario_count']}[/]")
    console.print(f"  Source articles: [bold]{stats['article_count']}[/]")
    console.print(f"  Store path: [dim]{stats['store_path']}[/]")

    # Show scenarios
    scenarios_data = raw.get("scenarios", [])
    if scenarios_data:
        from rich.table import Table

        table = Table(title="\nStored Scenarios", show_header=True)
        table.add_column("Name", style="cyan", width=35)
        table.add_column("Faults", width=8)
        table.add_column("Traffic", width=8)
        table.add_column("ID", style="dim", width=16)

        for s in scenarios_data:
            traffic = s.get("traffic_multiplier", 1.0)
            traffic_str = f"{traffic}x" if traffic > 1.0 else "normal"
            table.add_row(
                s["name"],
                str(len(s.get("faults", []))),
                traffic_str,
                s["id"][:16],
            )

        console.print(table)

    # Show recent articles
    articles = raw.get("articles", [])
    if articles:
        console.print(f"\n[bold]Recent Source Articles ({len(articles)}):[/]")
        for art in articles[:10]:
            conf = art.get("confidence", 0)
            console.print(
                f"  [{art.get('source', '?')}] {art.get('title', '?')[:70]} "
                f"[dim]({conf:.0%} match)[/]"
            )
        if len(articles) > 10:
            console.print(f"  [dim]... and {len(articles) - 10} more[/]")


@app.command()
def feed_sources() -> None:
    """Show configured feed sources."""
    from infrasim.feeds.sources import DEFAULT_SOURCES

    from rich.table import Table

    table = Table(title="Security News Feed Sources", show_header=True)
    table.add_column("Name", style="cyan", width=25)
    table.add_column("Type", width=6)
    table.add_column("Status", width=8)
    table.add_column("Tags", style="dim")
    table.add_column("URL", style="dim", width=50)

    for src in DEFAULT_SOURCES:
        status = "[green]ON[/]" if src.enabled else "[red]OFF[/]"
        table.add_row(
            src.name,
            src.feed_type,
            status,
            ", ".join(src.tags),
            src.url[:50],
        )

    console.print(table)
    console.print(f"\n[dim]{len(DEFAULT_SOURCES)} sources configured[/]")


@app.command()
def feed_clear() -> None:
    """Clear all stored feed-generated scenarios."""
    from infrasim.feeds.store import clear_store, get_store_stats

    stats = get_store_stats()
    if not stats["last_updated"]:
        console.print("[yellow]Store is already empty.[/]")
        return

    clear_store()
    console.print(f"[green]Cleared {stats['scenario_count']} feed scenarios.[/]")
