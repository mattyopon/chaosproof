# FaultRay クイックスタートガイド

## インストール

### pip（推奨）
```bash
pip install faultray
```

### Docker
```bash
docker compose up web
# ブラウザで http://localhost:8000 にアクセス
```

### ソースから
```bash
git clone https://github.com/mattyopon/faultray.git
cd faultray
pip install -e ".[dev]"
```

## 最初のシミュレーション

### 1. デモを実行
```bash
faultray demo
```

6コンポーネント構成（nginx, API, DB, Cache, Queue, Worker）に対して2,000+のシナリオを実行します。

### 2. 自分のインフラを定義

`infra.yaml` を作成:
```yaml
name: my-platform
components:
  - id: lb
    type: load_balancer
    replicas: 2
  - id: api
    type: application
    replicas: 3
    dependencies: [lb, db, cache]
  - id: db
    type: database
    replicas: 2
  - id: cache
    type: cache
    replicas: 3
```

### 3. シミュレーション実行
```bash
# 静的シミュレーション（カスケード障害分析）
faultray load infra.yaml
faultray simulate --html report.html

# 動的シミュレーション（トラフィックパターン付き）
faultray dynamic infra.yaml --traffic diurnal --duration 24h

# 運用シミュレーション（7日間）
faultray ops-sim infra.yaml --days 7

# キャパシティ計画
faultray capacity infra.yaml --growth 0.15 --slo 99.9

# コスト影響分析
faultray cost-report infra.yaml --revenue-per-hour 50000
```

### 4. Webダッシュボード
```bash
faultray serve --port 8000
# ブラウザで http://localhost:8000 にアクセス
```

## CLIコマンド一覧

| コマンド | 説明 |
|---------|------|
| `faultray demo` | デモ実行（6コンポーネント構成） |
| `faultray demo --web` | デモ + Webダッシュボード |
| `faultray load <yaml>` | インフラ定義をロード |
| `faultray simulate` | 静的シミュレーション（カスケード分析） |
| `faultray dynamic <yaml>` | 動的シミュレーション（時系列） |
| `faultray ops-sim <yaml>` | 運用シミュレーション（日〜週単位） |
| `faultray whatif <yaml>` | What-If分析（パラメータスイープ） |
| `faultray capacity <yaml>` | キャパシティ計画（成長予測） |
| `faultray cost-report <yaml>` | コスト影響分析 |
| `faultray tf-import` | Terraform stateインポート |
| `faultray tf-plan <plan>` | Terraform plan影響分析 |
| `faultray scan` | ローカルシステムスキャン |
| `faultray feed-update` | セキュリティフィード更新 |
| `faultray serve` | Webダッシュボード起動 |
| `faultray report` | HTMLレポート生成 |

## 出力例

```
+-------------- FaultRay Chaos Simulation Report --------------+
| Resilience Score: 36/100                                     |
| Scenarios tested: 2,000+                                     |
| Critical: 7  Warning: 66  Passed: 77                        |
+--------------------------------------------------------------+

CRITICAL FINDINGS

  10.0/10 CRITICAL  Traffic spike (10x)
  Cascade path:
  +-- DOWN nginx (LB)
  +-- DOWN api-server-1
  +-- DOWN api-server-2
  +-- DOWN PostgreSQL (primary)
  +-- DOWN Redis (cache)
  +-- DOWN RabbitMQ
```

## 動作要件

- Python 3.11以上
- 依存パッケージ: typer, rich, pydantic, networkx, psutil, fastapi, uvicorn, jinja2, httpx, pyyaml, sqlalchemy, aiosqlite

## クラウドプロバイダー連携（オプション）

```bash
# AWS
pip install "faultray[aws]"

# GCP
pip install "faultray[gcp]"

# Azure
pip install "faultray[azure]"

# Kubernetes
pip install "faultray[k8s]"

# 全クラウド
pip install "faultray[all-clouds]"
```

## 次のステップ

- [5つのシミュレーションエンジン](engines.md) -- 各エンジンの詳細と使い方
- [Terraform統合ガイド](../integrations/terraform.md) -- Terraform stateからのインポート
- [コンプライアンス評価](compliance.md) -- SOC 2/ISO 27001/PCI DSS/DORA/HIPAA/GDPR準拠チェック
- [API リファレンス](api.md) -- REST APIエンドポイント一覧
- [業界別ユースケース](usecases.md) -- 金融・医療・SaaS・EC向けの活用事例
