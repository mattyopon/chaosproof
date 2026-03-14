# InfraSim - Virtual Infrastructure Simulation Platform

**実インフラに一切触れず、障害の連鎖的影響・SLO/SLI・キャパシティをシミュレーションする仮想インフラシミュレーションプラットフォーム**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## What is InfraSim?

InfraSim は、インフラの依存関係グラフをモデル化し、**150以上のカオスシナリオ**を自動生成・実行してシステムの脆弱性と障害連鎖リスクを可視化するツールです。さらに、**SLO/SLI追跡**、**What-if分析**、**キャパシティプランニング**、**トラフィックパターンシミュレーション（DDoS・日次変動・成長トレンド）**、**長期運用シミュレーション（ops-sim）** を備えた包括的なインフラシミュレーションプラットフォームです。

**Gremlin や Chaos Monkey との違い**: これらは実際のインフラに障害を注入しますが、InfraSim は**完全に仮想環境（メモリ上）で実行**するため、本番・ステージング環境に一切影響を与えません。

### Key Features

- **Zero Risk** - 実インフラに触れない完全仮想シミュレーション
- **150+ Scenarios** - 30カテゴリのカオスシナリオを自動生成
- **Dependency Graph** - NetworkX による依存関係グラフ解析と連鎖障害予測
- **Risk Scoring** - 影響度 × 拡散率 × 発生確率の3軸定量評価
- **SLO/SLI Tracking** - 可用性・レイテンシ・エラー率のSLO目標に対する追跡と評価
- **What-If Analysis** - パラメータスイープによる障害耐性の感度分析
- **Capacity Planning** - 成長予測に基づくキャパシティ計画とSLO達成可否の評価
- **Traffic Patterns** - DDoS・日次変動・成長トレンドなど10種類のトラフィックモデル
- **Operational Simulation** - 長期間（数日〜数週間）の運用シミュレーション（ops-sim）
- **Dynamic Simulation** - 時間ステップ型の動的シミュレーションとトラフィックパターン連動
- **Security Feed** - セキュリティニュースから最新脅威シナリオを自動追加
- **Terraform Integration** - tfstate / plan からインフラ自動インポート & 変更影響分析
- **Web Dashboard** - D3.js インタラクティブグラフ & Grafana風ダッシュボード
- **Multiple Discovery** - ローカルスキャン / Prometheus / Terraform / YAML

## Quick Start

```bash
# Install
pip install -e .

# Run demo (6-component web stack simulation)
infrasim demo

# With web dashboard
infrasim demo --web
```

### Output Example

```
╭────────── InfraSim Chaos Simulation Report ──────────╮
│ Resilience Score: 36/100                             │
│ Scenarios tested: 150                                │
│ Critical: 7  Warning: 67  Passed: 76                 │
╰──────────────────────────────────────────────────────╯

CRITICAL FINDINGS

  10.0/10 CRITICAL  Traffic spike (10x)
  Cascade path:
  ├── DOWN nginx (LB)
  ├── DOWN api-server-1
  ├── DOWN api-server-2
  ├── DOWN PostgreSQL (primary)
  ├── DOWN Redis (cache)
  └── DOWN RabbitMQ
```

## Usage

### From YAML Definition

```yaml
# infra.yaml
components:
  - id: nginx
    type: load_balancer
    port: 443
    replicas: 2
    metrics: { cpu_percent: 25, memory_percent: 30 }
    capacity: { max_connections: 10000 }

  - id: api
    type: app_server
    port: 8080
    metrics: { cpu_percent: 65, memory_percent: 70 }
    capacity: { max_connections: 500, connection_pool_size: 100 }

  - id: postgres
    type: database
    port: 5432
    metrics: { cpu_percent: 45, memory_percent: 80, disk_percent: 72 }
    capacity: { max_connections: 100 }

dependencies:
  - source: nginx
    target: api
    type: requires
  - source: api
    target: postgres
    type: requires
```

```bash
infrasim load infra.yaml
infrasim simulate --html report.html
```

### From Terraform

```bash
# Import from state file
infrasim tf-import --state terraform.tfstate

# Import from live terraform
infrasim tf-import --dir ./terraform

# Analyze plan impact
terraform plan -out=plan.out
infrasim tf-plan plan.out --html plan-report.html
```

### From Prometheus

```bash
infrasim scan --prometheus-url http://prometheus:9090
infrasim simulate
```

### Security News Feed

```bash
# Fetch latest security news and generate scenarios
infrasim feed-update

# View generated scenarios
infrasim feed-list

# Simulate with feed scenarios included automatically
infrasim simulate
```

### Web Dashboard

```bash
infrasim serve --port 8080
# Open http://localhost:8080
```

### Operational Simulation

長期間の運用をシミュレーションし、SLO達成率やインシデント発生をトラッキングします。

```bash
# Run 7-day operational simulation with 5-minute time steps
infrasim ops-sim infra.yaml --days 7 --step 5min

# Run with default parameters
infrasim ops-sim --defaults
```

### What-If Analysis

パラメータを変動させて障害耐性の感度を分析します。

```bash
# Run with default parameter sweep
infrasim whatif infra.yaml --defaults

# Sweep a specific parameter
infrasim whatif --parameter mttr_factor --values "0.5,1.0,2.0,4.0"
```

### Capacity Planning

成長予測に基づくキャパシティ計画を立案し、SLO達成可否を評価します。

```bash
# Capacity planning with 15% annual growth targeting 99.9% SLO
infrasim capacity infra.yaml --growth 0.15 --slo 99.9
```

### Traffic Patterns

動的シミュレーションで使用可能なトラフィックパターン:

| Pattern | Description |
|---------|-------------|
| `CONSTANT` | 一定トラフィック |
| `RAMP` | 線形増加 |
| `SPIKE` | 瞬間的スパイク |
| `WAVE` | 正弦波パターン |
| `DDoS_VOLUMETRIC` | 大量リクエスト型DDoS |
| `DDoS_SLOWLORIS` | Slowloris型DDoS |
| `FLASH_CROWD` | フラッシュクラウド（突発的人気） |
| `DIURNAL` | 日次変動（昼高・夜低） |
| `DIURNAL_WEEKLY` | 週次変動（平日高・週末低） |
| `GROWTH_TREND` | 長期成長トレンド |

```bash
# Dynamic simulation with traffic pattern
infrasim dynamic infra.yaml --traffic diurnal --duration 24h --step 1min
```

## Chaos Scenarios (30 Categories)

| Category | Examples |
|----------|---------|
| **Single Failures** | Component down, CPU saturation, OOM, disk full, network partition |
| **Traffic** | 1.5x, 2x, 3x, 5x, 10x (DDoS-level) traffic spikes |
| **Compound** | All pairwise (C(n,2)) and triple (C(n,3)) simultaneous failures |
| **DB-Specific** | Log explosion, replication lag, connection storm, lock contention |
| **Cache-Specific** | Stampede, eviction storm, split brain |
| **Queue-Specific** | Backpressure, poison message |
| **LB-Specific** | Health check failure, TLS expiry, config reload failure |
| **App-Specific** | Memory leak, thread exhaustion, GC pause, bad deployment |
| **Infrastructure** | Zone failure, cascading timeouts, total meltdown, rolling restart |
| **Real-World** | Black Friday (10x + cache pressure), noisy neighbor, slow DB at peak |
| **Security Feed** | Auto-generated from CISA, NVD, Krebs, BleepingComputer, etc. |

## Risk Scoring

```
severity = (impact × spread) × likelihood

impact  = weighted health status (DOWN=1.0, OVERLOADED=0.5, DEGRADED=0.25)
spread  = affected_components / total_components
likelihood = proximity to failure threshold (0.2 = unlikely, 1.0 = imminent)
```

| Level | Score | Meaning |
|-------|-------|---------|
| CRITICAL | 7.0-10.0 | Cascading failure, major outage risk |
| WARNING | 4.0-6.9 | Degradation, limited cascade |
| PASSED | 0.0-3.9 | Low risk, contained impact |

## Architecture

```
Discovery Layer          Model Layer           Simulator Layer
┌─────────────┐    ┌─────────────────┐    ┌──────────────────┐
│ Local Scan   │    │ InfraGraph      │    │ 30-cat Scenarios │
│ Prometheus   │───>│ Components      │───>│ Cascade Engine   │
│ Terraform    │    │ Dependencies    │    │ Ops Engine       │
│ YAML Loader  │    │ NetworkX Graph  │    │ What-If Engine   │
└─────────────┘    └─────────────────┘    │ Capacity Engine  │
                                          │ Traffic Models   │
                                          │ Feed Scenarios   │
                                          │ Risk Scoring     │
                                          └──────────────────┘
                                                    │
                   ┌─────────────────┐    ┌──────────────────┐
                   │ Web Dashboard   │<───│ CLI Reporter     │
                   │ FastAPI + D3.js │    │ HTML Reporter    │
                   └─────────────────┘    └──────────────────┘
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `infrasim scan` | Discover local system or Prometheus infrastructure |
| `infrasim simulate` | Run chaos simulation (150+ scenarios) |
| `infrasim dynamic` | Run dynamic time-stepped simulation with traffic patterns |
| `infrasim ops-sim` | Long-running operational simulation with SLO tracking |
| `infrasim show` | Display infrastructure model summary |
| `infrasim load <yaml>` | Load infrastructure from YAML |
| `infrasim tf-import` | Import from Terraform state |
| `infrasim tf-plan <plan>` | Analyze Terraform plan impact |
| `infrasim report` | Generate HTML report |
| `infrasim serve` | Launch web dashboard |
| `infrasim demo` | Run demo with sample infrastructure |
| `infrasim feed-update` | Update scenarios from security news |
| `infrasim feed-list` | Show stored feed scenarios |
| `infrasim feed-sources` | Show configured news sources |
| `infrasim feed-clear` | Clear feed scenario store |
| `infrasim whatif` | Run what-if analysis (parameter sweep) |
| `infrasim capacity` | Capacity planning with growth forecasting |

## Requirements

- Python 3.11+
- Dependencies: typer, rich, pydantic, networkx, psutil, fastapi, uvicorn, jinja2, httpx, pyyaml

## License

MIT License - see [LICENSE](LICENSE)
