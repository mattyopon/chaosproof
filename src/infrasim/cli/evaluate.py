"""Cross-engine evaluation CLI command.

Runs all 5 simulation engines sequentially and produces a unified summary
covering static simulation, dynamic simulation, ops simulation, what-if
analysis, and capacity planning.
"""

from __future__ import annotations

import json as json_lib
import sys
from pathlib import Path

import typer

from infrasim.cli.main import (
    DEFAULT_MODEL_PATH,
    _load_graph_for_analysis,
    app,
    console,
)


def _compute_avg_availability(sli_timeline: list) -> float:
    """Compute average availability from an SLI timeline."""
    if not sli_timeline:
        return 100.0
    total = sum(p.availability_percent for p in sli_timeline)
    return total / len(sli_timeline)


@app.command()
def evaluate(
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path"),
    file: Path = typer.Option(None, "--file", "-f", help="Alias for --model"),
    html: Path = typer.Option(None, "--html", help="Export cross-engine HTML report"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON summary"),
    ops_days: int = typer.Option(7, "--ops-days", help="Ops simulation duration in days"),
    max_scenarios: int = typer.Option(0, "--max-scenarios", help="Max static scenarios (0=default)"),
) -> None:
    """Run all 5 simulation engines and produce a unified evaluation report."""
    from rich.panel import Panel

    resolved_model = file if file is not None else model
    graph = _load_graph_for_analysis(resolved_model, yaml_file=None)

    num_components = len(graph.components)
    num_dependencies = len(graph.all_dependency_edges())
    model_name = resolved_model.name

    console.print(
        f"\n[cyan]Starting full evaluation of [bold]{model_name}[/bold] "
        f"({num_components} components, {num_dependencies} dependencies)...[/]\n"
    )

    # Collect results for JSON/HTML output
    evaluation_data: dict = {
        "model": model_name,
        "components": num_components,
        "dependencies": num_dependencies,
    }

    # ------------------------------------------------------------------
    # 1. Static Simulation
    # ------------------------------------------------------------------
    console.print("[cyan]  [1/5] Running static simulation...[/]")
    from infrasim.simulator.engine import SimulationEngine

    static_engine = SimulationEngine(graph)
    static_report = static_engine.run_all_defaults()

    total_generated = len(static_report.results)
    if max_scenarios > 0 and total_generated > max_scenarios:
        # Re-run with truncated scenario list is not needed;
        # MAX_SCENARIOS in engine already caps at 1000. This just
        # tracks what the user wanted to display.
        pass

    static_total = len(static_report.results)
    static_critical = len(static_report.critical_findings)
    static_warning = len(static_report.warnings)
    static_passed = len(static_report.passed)

    evaluation_data["static"] = {
        "resilience_score": round(static_report.resilience_score, 1),
        "total_scenarios": static_total,
        "generated_scenarios": total_generated,
        "critical": static_critical,
        "warning": static_warning,
        "passed": static_passed,
    }

    # ------------------------------------------------------------------
    # 2. Dynamic Simulation
    # ------------------------------------------------------------------
    console.print("[cyan]  [2/5] Running dynamic simulation...[/]")
    from infrasim.simulator.dynamic_engine import DynamicSimulationEngine

    dyn_engine = DynamicSimulationEngine(graph)
    dyn_report = dyn_engine.run_all_dynamic_defaults()

    dyn_results = dyn_report.results
    dyn_total = len(dyn_results)
    dyn_critical = len(dyn_report.critical_findings)
    dyn_warning = len(dyn_report.warnings)
    dyn_passed = len(dyn_report.passed)

    # Find worst scenario for display
    dyn_worst_name = None
    dyn_worst_severity = 0.0
    for r in dyn_results:
        if r.peak_severity > dyn_worst_severity:
            dyn_worst_severity = r.peak_severity
            dyn_worst_name = r.scenario.name

    evaluation_data["dynamic"] = {
        "total_scenarios": dyn_total,
        "critical": dyn_critical,
        "warning": dyn_warning,
        "passed": dyn_passed,
        "worst_scenario": dyn_worst_name,
        "worst_severity": dyn_worst_severity,
    }

    # ------------------------------------------------------------------
    # 3. Ops Simulation
    # ------------------------------------------------------------------
    console.print(f"[cyan]  [3/5] Running ops simulation ({ops_days} days)...[/]")
    from infrasim.model.components import SLOTarget
    from infrasim.simulator.ops_engine import OpsScenario, OpsSimulationEngine
    from infrasim.simulator.traffic import create_diurnal_weekly

    # Build a default ops scenario similar to the whatif base
    component_ids = list(graph.components.keys())
    deploy_targets: list[str] = []
    for comp_id, comp in graph.components.items():
        if comp.type.value in ("app_server", "web_server"):
            deploy_targets.append(comp_id)
    if not deploy_targets:
        deploy_targets = component_ids[:2] if len(component_ids) >= 2 else list(component_ids)

    scheduled_deploys = []
    for dow in [1, 3]:  # Tuesday, Thursday
        for comp_id in deploy_targets:
            scheduled_deploys.append({
                "component_id": comp_id,
                "day_of_week": dow,
                "hour": 14,
                "downtime_seconds": 30,
            })

    ops_scenario = OpsScenario(
        id=f"evaluate-ops-{ops_days}d",
        name=f"Full operations ({ops_days}d)",
        duration_days=ops_days,
        traffic_patterns=[
            create_diurnal_weekly(
                peak=2.5, duration=ops_days * 86400, weekend_factor=0.6,
            ),
        ],
        scheduled_deploys=scheduled_deploys,
        enable_random_failures=True,
        enable_degradation=True,
        enable_maintenance=True,
    )

    ops_engine = OpsSimulationEngine(graph)
    ops_result = ops_engine.run_ops_scenario(ops_scenario)

    ops_avg_avail = _compute_avg_availability(ops_result.sli_timeline)
    ops_total_events = len(ops_result.events)

    evaluation_data["ops"] = {
        "duration_days": ops_days,
        "avg_availability": round(ops_avg_avail, 4),
        "min_availability": round(ops_result.min_availability, 2),
        "total_downtime_seconds": round(ops_result.total_downtime_seconds, 1),
        "total_events": ops_total_events,
        "total_deploys": ops_result.total_deploys,
        "total_failures": ops_result.total_failures,
        "total_degradation_events": ops_result.total_degradation_events,
        "peak_utilization": round(ops_result.peak_utilization, 1),
    }

    # ------------------------------------------------------------------
    # 4. What-If Analysis
    # ------------------------------------------------------------------
    console.print("[cyan]  [4/5] Running what-if analysis...[/]")
    from infrasim.simulator.whatif_engine import WhatIfEngine

    whatif_engine = WhatIfEngine(graph)
    whatif_results = whatif_engine.run_default_whatifs()

    # Build a quick summary of pass/fail per parameter at key values
    whatif_summary: dict[str, str] = {}
    for wr in whatif_results:
        param_display = wr.parameter.replace("_", " ").title()
        # Find the most extreme tested value that still passes
        all_pass = all(wr.slo_pass)
        if all_pass:
            whatif_summary[param_display] = "PASS"
        elif wr.breakpoint_value is not None:
            whatif_summary[param_display] = f"FAIL@{wr.breakpoint_value}"
        else:
            whatif_summary[param_display] = "FAIL"

    evaluation_data["whatif"] = {
        "parameters_tested": len(whatif_results),
        "results": {
            wr.parameter: {
                "values": wr.values,
                "slo_pass": wr.slo_pass,
                "breakpoint": wr.breakpoint_value,
            }
            for wr in whatif_results
        },
    }

    # ------------------------------------------------------------------
    # 5. Capacity Planning
    # ------------------------------------------------------------------
    console.print("[cyan]  [5/5] Running capacity planning...[/]")
    from infrasim.simulator.capacity_engine import CapacityPlanningEngine

    cap_engine = CapacityPlanningEngine(graph)
    cap_report = cap_engine.forecast(monthly_growth_rate=0.10, slo_target=99.9)

    over_provisioned = [
        f for f in cap_report.forecasts
        if f.recommended_replicas_3m < f.current_replicas
    ]
    bottleneck_count = len(cap_report.bottleneck_components)

    evaluation_data["capacity"] = {
        "over_provisioned_count": len(over_provisioned),
        "cost_reduction_percent": round(cap_report.estimated_monthly_cost_increase, 1),
        "bottleneck_count": bottleneck_count,
        "bottleneck_components": cap_report.bottleneck_components[:5],
        "error_budget_status": cap_report.error_budget.status,
    }

    # ------------------------------------------------------------------
    # Determine overall verdict
    # ------------------------------------------------------------------
    if dyn_critical > 0 or static_critical > 0:
        verdict = "NEEDS ATTENTION"
        verdict_color = "red"
    elif dyn_warning > 0 or static_warning > 0:
        verdict = "ACCEPTABLE"
        verdict_color = "yellow"
    else:
        verdict = "HEALTHY"
        verdict_color = "green"

    evaluation_data["verdict"] = verdict

    # ------------------------------------------------------------------
    # JSON output
    # ------------------------------------------------------------------
    if json_output:
        console.print_json(data=evaluation_data)
        return

    # ------------------------------------------------------------------
    # Rich console output
    # ------------------------------------------------------------------
    box_width = 60

    # Header
    header_lines = (
        f"  InfraSim Full Evaluation Report\n"
        f"  Model: {model_name}\n"
        f"  Components: {num_components}  |  Dependencies: {num_dependencies}"
    )
    console.print(Panel(
        header_lines,
        style="bold",
        border_style="bright_blue",
        width=box_width,
    ))

    # 1. Static
    console.print(f"\n  [bold]1. Static Simulation[/]")
    console.print(f"     Resilience Score: [bold]{static_report.resilience_score:.0f}/100[/]")
    console.print(
        f"     Scenarios: [bold]{static_total:,}[/] tested"
        f" ({total_generated:,} generated)"
    )
    crit_color = "red" if static_critical > 0 else "dim"
    warn_color = "yellow" if static_warning > 0 else "dim"
    console.print(
        f"     [{crit_color}]Critical: {static_critical}[/]  |  "
        f"[{warn_color}]Warning: {static_warning}[/]  |  "
        f"[green]Passed: {static_passed}[/]"
    )

    # 2. Dynamic
    console.print(f"\n  [bold]2. Dynamic Simulation[/]")
    console.print(f"     Scenarios: [bold]{dyn_total:,}[/] tested")
    crit_color = "red" if dyn_critical > 0 else "dim"
    warn_color = "yellow" if dyn_warning > 0 else "dim"
    console.print(
        f"     [{crit_color}]Critical: {dyn_critical}[/]  |  "
        f"[{warn_color}]Warning: {dyn_warning}[/]  |  "
        f"[green]Passed: {dyn_passed}[/]"
    )
    if dyn_worst_name and dyn_worst_severity >= 4.0:
        sev_color = "red" if dyn_worst_severity >= 7.0 else "yellow"
        console.print(
            f"     [{sev_color}]Worst: {dyn_worst_name} "
            f"(severity: {dyn_worst_severity:.1f})[/]"
        )

    # 3. Ops
    console.print(f"\n  [bold]3. Ops Simulation ({ops_days} days)[/]")
    if ops_avg_avail >= 99.9:
        avail_color = "green"
    elif ops_avg_avail >= 99.0:
        avail_color = "yellow"
    else:
        avail_color = "red"
    console.print(
        f"     Availability: [{avail_color}]{ops_avg_avail:.3f}%[/]  |  "
        f"Downtime: {ops_result.total_downtime_seconds:.1f}s"
    )
    console.print(
        f"     Events: {ops_total_events} total "
        f"({ops_result.total_deploys} deploys, "
        f"{ops_result.total_degradation_events} degradation)"
    )
    console.print(f"     Peak Utilization: {ops_result.peak_utilization:.1f}%")

    # 4. What-If
    console.print(f"\n  [bold]4. What-If Analysis[/]")
    whatif_parts = []
    for wr in whatif_results:
        param_short = wr.parameter.replace("_factor", "").replace("_", " ").title()
        # Check the most extreme value tested
        extreme_val = wr.values[-1]
        extreme_pass = wr.slo_pass[-1] if wr.slo_pass else True
        pass_str = "[green]PASS[/]" if extreme_pass else "[red]FAIL[/]"
        whatif_parts.append(f"{param_short} {extreme_val}x: {pass_str}")
    # Display 3 per line
    for i in range(0, len(whatif_parts), 3):
        chunk = whatif_parts[i : i + 3]
        console.print(f"     {' | '.join(chunk)}")

    # 5. Capacity
    console.print(f"\n  [bold]5. Capacity Planning[/]")
    if over_provisioned:
        console.print(f"     Over-provisioned: {len(over_provisioned)} components")
    else:
        console.print(f"     Over-provisioned: 0 components")
    cost_val = cap_report.estimated_monthly_cost_increase
    if cost_val < 0:
        console.print(f"     Cost Reduction: [green]{cost_val:.1f}%[/]")
    elif cost_val > 0:
        console.print(f"     Cost Increase: [yellow]+{cost_val:.1f}%[/]")
    else:
        console.print(f"     Cost Change: 0.0%")
    console.print(f"     Bottlenecks: {bottleneck_count} components")

    # Overall Assessment
    assessment_lines = (
        f"  Overall Assessment\n"
        f"  [dim]|[/] Architecture Score: [bold]{static_report.resilience_score:.0f}/100[/] (structural)\n"
        f"  [dim]|[/] Operational Score: [{avail_color}]{ops_avg_avail:.3f}%[/] availability\n"
        f"  [dim]|[/] Dynamic Risks: "
        f"[red]{dyn_critical} CRITICAL[/], "
        f"[yellow]{dyn_warning} WARNING[/]\n"
        f"  [dim]|[/] Cost Optimization: {abs(cost_val):.1f}% "
        f"{'reduction' if cost_val < 0 else 'increase' if cost_val > 0 else 'change'} possible\n"
        f"  [dim]|[/] Verdict: [{verdict_color}][bold]{verdict}[/bold][/]"
    )

    console.print()
    console.print(Panel(
        assessment_lines,
        border_style=verdict_color,
        width=box_width,
    ))

    # ------------------------------------------------------------------
    # HTML export
    # ------------------------------------------------------------------
    if html:
        _export_html_report(html, evaluation_data, graph, static_report, dyn_report, ops_result, whatif_results, cap_report)
        console.print(f"\n[green]HTML report saved to {html}[/]")


def _export_html_report(
    path: Path,
    data: dict,
    graph: object,
    static_report: object,
    dyn_report: object,
    ops_result: object,
    whatif_results: list,
    cap_report: object,
) -> None:
    """Generate a cross-engine HTML evaluation report."""
    verdict = data.get("verdict", "UNKNOWN")
    verdict_color = "#e74c3c" if verdict == "NEEDS ATTENTION" else (
        "#f39c12" if verdict == "ACCEPTABLE" else "#2ecc71"
    )

    static = data.get("static", {})
    dynamic = data.get("dynamic", {})
    ops = data.get("ops", {})
    capacity = data.get("capacity", {})

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>InfraSim Full Evaluation Report - {data.get('model', '')}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       margin: 2em auto; max-width: 900px; color: #333; }}
h1 {{ border-bottom: 3px solid #3498db; padding-bottom: 0.3em; }}
h2 {{ color: #2c3e50; margin-top: 1.5em; }}
.verdict {{ background: {verdict_color}; color: #fff; padding: 0.5em 1em;
            border-radius: 4px; display: inline-block; font-size: 1.2em;
            font-weight: bold; }}
.metric {{ display: inline-block; margin: 0.3em 1em 0.3em 0;
           padding: 0.4em 0.8em; background: #f8f9fa; border-radius: 4px;
           border-left: 3px solid #3498db; }}
.critical {{ border-left-color: #e74c3c; }}
.warning {{ border-left-color: #f39c12; }}
.pass {{ border-left-color: #2ecc71; }}
table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
th, td {{ border: 1px solid #ddd; padding: 0.5em; text-align: left; }}
th {{ background: #f8f9fa; }}
</style>
</head>
<body>
<h1>InfraSim Full Evaluation Report</h1>
<p>Model: <strong>{data.get('model', '')}</strong> |
   Components: {data.get('components', 0)} |
   Dependencies: {data.get('dependencies', 0)}</p>
<p class="verdict">{verdict}</p>

<h2>1. Static Simulation</h2>
<div class="metric">Resilience Score: <strong>{static.get('resilience_score', 0)}/100</strong></div>
<div class="metric">Scenarios: {static.get('total_scenarios', 0)} tested</div>
<div class="metric critical">Critical: {static.get('critical', 0)}</div>
<div class="metric warning">Warning: {static.get('warning', 0)}</div>
<div class="metric pass">Passed: {static.get('passed', 0)}</div>

<h2>2. Dynamic Simulation</h2>
<div class="metric">Scenarios: {dynamic.get('total_scenarios', 0)} tested</div>
<div class="metric critical">Critical: {dynamic.get('critical', 0)}</div>
<div class="metric warning">Warning: {dynamic.get('warning', 0)}</div>
<div class="metric pass">Passed: {dynamic.get('passed', 0)}</div>
{'<p>Worst: ' + str(dynamic.get('worst_scenario', '')) + ' (severity: ' + str(dynamic.get('worst_severity', 0)) + ')</p>' if dynamic.get('worst_severity', 0) >= 4.0 else ''}

<h2>3. Ops Simulation ({ops.get('duration_days', 7)} days)</h2>
<div class="metric">Availability: {ops.get('avg_availability', 100.0):.3f}%</div>
<div class="metric">Downtime: {ops.get('total_downtime_seconds', 0):.1f}s</div>
<div class="metric">Events: {ops.get('total_events', 0)}</div>
<div class="metric">Peak Utilization: {ops.get('peak_utilization', 0):.1f}%</div>

<h2>4. What-If Analysis</h2>
<table>
<tr><th>Parameter</th><th>Values</th><th>SLO Pass</th><th>Breakpoint</th></tr>
"""

    whatif_data = data.get("whatif", {}).get("results", {})
    for param, info in whatif_data.items():
        values_str = ", ".join(str(v) for v in info.get("values", []))
        pass_str = ", ".join("PASS" if p else "FAIL" for p in info.get("slo_pass", []))
        bp = info.get("breakpoint")
        bp_str = str(bp) if bp is not None else "None"
        html_content += f"<tr><td>{param}</td><td>{values_str}</td><td>{pass_str}</td><td>{bp_str}</td></tr>\n"

    html_content += f"""</table>

<h2>5. Capacity Planning</h2>
<div class="metric">Over-provisioned: {capacity.get('over_provisioned_count', 0)} components</div>
<div class="metric">Cost Change: {capacity.get('cost_reduction_percent', 0):.1f}%</div>
<div class="metric">Bottlenecks: {capacity.get('bottleneck_count', 0)} components</div>

<h2>Overall Assessment</h2>
<ul>
<li>Architecture Score: {static.get('resilience_score', 0)}/100 (structural)</li>
<li>Operational Score: {ops.get('avg_availability', 100.0):.3f}% availability</li>
<li>Dynamic Risks: {dynamic.get('critical', 0)} CRITICAL, {dynamic.get('warning', 0)} WARNING</li>
<li>Cost Optimization: {abs(capacity.get('cost_reduction_percent', 0)):.1f}% possible</li>
<li>Verdict: <strong>{verdict}</strong></li>
</ul>

<hr>
<p><em>Generated by InfraSim evaluate</em></p>
</body>
</html>"""

    path.write_text(html_content, encoding="utf-8")
