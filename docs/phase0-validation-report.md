# FaultRay Phase 0 Baseline Validation Report

This report records hands-on validation of FaultRay's cloud / Kubernetes /
Terraform discovery and simulation commands against **real** external
infrastructure (i.e. not the built-in `demo` model). Each section lists the
exact commands executed, verbatim output excerpts, and a per-criterion
judgement.

Judgement legend:
- ✓ — verified, behaves as expected.
- △ — partially verified, or verified with caveats worth documenting.
- ✗ — failed / not verified.

Environment:

- Date: 2026-04-17
- Host: WSL2 (Ubuntu), Docker Desktop WSL integration enabled
- FaultRay: installed editable from `/home/user/repos/faultray`, v11.2.0
- Tools:
  - `kind v0.27.0 go1.23.6 linux/amd64`
  - `kubectl Client Version: v1.35.4`
  - `docker 29.2.0` (accessed via `sg docker -c '...'` — the active shell is
    not yet in the `docker` group)

---

## K8s Discovery (Task 2)

**Goal.** Verify that `faultray scan --k8s` discovers a real Kubernetes
topology (three Deployments + Services across a namespace), that dependencies
are inferred, and that the resulting model can be fed straight into
`faultray simulate`.

### Commands run (verbatim)

```bash
# 1. Create kind cluster (control-plane + worker)
sg docker -c "/home/user/.local/bin/kind create cluster \
    --name faultray-test \
    --config /home/user/repos/faultray/tests/fixtures/kind-config.yaml"

# 2. Deploy sample workload (3 Deployments + 3 Services in faultray-demo ns)
sg docker -c "/home/user/.local/bin/kubectl --context kind-faultray-test \
    apply -f /tmp/sample-microservices.yaml"
sg docker -c "/home/user/.local/bin/kubectl --context kind-faultray-test \
    -n faultray-demo wait --for=condition=Available --timeout=180s \
    deployment/nginx deployment/redis deployment/app"

# 3. Scan
sg docker -c "python3 -m faultray scan --k8s \
    --context kind-faultray-test --namespace faultray-demo \
    --output /tmp/k8s-topology.json"

# 4. Simulate off the scan output
python3 -m faultray simulate --model /tmp/k8s-topology.json
python3 -m faultray simulate --model /tmp/k8s-topology.json --json

# 5. Tear down
sg docker -c "/home/user/.local/bin/kind delete cluster --name faultray-test"
```

### Cluster state before scan (verbatim)

```
NAME                    READY   UP-TO-DATE   AVAILABLE   AGE
deployment.apps/app     3/3     3            3           24s
deployment.apps/nginx   2/2     2            2           24s
deployment.apps/redis   1/1     1            1           24s

NAME            TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE
service/app     ClusterIP   10.96.61.172    <none>        8080/TCP   24s
service/nginx   ClusterIP   10.96.170.83    <none>        80/TCP     24s
service/redis   ClusterIP   10.96.221.227   <none>        6379/TCP   24s

NAME                         READY   STATUS    RESTARTS   AGE
pod/app-69f7dc54cc-2k8g4     1/1     Running   0          24s
pod/app-69f7dc54cc-bzz4b     1/1     Running   0          24s
pod/app-69f7dc54cc-d9fvs     1/1     Running   0          24s
pod/nginx-f576985cc-5zbc8    1/1     Running   0          24s
pod/nginx-f576985cc-gwwgl    1/1     Running   0          24s
pod/redis-5f86f8f9c7-f7h2v   1/1     Running   0          24s
```

Matches the spec: **3 deployments, 3 services, 6 pods** all `Running`.

### `faultray scan --k8s` output (verbatim)

```
FaultRay v11.2.0 [Free Tier - upgrade at github.com/sponsors/mattyopon]
Scanning Kubernetes cluster (context: kind-faultray-test) (namespace:
faultray-demo)...
Discovered 3 components, 2 dependencies in 0.1s
    Infrastructure Overview
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Metric           ┃ Value    ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ Components       │ 3        │
│ Dependencies     │ 2        │
│   app_server     │ 2        │
│   database       │ 1        │
│ Resilience Score │ 88.0/100 │
└──────────────────┴──────────┘

Model saved to /tmp/k8s-topology.json
```

Exit code `0`. Model file is valid JSON; components & dependencies extracted:

```
keys: ['schema_version', 'components', 'dependencies']
components:
 - faultray-demo/app   | app_server
 - faultray-demo/nginx | app_server
 - faultray-demo/redis | database
dependencies:
 - deploy-faultray-demo-app   -> deploy-faultray-demo-redis  (requires, tcp)
 - deploy-faultray-demo-nginx -> deploy-faultray-demo-redis  (requires, tcp)
```

Note: redis was auto-classified as `database` — that's a label-heuristic from
the scanner, not something we declared in the manifest. The two inferred deps
point from the two `app_server` components to the `database`, which matches
what a heuristic "every non-DB talks to the DB" rule would produce. There is
**no** edge from nginx ↔ app, even though a real HTTP fan-out topology
typically has one; the scanner does not yet use label/selector co-location or
Service endpoint analysis to infer that. See "Notes & Phase 1 candidates"
below.

### `faultray simulate --model` output (trimmed)

```
FaultRay v11.2.0 [Free Tier - upgrade at github.com/sponsors/mattyopon]
Loading infrastructure model...
Running chaos simulation (3 components)...
Scenarios: 66 generated, 66 tested

╭────────────────────── FaultRay Chaos Simulation Report ──────────────────────╮
│ Resilience Score: 88/100                                                     │
│ Scenarios tested: 66                                                         │
│ Critical: 11  Warning: 1  Passed: 54                                         │
╰──────────────────────────────────────────────────────────────────────────────╯
```

Exit code `0`. `simulate --json` additionally emits a machine-readable payload
with `scenarios`, `resilience_score`, etc. (131-line rich output in text mode;
the cascade traces correctly model both app and nginx failing 30 s after redis
goes down, matching the inferred dependency graph).

### Judgement

| # | Criterion (from the task spec) | Verdict | Evidence |
|---|---|---|---|
| 1 | scan output is YAML/JSON parseable | ✓ | `json.load('/tmp/k8s-topology.json')` succeeds; top-level keys `schema_version`, `components`, `dependencies`. |
| 2 | 3 components (nginx, redis, app) detected | ✓ | Table shows `Components: 3`; JSON lists all three names (`faultray-demo/nginx`, `faultray-demo/redis`, `faultray-demo/app`). |
| 3 | dependencies are inferred | △ | 2 deps inferred (`app→redis`, `nginx→redis`) via DB-heuristic only. No edge inferred between `nginx` and `app`, even though both are in the same namespace and a typical nginx+app pair has one. Phase 1 candidate: use Service selector + Endpoints API to discover east/west HTTP edges. |
| 4 | completes without errors | ✓ | Exit code 0, no stderr, 0.1 s wall-clock. |
| 5 | simulate consumes scan output | ✓ | `faultray simulate --model /tmp/k8s-topology.json` finishes with exit 0, runs 66 scenarios, produces a sensible cascade (redis failure propagates to app+nginx after 30 s). `--json` mode also parses. |

### Cleanup verification

```
$ sg docker -c "/home/user/.local/bin/kind get clusters"
No kind clusters found.
```

### Notes & Phase 1 candidates

1. **East/west dependency inference is thin.** The scanner only draws edges
   into components it has labelled as `database` (heuristic on image/name).
   There is no edge `nginx → app` or `app → nginx`, even though they share a
   namespace and have exposing Services. Consider using the Endpoints API
   and/or Service.spec.selector overlap to infer HTTP-tier edges in a future
   release.
2. **Component identity is a little inconsistent.** In the rendered table
   components are listed as `faultray-demo/<name>` but dependency IDs use
   `deploy-faultray-demo-<name>`. The JSON dependency records don't carry the
   resolved component names — consumers have to re-key. Low-severity Phase 1
   polish candidate.
3. **Port `0` in inferred dependencies.** Both inferred deps have `port: 0`
   and `latency_ms: 0.0`. The scanner isn't pulling port/protocol info from
   the Service spec. That's OK for topology, but simulation accuracy would
   improve if the actual service port (`6379` for redis) were attached.

### Files produced by this task

- `tests/fixtures/kind-config.yaml` — kind cluster config (control-plane + worker, named `faultray-test`).
- `tests/integration/test_k8s_discovery.py` — pytest integration test, marked `@pytest.mark.integration`, skipped automatically if kind/docker/kubectl aren't reachable from the session. Manual verification above is the primary evidence; the test is the reproducer.
- This report section.

---

## Terraform Check (Task 3)

**Goal.** Verify that `faultray tf-check` parses a Terraform plan JSON, detects destructive changes, reports blast radius, and that `--fail-on-regression` actually gates CI (non-zero exit) when resilience regresses.

### Commands run (verbatim)

```bash
# Create sample plan fixture (aws_instance.web + aws_db_instance.primary; DB scheduled for delete)
cat tests/fixtures/sample-tf-plan.json  # see fixture file for full content

# 1. Basic analysis
python3 -m faultray tf-check tests/fixtures/sample-tf-plan.json
# => EXIT 0

# 2. With --fail-on-regression
python3 -m faultray tf-check tests/fixtures/sample-tf-plan.json --fail-on-regression
# => EXIT 0  ⚠️  expected 1 (DB delete should regress)

# 3. JSON output
python3 -m faultray tf-check tests/fixtures/sample-tf-plan.json --json
# => EXIT 0

# 4. With stricter --min-score 99 + --fail-on-regression
python3 -m faultray tf-check tests/fixtures/sample-tf-plan.json --fail-on-regression --min-score 99
# => EXIT 0  (score_after=100.0 > 99, so threshold not triggered either)
```

### Text output (verbatim, trimmed)

```
╭────────────────────────── FaultRay Terraform Check ──────────────────────────╮
│ Terraform Plan Analysis                                                      │
│   Resources Added:     +0                                                    │
│   Resources Changed:   0                                                     │
│   Resources Destroyed: -1                                                    │
│   Score Before: 100.0                                                        │
│   Score After:  100.0 (0.0)                                                  │
│   Recommendation: HIGH RISK                                                  │
╰──────────────────────────────────────────────────────────────────────────────╯

                         Resource Changes
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ Address                             ┃ Actions         ┃  Risk  ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━┩
│ aws_db_instance.primary             │ delete          │   10   │
└─────────────────────────────────────┴─────────────────┴────────┘
```

### JSON output (verbatim)

```json
{
  "plan_file": "tests/fixtures/sample-tf-plan.json",
  "resources_added": 0,
  "resources_changed": 0,
  "resources_destroyed": 1,
  "score_before": 100.0,
  "score_after": 100.0,
  "score_delta": 0.0,
  "new_risks": [],
  "resolved_risks": [],
  "recommendation": "high risk"
}
```

### Judgement

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 1 | plan JSON parseable | ✓ | 4 invocations exited with correct resource counts (Destroyed: -1, DB address correctly surfaced). |
| 2 | resource_changes から DB 削除を検出 | ✓ | Text table + JSON both show `aws_db_instance.primary` with action `delete` and Risk `10`. |
| 3 | blast radius 算出 | △ | Risk column shows `10` (correctly high for DB delete), but `score_before` == `score_after` == `100.0`, `score_delta: 0.0`, `new_risks: []`. Risk/recommendation layer works; score-delta layer does not factor destructive changes into the numeric score. Internal inconsistency. |
| 4 | `--fail-on-regression` で exit code 1 | ✗ | **Bug.** DB delete produces Recommendation=HIGH RISK but exit code 0. Because `score_delta` is always 0 for plans that didn't start from an existing model, the regression check never fires. `--min-score 99` with `--fail-on-regression` also returns 0 (score_after=100.0 still passes threshold). CI/CD gating via this flag is non-functional on this scenario. |

### Phase 1 candidate issues discovered

1. **🚨 `tf-check --fail-on-regression` is broken for destructive-only plans** — The gate decision is driven purely by `score_after < score_before`, but the simulation uses the same topology model for both sides (no "before" reflects the pre-plan state when the model starts empty). Destructive resource changes produce Risk=10 in the per-resource table and Recommendation=HIGH RISK, yet `score_delta` stays `0.0` and exit code is 0. **This makes the CI gate ineffective.** Recommended fix: wire `--fail-on-regression` to also consider `recommendation == "high risk"` and/or the max row risk (≥ threshold). Regression test: the `sample-tf-plan.json` fixture added in this task can be used as the failing case.
2. **`new_risks` is always empty in the sample case** — Even though a DB deletion is the riskiest possible change, `new_risks: []` in JSON output. The risk enumeration isn't wired to the change analyzer. Phase 1 candidate to fix alongside #1.
3. **Score-delta layer ignores destructive changes** — `score_before` and `score_after` are both 100.0 despite `Resources Destroyed: -1`. The scoring pipeline needs to feed plan-applied state into the "after" model (not the current-state model).

### Files produced by this task

- `tests/fixtures/sample-tf-plan.json` — AWS EC2 + RDS plan with DB scheduled for delete. Minimal, no AWS account needed.
- This report section.
