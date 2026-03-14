"""Simulate and dynamic simulation CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

from infrasim.cli.main import (
    DEFAULT_MODEL_PATH,
    InfraGraph,
    SimulationEngine,
    _print_ai_analysis,
    _print_dynamic_results,
    app,
    console,
    print_simulation_report,
)


def _dynamic_results_to_json(results: list) -> dict:
    """Convert dynamic simulation results to a JSON-serialisable dict."""
    total = len(results)
    critical = sum(1 for r in results if getattr(r, "is_critical", False))
    warning = sum(1 for r in results if getattr(r, "is_warning", False))
    passed = total - critical - warning

    scenarios = []
    for r in results:
        name = getattr(r, "scenario", None)
        name = getattr(name, "name", "unknown") if name else "unknown"
        scenarios.append({
            "name": name,
            "peak_severity": getattr(r, "peak_severity", 0.0),
            "peak_time_seconds": getattr(r, "peak_time_seconds", None),
            "recovery_time_seconds": getattr(r, "recovery_time_seconds", None),
            "is_critical": getattr(r, "is_critical", False),
            "is_warning": getattr(r, "is_warning", False),
            "autoscaling_events": len(getattr(r, "autoscaling_events", [])),
            "failover_events": len(getattr(r, "failover_events", [])),
        })

    return {
        "total": total,
        "critical": critical,
        "warning": warning,
        "passed": passed,
        "scenarios": scenarios,
    }


def _static_report_to_json(report: object) -> dict:
    """Convert a static SimulationReport to a JSON-serialisable dict."""
    results = getattr(report, "results", [])
    critical_findings = getattr(report, "critical_findings", [])
    warnings = getattr(report, "warnings", [])
    passed = getattr(report, "passed", [])

    scenarios = []
    for r in results:
        scenario = getattr(r, "scenario", None)
        scenarios.append({
            "name": getattr(scenario, "name", "unknown") if scenario else "unknown",
            "severity": getattr(r, "severity", "info"),
            "message": getattr(r, "message", ""),
        })

    return {
        "resilience_score": round(getattr(report, "resilience_score", 0.0), 1),
        "total_scenarios": len(results),
        "total_generated": getattr(report, "total_generated", len(results)),
        "was_truncated": getattr(report, "was_truncated", False),
        "critical": len(critical_findings),
        "warning": len(warnings),
        "passed": len(passed),
        "scenarios": scenarios,
    }


@app.command()
def simulate(
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path"),
    html: Path | None = typer.Option(None, "--html", help="Export HTML report to this path"),
    pdf: Path | None = typer.Option(None, "--pdf", help="Export print-ready HTML report (open in browser → Ctrl+P for PDF)"),
    md: Path | None = typer.Option(None, "--md", help="Export Markdown report to this path"),
    dynamic: bool = typer.Option(False, "--dynamic", "-d", help="Run dynamic time-stepped simulation"),
    analyze_flag: bool = typer.Option(False, "--analyze", "-a", help="Run AI analysis after simulation"),
    plugins_dir: Path | None = typer.Option(None, "--plugins-dir", help="Directory of plugin .py files to load"),
    slack_webhook: str | None = typer.Option(None, "--slack-webhook", help="Slack webhook URL for notifications"),
    pagerduty_key: str | None = typer.Option(None, "--pagerduty-key", help="PagerDuty routing key for critical alerts"),
    max_scenarios: int = typer.Option(0, "--max-scenarios", help="Max scenarios to test (0 = engine default)"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON summary"),
) -> None:
    """Run chaos simulation against infrastructure model."""
    if not model.exists():
        console.print(f"[red]Model file not found: {model}[/]")
        console.print("Run [cyan]infrasim scan[/] first to create a model.")
        raise typer.Exit(1)

    # Load plugins if a directory is specified
    if plugins_dir is not None:
        from infrasim.plugins.registry import PluginRegistry

        console.print(f"[cyan]Loading plugins from {plugins_dir}...[/]")
        PluginRegistry.load_plugins_from_dir(plugins_dir)

    if not json_output:
        console.print("[cyan]Loading infrastructure model...[/]")
    graph = InfraGraph.load(model)

    if dynamic:
        from infrasim.simulator.dynamic_engine import DynamicSimulationEngine

        if not json_output:
            console.print(f"[cyan]Running dynamic simulation ({len(graph.components)} components)...[/]")
        dyn_engine = DynamicSimulationEngine(graph)
        report = dyn_engine.run_all_dynamic_defaults()
        # report is a DynamicSimulationReport; extract .results list
        results = getattr(report, "results", report) if not isinstance(report, list) else report
        if json_output:
            console.print_json(data=_dynamic_results_to_json(results))
            return
        _print_dynamic_results(results, console)
        return

    if not json_output:
        console.print(f"[cyan]Running chaos simulation ({len(graph.components)} components)...[/]")
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults(max_scenarios=max_scenarios)

    if json_output:
        console.print_json(data=_static_report_to_json(report))
        return

    # Scenario stats
    if report.was_truncated:
        console.print(
            f"\n[yellow]\u26a0 {report.total_generated:,} scenarios generated, "
            f"truncated to {len(report.results):,}. "
            f"Use --max-scenarios to adjust.[/]"
        )
    console.print(
        f"[dim]Scenarios: {report.total_generated:,} generated, "
        f"{len(report.results):,} tested"
        + (f" ({report.total_generated - len(report.results):,} skipped)" if report.was_truncated else "")
        + "[/]"
    )

    print_simulation_report(report, console)

    if analyze_flag:
        from infrasim.ai.analyzer import InfraSimAnalyzer

        console.print("\n[cyan]Running AI analysis...[/]")
        ai_analyzer = InfraSimAnalyzer()
        ai_report = ai_analyzer.analyze(graph, report)
        _print_ai_analysis(ai_report, console)

    if html:
        from infrasim.reporter.html_report import save_html_report

        save_html_report(report, graph, html)
        console.print(f"\n[green]HTML report saved to {html}[/]")

    if pdf:
        from infrasim.reporter.pdf_report import save_pdf_ready_html

        save_pdf_ready_html(report, graph, pdf)
        console.print(f"\n[green]Print-ready HTML report saved to {pdf}[/]")
        console.print("[dim]Open in a browser and press Ctrl+P to save as PDF.[/]")

    if md:
        from infrasim.reporter.pdf_report import export_markdown

        export_markdown(report, graph, md)
        console.print(f"\n[green]Markdown report saved to {md}[/]")

    # Webhook notifications
    if slack_webhook or pagerduty_key:
        import asyncio

        from infrasim.api.server import _report_to_dict

        report_dict = _report_to_dict(report)

        async def _send_notifications():
            if slack_webhook:
                from infrasim.integrations.webhooks import send_slack_notification

                ok = await send_slack_notification(slack_webhook, report_dict)
                if ok:
                    console.print("[green]Slack notification sent.[/]")
                else:
                    console.print("[yellow]Slack notification failed.[/]")
            if pagerduty_key:
                from infrasim.integrations.webhooks import send_pagerduty_event

                ok = await send_pagerduty_event(pagerduty_key, report_dict)
                if ok:
                    console.print("[green]PagerDuty event sent.[/]")
                else:
                    console.print("[dim]PagerDuty: no critical findings, event skipped.[/]")

        try:
            asyncio.run(_send_notifications())
        except Exception as exc:
            console.print(f"[yellow]Webhook notification error: {exc}[/]")


@app.command()
def dynamic(
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path"),
    html: Path | None = typer.Option(None, "--html", help="Export HTML report to this path"),
    duration: int = typer.Option(300, "--duration", help="Simulation duration in seconds"),
    step: int = typer.Option(5, "--step", help="Time step interval in seconds"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON summary"),
) -> None:
    """Run dynamic time-stepped chaos simulation with realistic traffic patterns."""
    if not model.exists():
        console.print(f"[red]Model file not found: {model}[/]")
        console.print("Run [cyan]infrasim scan[/] first to create a model.")
        raise typer.Exit(1)

    # Validate step < duration
    if step >= duration:
        console.print("[red]Error: --step must be smaller than --duration[/]")
        raise typer.Exit(1)

    if not json_output:
        console.print("[cyan]Loading infrastructure model...[/]")
    graph = InfraGraph.load(model)

    from infrasim.simulator.dynamic_engine import DynamicSimulationEngine

    if not json_output:
        console.print(
            f"[cyan]Running dynamic simulation "
            f"({len(graph.components)} components, "
            f"duration={duration}s, step={step}s)...[/]"
        )
    engine = DynamicSimulationEngine(graph)
    report = engine.run_all_dynamic_defaults(duration=duration, step=step)
    # report is a DynamicSimulationReport; extract .results list
    results = getattr(report, "results", report) if not isinstance(report, list) else report

    if json_output:
        console.print_json(data=_dynamic_results_to_json(results))
        return

    _print_dynamic_results(results, console)

    if html:
        from infrasim.reporter.html_report import save_html_report

        save_html_report(results, graph, html)
        console.print(f"\n[green]HTML report saved to {html}[/]")
