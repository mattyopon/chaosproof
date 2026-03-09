# InfraSim - Virtual Infrastructure Chaos Engineering Simulator

**実インフラに一切触れず、障害の連鎖的影響をシミュレーションする仮想カオスエンジニアリングツール**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## What is InfraSim?

InfraSim は、インフラの依存関係グラフをモデル化し、**150以上のカオスシナリオ**を自動生成・実行してシステムの脆弱性と障害連鎖リスクを可視化するツールです。

**Gremlin や Chaos Monkey との違い**: これらは実際のインフラに障害を注入しますが、InfraSim は**完全に仮想環境（メモリ上）で実行**するため、本番・ステージング環境に一切影響を与えません。

### Key Features

- **Zero Risk** - 実インフラに触れない完全仮想シミュレーション
- **150+ Scenarios** - 30カテゴリのカオスシナリオを自動生成
- **Dependency Graph** - NetworkX による依存関係グラフ解析と連鎖障害予測
- **Risk Scoring** - 影響度 × 拡散率 × 発生確率の3軸定量評価
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
│ Terraform    │    │ Dependencies    │    │ Feed Scenarios   │
│ YAML Loader  │    │ NetworkX Graph  │    │ Risk Scoring     │
└─────────────┘    └─────────────────┘    └──────────────────┘
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
| `infrasim load <yaml>` | Load infrastructure from YAML |
| `infrasim tf-import` | Import from Terraform state |
| `infrasim tf-plan <plan>` | Analyze Terraform plan impact |
| `infrasim simulate` | Run chaos simulation |
| `infrasim demo` | Run demo with sample infrastructure |
| `infrasim show` | Display infrastructure summary |
| `infrasim report` | Generate HTML report |
| `infrasim serve` | Launch web dashboard |
| `infrasim feed-update` | Update scenarios from security news |
| `infrasim feed-list` | Show stored feed scenarios |
| `infrasim feed-sources` | Show configured news sources |
| `infrasim feed-clear` | Clear feed scenario store |

## Requirements

- Python 3.11+
- Dependencies: typer, rich, pydantic, networkx, psutil, fastapi, uvicorn, jinja2, httpx, pyyaml

## License

MIT License - see [LICENSE](LICENSE)
