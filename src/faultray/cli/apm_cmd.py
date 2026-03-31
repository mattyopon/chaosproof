# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""CLI commands for FaultRay APM agent management.

Provides: install, start, stop, status, agents, metrics, alerts subcommands.
"""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import app, console

apm_app = typer.Typer(
    name="apm",
    help="APM agent — install, start, stop, and query application performance metrics",
    no_args_is_help=True,
)
app.add_typer(apm_app, name="apm")


# ---------------------------------------------------------------------------
# Agent lifecycle commands
# ---------------------------------------------------------------------------


@apm_app.command("install")
def apm_install(
    collector_url: str = typer.Option(
        "http://localhost:8080", "--collector", "-c", help="Collector server URL"
    ),
    api_key: str = typer.Option("", "--api-key", "-k", help="API key for auth"),
    config_dir: str = typer.Option(
        str(Path.home() / ".faultray"),
        "--config-dir",
        help="Directory for agent config",
    ),
    interval: int = typer.Option(15, "--interval", "-i", help="Collection interval (seconds)"),
) -> None:
    """Install the FaultRay APM agent configuration.

    Creates a configuration file and optionally a systemd service unit.

    Examples:
        faultray apm install --collector http://faultray.internal:8080
        faultray apm install --api-key sk_xxxx --interval 30
    """
    import yaml

    from faultray.apm.models import AgentConfig

    config = AgentConfig(
        collector_url=collector_url,
        api_key=api_key,
        collect_interval_seconds=interval,
        pid_file=str(Path(config_dir) / "agent.pid"),
        log_file=str(Path(config_dir) / "agent.log"),
    )

    config_path = Path(config_dir) / "agent.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.dump(config.model_dump(), default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )

    console.print(f"[green]Agent configuration written to:[/] {config_path}")
    console.print(f"[dim]Agent ID: {config.agent_id}[/]")
    console.print(f"[dim]Collector: {collector_url}[/]")
    console.print(f"[dim]Interval: {interval}s[/]")
    console.print()
    console.print("[bold]Start the agent with:[/]")
    console.print(f"  faultray apm start --config {config_path}")


@apm_app.command("start")
def apm_start(
    config: str = typer.Option(
        str(Path.home() / ".faultray" / "agent.yaml"),
        "--config",
        "-f",
        help="Path to agent config YAML",
    ),
    foreground: bool = typer.Option(False, "--foreground", "-F", help="Run in foreground"),
) -> None:
    """Start the FaultRay APM agent.

    By default starts as a background daemon. Use --foreground for debugging.

    Examples:
        faultray apm start
        faultray apm start --foreground
        faultray apm start --config /etc/faultray/agent.yaml
    """
    from faultray.apm.agent import APMAgent, load_agent_config

    agent_config = load_agent_config(config)

    # Check if already running
    pid_path = Path(agent_config.pid_file)
    if pid_path.exists():
        try:
            pid = int(pid_path.read_text().strip())
            os.kill(pid, 0)  # Check if process exists
            console.print(
                f"[yellow]Agent already running (PID {pid}). "
                f"Stop it first with: faultray apm stop[/]"
            )
            raise typer.Exit(1)
        except (OSError, ValueError):
            pid_path.unlink(missing_ok=True)

    agent = APMAgent(agent_config)

    if foreground:
        console.print(
            Panel(
                f"[bold green]FaultRay APM Agent[/]\n"
                f"ID: {agent_config.agent_id}\n"
                f"Collector: {agent_config.collector_url}\n"
                f"Interval: {agent_config.collect_interval_seconds}s\n"
                f"Press Ctrl+C to stop.",
                title="APM Agent",
            )
        )
        agent.start()
    else:
        # Fork to background
        console.print(f"[green]Starting APM agent (id={agent_config.agent_id})...[/]")
        try:
            pid = os.fork()
        except AttributeError:
            # Windows — run in foreground
            console.print("[yellow]Background mode not supported on this OS. Running in foreground.[/]")
            agent.start()
            return

        if pid > 0:
            console.print(f"[green]Agent started in background (PID {pid})[/]")
            return
        else:
            # Child process
            os.setsid()
            sys.stdin.close()
            agent.start()
            sys.exit(0)


@apm_app.command("stop")
def apm_stop(
    config: str = typer.Option(
        str(Path.home() / ".faultray" / "agent.yaml"),
        "--config",
        "-f",
        help="Path to agent config YAML",
    ),
) -> None:
    """Stop the running FaultRay APM agent.

    Examples:
        faultray apm stop
    """
    import yaml

    config_path = Path(config)
    pid_file = str(Path.home() / ".faultray" / "agent.pid")

    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        pid_file = data.get("pid_file", pid_file)

    pid_path = Path(pid_file)
    if not pid_path.exists():
        console.print("[yellow]No running agent found (PID file missing).[/]")
        raise typer.Exit(1)

    try:
        pid = int(pid_path.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        console.print(f"[green]Sent SIGTERM to agent (PID {pid})[/]")
        pid_path.unlink(missing_ok=True)
    except (OSError, ValueError) as e:
        console.print(f"[red]Could not stop agent: {e}[/]")
        pid_path.unlink(missing_ok=True)
        raise typer.Exit(1)


@apm_app.command("status")
def apm_status(
    config: str = typer.Option(
        str(Path.home() / ".faultray" / "agent.yaml"),
        "--config",
        "-f",
        help="Path to agent config YAML",
    ),
) -> None:
    """Show the status of the APM agent.

    Examples:
        faultray apm status
    """
    import yaml

    config_path = Path(config)
    pid_file = str(Path.home() / ".faultray" / "agent.pid")

    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        pid_file = data.get("pid_file", pid_file)

    pid_path = Path(pid_file)
    if not pid_path.exists():
        console.print("[yellow]Agent is not running (no PID file).[/]")
        return

    try:
        pid = int(pid_path.read_text().strip())
        os.kill(pid, 0)
        console.print(f"[green]Agent is running (PID {pid})[/]")

        if config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}
            console.print(f"  Agent ID:  {data.get('agent_id', 'unknown')}")
            console.print(f"  Collector: {data.get('collector_url', 'unknown')}")
            console.print(f"  Interval:  {data.get('collect_interval_seconds', '?')}s")
    except (OSError, ValueError):
        console.print("[red]Agent PID file exists but process is not running.[/]")
        pid_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Query commands (talk to collector API)
# ---------------------------------------------------------------------------


@apm_app.command("agents")
def apm_list_agents(
    server: str = typer.Option("http://localhost:8080", "--server", "-s", help="FaultRay server URL"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all registered APM agents.

    Examples:
        faultray apm agents
        faultray apm agents --server http://faultray:8080 --json
    """
    import httpx

    try:
        resp = httpx.get(f"{server}/api/apm/agents", timeout=10.0)
        agents = resp.json()
    except Exception as e:
        console.print(f"[red]Could not connect to server: {e}[/]")
        raise typer.Exit(1)

    if json_output:
        console.print_json(data=agents)
        return

    if not agents:
        console.print("[yellow]No agents registered.[/]")
        return

    table = Table(title="Registered APM Agents", show_header=True)
    table.add_column("Agent ID", width=14)
    table.add_column("Hostname", width=20)
    table.add_column("IP", width=15)
    table.add_column("Status", width=10, justify="center")
    table.add_column("Last Seen", width=22)
    table.add_column("OS", width=20)

    for a in agents:
        status_style = "green" if a.get("status") == "running" else "red"
        table.add_row(
            a.get("agent_id", ""),
            a.get("hostname", ""),
            a.get("ip_address", ""),
            f"[{status_style}]{a.get('status', 'unknown')}[/]",
            a.get("last_seen", "")[:19],
            a.get("os_info", ""),
        )

    console.print(table)


@apm_app.command("metrics")
def apm_metrics(
    agent_id: str = typer.Argument(..., help="Agent ID to query"),
    metric: str = typer.Option(None, "--metric", "-m", help="Specific metric name"),
    server: str = typer.Option("http://localhost:8080", "--server", "-s", help="FaultRay server URL"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Query metrics for an APM agent.

    Examples:
        faultray apm metrics agent123
        faultray apm metrics agent123 --metric cpu_percent
    """
    import httpx

    params: dict[str, str] = {}
    if metric:
        params["metric_name"] = metric

    try:
        resp = httpx.get(
            f"{server}/api/apm/agents/{agent_id}/metrics",
            params=params,
            timeout=10.0,
        )
        data = resp.json()
    except Exception as e:
        console.print(f"[red]Could not connect to server: {e}[/]")
        raise typer.Exit(1)

    if json_output:
        console.print_json(data=data)
        return

    if not data:
        console.print(f"[yellow]No metrics found for agent {agent_id}.[/]")
        return

    table = Table(title=f"Metrics for {agent_id}", show_header=True)
    table.add_column("Metric", width=25)
    table.add_column("Value", width=15, justify="right")
    table.add_column("Samples", width=10, justify="right")
    table.add_column("Bucket", width=15)

    for d in data:
        table.add_row(
            d.get("metric_name", ""),
            f"{d.get('value', 0):.2f}",
            str(d.get("sample_count", 0)),
            str(d.get("bucket_epoch", "")),
        )

    console.print(table)


@apm_app.command("alerts")
def apm_alerts(
    agent_id: str = typer.Option(None, "--agent", "-a", help="Filter by agent ID"),
    severity: str = typer.Option(None, "--severity", help="Filter by severity"),
    server: str = typer.Option("http://localhost:8080", "--server", "-s", help="FaultRay server URL"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List APM alerts.

    Examples:
        faultray apm alerts
        faultray apm alerts --severity critical
    """
    import httpx

    params: dict[str, str] = {}
    if agent_id:
        params["agent_id"] = agent_id
    if severity:
        params["severity"] = severity

    try:
        resp = httpx.get(f"{server}/api/apm/alerts", params=params, timeout=10.0)
        data = resp.json()
    except Exception as e:
        console.print(f"[red]Could not connect to server: {e}[/]")
        raise typer.Exit(1)

    if json_output:
        console.print_json(data=data)
        return

    if not data:
        console.print("[green]No alerts.[/]")
        return

    table = Table(title="APM Alerts", show_header=True)
    table.add_column("Severity", width=10, justify="center")
    table.add_column("Rule", width=18)
    table.add_column("Agent", width=14)
    table.add_column("Metric", width=18)
    table.add_column("Value", width=10, justify="right")
    table.add_column("Threshold", width=10, justify="right")
    table.add_column("Fired At", width=20)

    severity_colors = {"critical": "bold red", "warning": "yellow", "info": "blue"}

    for a in data:
        sev = a.get("severity", "info")
        color = severity_colors.get(sev, "white")
        table.add_row(
            f"[{color}]{sev.upper()}[/]",
            a.get("rule_name", ""),
            a.get("agent_id", ""),
            a.get("metric_name", ""),
            f"{a.get('metric_value', 0):.1f}",
            f"{a.get('threshold', 0):.1f}",
            a.get("fired_at", "")[:19],
        )

    console.print(table)
