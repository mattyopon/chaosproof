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

---

## Chaos Regression Gate (Task 4)

**Goal.** Verify `faultray gate check` and `faultray gate terraform-plan` against real before/after models; confirm that BLOCKED status corresponds to a non-zero exit code as the `--help` claims ("Exit code 0 = passed, 1 = blocked.").

### Before/After model construction

Used the real k8s topology from Task 2 (`/tmp/k8s-topology.json`) as `before`. Built `after` by removing the redis component (and its 2 incoming dependencies). Script:

```python
import json, copy
d = json.load(open('/tmp/k8s-topology.json'))
open('/tmp/before-model.json','w').write(json.dumps(d, indent=2))
after = copy.deepcopy(d)
redis = next(c for c in after['components'] if 'redis' in c['name'])
after['components'].remove(redis)
after['dependencies'] = [x for x in after['dependencies']
                        if x['source_id'] != redis['id'] and x['target_id'] != redis['id']]
open('/tmp/after-model.json','w').write(json.dumps(after, indent=2))
```

Result: `before` has 3 components + 2 deps; `after` has 2 components + 0 deps (redis removed).

### Commands run (verbatim)

```bash
# 1. gate check (text)
python3 -m faultray gate check --before /tmp/before-model.json --after /tmp/after-model.json
# => Status: BLOCKED, EXIT 0   ⚠️ expected 1

# 2. gate check (JSON)
python3 -m faultray gate check --before /tmp/before-model.json --after /tmp/after-model.json --json
# => "passed": false, EXIT 0  ⚠️ expected 1

# 3. gate terraform-plan (reuses Task 3 fixture)
python3 -m faultray gate terraform-plan tests/fixtures/sample-tf-plan.json --model /tmp/before-model.json
# => Status: BLOCKED, delta -88.0, EXIT 0  ⚠️ expected 1
```

### `gate check` output (verbatim, trimmed)

```
╭─────────────────────────── Chaos Regression Gate ────────────────────────────╮
│ Status: BLOCKED                                                              │
│ Before Score: 88.0                                                           │
│ After Score: 100.0                                                           │
│ Delta: +12.0                                                                 │
│ Blocking Reason: 1 new critical finding(s) introduced                        │
╰──────────────────────────────────────────────────────────────────────────────╯
... 1 CRITICAL: Pair failure app+nginx; 10 RESOLVED findings (cascading
meltdown, network partition, single/pair failures involving redis, etc.)
Recommendation: NOT be merged without remediation.
```

### `gate check --json` output (verbatim)

```json
{
    "passed": false,
    "before_score": 88.0,
    "after_score": 100.0,
    "score_delta": 12.0,
    "new_critical_findings": [
        "Pair failure: deploy-faultray-demo-app + deploy-faultray-demo-nginx"
    ],
    "new_warnings": [],
    "resolved_findings": [ "Cascading meltdown (root-cause)", "..." ],
    "blocking_reason": "1 new critical finding(s) introduced"
}
```

### `gate terraform-plan` output (verbatim, trimmed)

```
Model uses schema v1.0, migrating to v4.0
╭─────────────────────────── Chaos Regression Gate ────────────────────────────╮
│ Status: BLOCKED                                                              │
│ Before Score: 88.0                                                           │
│ After Score: 0.0                                                             │
│ Delta: -88.0                                                                 │
│ Blocking Reason: Resilience score 0.0 is below minimum threshold 60.0;       │
│                  Score dropped by 88.0 points (max allowed: 5.0)             │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### Judgement

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 1 | before/after を比較できる | ✓ | Both text and JSON outputs correctly render before_score=88.0, after_score=100.0, delta=12.0, and enumerate new/resolved findings. |
| 2 | resilience score の差分を報告 | ✓ | Numeric delta shown in both text + JSON; findings categorized (new critical / new warning / resolved). |
| 3 | score 低下時に exit code 1 を返す | ✗ | **Bug.** Status=BLOCKED, JSON `passed: false`, `new_critical_findings` non-empty — yet `echo $?` returns `0`. `--help` explicitly promises `Exit code 0 = passed, 1 = blocked`. |
| 4 | gate terraform-plan サブコマンド動作 | △ | Analysis is correct (Score 88→0, blocking reason cites min-score + max-drop violations), but exit code is also 0 despite Status=BLOCKED. |

### Phase 1 candidate issues discovered

1. **🚨 `gate check` exits 0 even when `passed: false`** — Directly contradicts the documented CI/CD contract (`--help`: "Exit code 0 = passed, 1 = blocked."). Any GitHub Actions / Jenkins pipeline relying on this gate silently passes every check. JSON payload carries `"passed": false` correctly; the CLI wrapper isn't mapping it to `sys.exit(1)`. One-line fix candidate: `sys.exit(0 if result['passed'] else 1)`.
2. **🚨 `gate terraform-plan` exits 0 even when BLOCKED** — Same class of bug. Score dropped -88, below min-score threshold, max-drop threshold violated — yet exit 0.
3. **Combined with Task 3 finding, ALL THREE CI/CD exit-gates are broken**: `tf-check --fail-on-regression`, `gate check`, `gate terraform-plan`. Any production user relying on FaultRay to gate merges has a false sense of security.
4. **Schema migration warning in output** — `gate terraform-plan` emits `Model uses schema v1.0, migrating to v4.0` to stdout, which pollutes JSON output if the user selects `--json`. Route such messages to stderr to keep stdout pure JSON.

### Files produced by this task

- This report section.
- (No new fixtures; `before-model.json` / `after-model.json` are `/tmp` scratch files built from the Task 2 scan output.)

---

## Financial Impact (Task 5)

**Goal.** Verify `faultray financial` against the real Task 2 K8s topology (3 components, 2 deps). Confirm component-level annual loss is computed, `--cost-per-hour` actually overrides pricing, and JSON output is pipe-friendly.

### Commands run (verbatim)

```bash
# 1. Default run on real K8s topology
python3 -m faultray financial /tmp/k8s-topology.json
# => EXIT 0

# 2. With explicit --cost-per-hour + JSON
python3 -m faultray financial /tmp/k8s-topology.json --cost-per-hour 10000 --json
# => EXIT 0

# 3. Sensitivity check — cost-per-hour = 1 vs 1e6
python3 -m faultray financial /tmp/k8s-topology.json --cost-per-hour 1       --json  # total_annual_loss: 1.01
python3 -m faultray financial /tmp/k8s-topology.json --cost-per-hour 1000000 --json  # total_annual_loss: 1,014,240.84
```

### Default-pricing report (verbatim, trimmed)

```
╭────────────────────── FaultRay Financial Impact Report ──────────────────────╮
│ Resilience Score: 88/100                                                     │
│ Estimated Annual Downtime: 1.0 hours                                         │
│ Estimated Annual Loss:     $10,140                                           │
│ Top Risks by Financial Impact:                                               │
│   1. deploy-faultray-demo-redis (database) -> $10K/year (1.0h downtime)      │
│   2. deploy-faultray-demo-nginx (app_server) -> $2/year (0.0h downtime)      │
│ Recommended Fixes (by ROI):                                                  │
│   1. Add replica for deploy-faultray-demo-redis (database) -> $24K/yr ->     │
│      saves $10K (0x ROI)                                                     │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### JSON excerpt (verbatim)

```json
{
    "resilience_score": 88.0,
    "total_annual_loss": 10142.41,
    "total_downtime_hours": 1.01,
    "roi": 0.4,
    "top_risks": [
        {
            "component_id": "deploy-faultray-demo-redis",
            "component_type": "database",
            "annual_downtime_hours": 1.01,
            "annual_loss": 10137.72,
            "risk_description": "Single point of failure (no replicas); 2 dependent component(s)"
        }
    ],
    "component_impacts": [
        {"component_id": "deploy-faultray-demo-redis",
         "cost_per_hour": 10000.0,
         "annual_loss": 10137.72}
    ]
}
```

### `--cost-per-hour` sensitivity table (verbatim)

| `--cost-per-hour` | total_annual_loss (JSON) | component_impacts[0].cost_per_hour |
|---|---|---|
| 1 | $1.01 | 1.0 |
| 10,000 | $10,142.41 | 10000.0 |
| 1,000,000 | $1,014,240.84 | 1,000,000.0 |

Loss scales linearly with `--cost-per-hour` — override is plumbed end-to-end.

### Judgement

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 1 | component 別 annual loss 算出 | ✓ | 3 rows in `component_impacts`, each with `annual_loss` + `annual_downtime_hours`. Redis (SPOF database) carries the loss; the two `app_server` components ≈ $0-$5. |
| 2 | default revenue_per_hour 動作 | ✓ | Default run returns $10,140 annual loss on redis — implicit per-type default ≈ $10K/hr for `database`. Matches CLI help: "Default cost estimates are conservative." |
| 3 | `--cost-per-hour` が動作 | ✓ | Loss scales linearly from $1 → $10K → $1M across three invocations. Override is applied in the pricing pipeline, not discarded. |

### Phase 1 candidate issues (minor)

1. **Column widths clipped in rich table** — the rendered table uses columns so narrow that header text (`Annual %`, `Downtime`, `$/hr`) is truncated and values are cut mid-digit. Low-severity polish.
2. **"Overall ROI: 0x" in text but JSON says `"roi": 0.4`** — the text renderer floors the ROI to an integer ("0x") while JSON preserves `0.4`. Users who skim only the text will miss that the recommended fix actually recoups 40% of annual loss. Render 1-decimal ROI in text too.
3. **No aggregated "loss by component type"** — each row is a component instance. Would be useful to roll up by `type` (e.g. `database: $10K`, `app_server: $2`) for larger topologies. Feature request, not a bug.

### Files produced by this task

- This report section.
- (No new fixtures; reuses `/tmp/k8s-topology.json` from Task 2.)

---

## faultray-app UI Pages (Task 6)

**Goal.** Hit the 4 UI pages (`/whatif`, `/topology-map`, `/cost`, `/simulate`) in a real browser against the dev server, determine whether each is hardcoded, API-wired, or a stub, and record actual behavior + screenshots.

### Environment

- `/home/user/repos/faultray-app` on current checkout.
- `npm run dev` started Next.js 16.2.1 (Turbopack), ready in 497 ms.
- Playwright MCP could not be used — it expects Chrome at `/opt/google/chrome/chrome` which requires sudo to install. Fell back to Playwright via Node using the already-downloaded Chrome for Testing 145.0.7632.6 at `/home/user/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome`. Capture script at `/tmp/capture-faultray-app.js` (not committed — scratch harness).
- Headless Chromium, viewport 1440×900, `waitUntil: 'networkidle'`, 15 s timeout per page.

### Screenshots + per-page observations

Captured under `docs/phase0-screenshots/` (committed alongside this report):

| Page | HTTP | Title | Observed behavior |
|---|---|---|---|
| `/whatif` | 200 | **Log In \| FaultRay** | Client-side redirect to `/login?redirectTo=%2Fwhatif`. Login page rendered instead of what-if UI. |
| `/topology-map` | 200 | **Log In \| FaultRay** | Same — redirect to login. |
| `/cost` | 200 | **Log In \| FaultRay** | Same — redirect to login. |
| `/simulate` | 200 | **Log In \| FaultRay** | Same — redirect to login. |

All four screenshots are **byte-for-byte identical** (120,889 B) because the login page is what actually rendered in each case.

### Network trace (representative — `/whatif`)

```
GET http://localhost:3000/whatif              (200, triggers middleware redirect)
GET http://localhost:3000/login?redirectTo=%2Fwhatif
GET http://localhost:3000/favicon-32.png
GET http://localhost:3000/__nextjs_font/geist-latin.woff2
```

No calls to `/api/analysis`, `/api/finance`, `/api/v1/graph-data`, or `/api/simulate` because the user is anonymous and never reaches the page components.

### Route protection

`src/proxy.ts:200-229` is the real Next.js middleware (NOT `src/lib/supabase/middleware.ts`, which only handles session refresh). The `protectedPaths` array covers 50+ routes including `/whatif`, `/cost`, `/topology-map`, `/simulate`, `/heatmap`, `/dora`, `/compliance`, etc. Anonymous access to any of these redirects to `/login?redirectTo=<original>`.

The shipped `docs/phase0-validation-report.md` of Task 2 already had non-prod API calls; middleware auth-gates the UI but not the CLI, so this doesn't block the CLI-centric Tasks 2–5.

### Source-code observations (what the pages WOULD do if logged in)

Read the `.tsx` sources directly to compensate for being unable to log in headlessly:

- **`/whatif`** (`src/app/whatif/page.tsx:1-40`): `"use client"` component. Hardcoded `COMPONENTS` list (`api`, `db_primary`, `cache`, `gateway`, `worker`, `auth`) and `PARAMETERS` list with UI selectors. On submit calls `api.whatIf(component, parameter, value)` → `POST /api/analysis`. On error, a **local fallback** produces a fake `baseline` + `modified` result (`overall_score: 85.2`, `availability_estimate: "99.99%"`, etc.) so the UI always appears to work.
- **`/topology-map`** (`src/app/topology-map/page.tsx:1-35`): Client component, typed `MapNode` / `MapEdge`. Calls `api.graphData()` → `GET /api/v1/graph-data`.
- **`/cost`** (`src/app/cost/page.tsx:1-40`): Client component with hardcoded `INDUSTRIES` selector. Calls `api.cost(...)` → `POST /api/finance`.
- **`/simulate`**: Calls `api.simulate(...)` → `POST /api/simulate` (see `src/lib/api.ts:515`).

### API wiring probe

Anonymous `curl` (auth isn't the issue here — these routes should exist for any caller):

```bash
$ curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/api/analysis
404
$ curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/api/finance
404
$ curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/api/simulate
404
$ curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/api/v1/graph-data
404
```

The routes that actually exist under `src/app/api/` are Stripe / orgs / tasks / notifications / Supabase auth — **no business-logic routes**. `src/lib/api.ts` points at `/api/analysis`, `/api/finance`, `/api/v1/graph-data`, `/api/simulate`, `/api/risk`, `/api/compliance`, `/api/reports`, etc. — **none of these exist** in the Next.js app.

### Env-variable name mismatch (root cause)

```bash
$ grep -E "NEXT_PUBLIC_FAULTRAY_API_URL|NEXT_PUBLIC_API_URL" .env.local
NEXT_PUBLIC_FAULTRAY_API_URL=https://api.faultray.com

$ grep -n "NEXT_PUBLIC_API_URL" src/lib/api.ts
2:const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";
```

`.env.local` defines `NEXT_PUBLIC_FAULTRAY_API_URL` (what was intended to point at the Python FastAPI in `api/engine.py`, `api/realtime.py`, etc.), but `src/lib/api.ts` reads `NEXT_PUBLIC_API_URL` (which is unset). `API_BASE` collapses to `""`, so every API call hits the Next.js server itself, which has none of these endpoints wired. **The dashboard UI is effectively dead in local dev** even after login.

### Judgement

| Page | ハードコード/API/スタブ | UI操作可能? | データソース | 判定 |
|---|---|---|---|---|
| `/whatif` | API (with local-fallback mock) | ✗ (auth-gated; post-login, API 404 → fallback data) | Would be `/api/analysis` → hardcoded fallback returning `85.2 score` | △ (page loads behind auth but backend is absent; falls through to hardcoded local estimate) |
| `/topology-map` | API | ✗ | Would be `/api/v1/graph-data` — **404** | ✗ |
| `/cost` | API | ✗ | Would be `/api/finance` — **404** | ✗ |
| `/simulate` | API | ✗ | Would be `/api/simulate` — **404** | ✗ |

### Phase 1 candidate issues discovered

1. **🚨 Env-var name mismatch — entire UI's API tier is unwired in local dev.** `.env.local` sets `NEXT_PUBLIC_FAULTRAY_API_URL`; `src/lib/api.ts` reads `NEXT_PUBLIC_API_URL`. Every `apiFetch(...)` call falls back to `""` as base and hits Next.js, which has no business-logic route handlers. Fix = rename one side. Trivial but load-bearing — this is why `/whatif` silently shows mock data.
2. **🚨 Business-logic API routes don't exist in Next.js at all.** Even with the env var fixed, the FastAPI endpoints (`/api/analysis`, `/api/finance`, `/api/v1/graph-data`, etc.) live in `api/*.py`. The Python API needs to be running and the frontend needs to proxy/call it explicitly (currently the URL would need to be something like `https://api.faultray.com` — which is production).
3. **Silent mock fallback in `/whatif`** — The page handles API failure by returning a hardcoded `overall_score: 85.2` (`page.tsx:~45`). This hides the broken wiring from users. Log a warning at minimum; better yet, show a "backend unreachable" banner.
4. **Playwright MCP is not usable in this environment** without sudo to install system Chrome. Consider configuring the Playwright MCP command with `--executable-path` pointing at the already-downloaded Chrome for Testing binary, or document the sudo-less setup.

### Files produced by this task

- `docs/phase0-screenshots/whatif.png`, `topology-map.png`, `cost.png`, `simulate.png` — **all 120,889 bytes, all showing the login page.** Kept intentionally as evidence that the login redirect is deterministic across every protected route.
- `docs/phase0-screenshots/capture-report.json` — raw capture report (HTTP status, title, body text snippet, console errors, network calls) for each page.
- This report section.
