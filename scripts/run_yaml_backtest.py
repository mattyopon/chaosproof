#!/usr/bin/env python3
"""Run BacktestEngine on YAML incident files and update backtest-results.json.

Reads tests/incidents/*.yaml, constructs InfraGraph + RealIncident for each,
runs BacktestEngine.run_backtest(), and updates docs/backtest-results.json
with real simulation results (replacing synthetic values).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.simulator.backtest_engine import BacktestEngine, RealIncident


COMPONENT_TYPE_MAP = {
    "load_balancer": ComponentType.LOAD_BALANCER,
    "app_server": ComponentType.APP_SERVER,
    "database": ComponentType.DATABASE,
    "cache": ComponentType.CACHE,
    "queue": ComponentType.QUEUE,
    "storage": ComponentType.STORAGE,
    "dns": ComponentType.DNS,
    "external_api": ComponentType.EXTERNAL_API,
    "web_server": ComponentType.WEB_SERVER,
    "custom": ComponentType.CUSTOM,
}


def yaml_to_graph(topology: dict) -> InfraGraph:
    """Convert YAML topology to InfraGraph."""
    graph = InfraGraph()
    for comp in topology.get("components", []):
        ctype = COMPONENT_TYPE_MAP.get(comp["type"], ComponentType.CUSTOM)
        component = Component(
            id=comp["id"],
            name=comp["id"],
            type=ctype,
            replicas=comp.get("replicas", 1),
        )
        graph.add_component(component)

    for dep in topology.get("dependencies", []):
        dependency = Dependency(
            source_id=dep["source"],
            target_id=dep["target"],
            dependency_type=dep.get("type", "requires"),
        )
        graph.add_dependency(dependency)

    return graph


def yaml_to_incident(incident_data: dict) -> RealIncident:
    """Convert YAML incident section to RealIncident."""
    return RealIncident(
        incident_id=incident_data["id"],
        timestamp=str(incident_data.get("date", "")),
        failed_component=incident_data["affected_services"][0],
        actual_affected_components=incident_data["affected_services"],
        actual_downtime_minutes=incident_data.get("duration_hours", 1) * 60,
        actual_severity=incident_data.get("severity", "medium"),
        root_cause=incident_data.get("root_cause", ""),
    )


def main() -> None:
    incidents_dir = PROJECT_ROOT / "tests" / "incidents"
    results_file = PROJECT_ROOT / "docs" / "backtest-results.json"

    # Load existing results
    existing = json.loads(results_file.read_text())
    existing_ids = {e["incident_id"] for e in existing["per_incident"]}

    # Find YAML files
    yaml_files = sorted(incidents_dir.glob("*.yaml"))
    print(f"Found {len(yaml_files)} YAML incident files")

    new_results = []
    errors = []

    for yf in yaml_files:
        data = yaml.safe_load(yf.read_text())
        incident_data = data["incident"]
        iid = incident_data["id"]

        # Skip if already in results with real data
        if iid in existing_ids:
            # Check if it's synthetic (downtime_mae pattern)
            existing_entry = next(
                (e for e in existing["per_incident"] if e["incident_id"] == iid), None
            )
            if existing_entry and (existing_entry["downtime_mae"] + 0.5) % 30 != 0:
                print(f"  SKIP {iid} (already has real backtest data)")
                continue

        try:
            graph = yaml_to_graph(data["topology"])
            incident = yaml_to_incident(incident_data)
            engine = BacktestEngine(graph)
            results = engine.run_backtest([incident])

            if results:
                r = results[0]
                entry = {
                    "incident_id": iid,
                    "component": incident.failed_component,
                    "precision": r.precision,
                    "recall": r.recall,
                    "f1": r.f1_score,
                    "severity_accuracy": r.severity_accuracy,
                    "downtime_mae": r.downtime_mae,
                    "confidence": r.prediction_confidence,
                }
                new_results.append(entry)
                print(f"  OK {iid}: F1={r.f1_score}, sev_acc={r.severity_accuracy}")
        except Exception as e:
            errors.append((iid, str(e)))
            print(f"  ERROR {iid}: {e}")

    # Update existing results: replace synthetic entries with real ones
    new_ids = {r["incident_id"] for r in new_results}
    kept = [e for e in existing["per_incident"] if e["incident_id"] not in new_ids]
    all_entries = kept + new_results

    # Recalculate aggregates
    n = len(all_entries)
    avg_precision = sum(e["precision"] for e in all_entries) / n if n else 0
    avg_recall = sum(e["recall"] for e in all_entries) / n if n else 0
    avg_f1 = sum(e["f1"] for e in all_entries) / n if n else 0
    avg_sev = sum(e["severity_accuracy"] for e in all_entries) / n if n else 0
    avg_mae = sum(e["downtime_mae"] for e in all_entries) / n if n else 0
    avg_conf = sum(e["confidence"] for e in all_entries) / n if n else 0

    updated = {
        "total_incidents": n,
        "avg_precision": round(avg_precision, 4),
        "avg_recall": round(avg_recall, 4),
        "avg_f1": round(avg_f1, 4),
        "avg_severity_accuracy": round(avg_sev, 4),
        "avg_downtime_mae_minutes": round(avg_mae, 2),
        "avg_confidence": round(avg_conf, 4),
        "calibration": existing.get("calibration", {}),
        "per_incident": all_entries,
    }

    results_file.write_text(json.dumps(updated, indent=2) + "\n")
    print(f"\nUpdated {results_file}: {n} incidents total")
    print(f"  New/replaced: {len(new_results)}, Errors: {len(errors)}")
    if errors:
        print("  Errors:")
        for iid, err in errors:
            print(f"    {iid}: {err}")


if __name__ == "__main__":
    main()
