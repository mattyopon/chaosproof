# FaultRay REST API リファレンス

FaultRayはFastAPIベースのREST APIを提供し、シミュレーション・コンプライアンス評価・コスト分析をプログラマティックに実行できます。

---

## サーバー起動

```bash
# デフォルト（ポート8000）
faultray serve

# ポート指定
faultray serve --port 8080

# Docker
docker compose up web
```

起動後、以下のURLでアクセスできます:

| URL | 説明 |
|-----|------|
| `http://localhost:8000` | Webダッシュボード（D3.jsインタラクティブグラフ） |
| `http://localhost:8000/docs` | Swagger UI（OpenAPIドキュメント） |
| `http://localhost:8000/redoc` | ReDoc（APIドキュメント） |
| `http://localhost:8000/api/v1/` | APIベースURL |

---

## 認証

APIリクエストにはBearerトークンが必要です:

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
     http://localhost:8000/api/v1/health
```

ローカル開発時は認証をスキップできます（環境変数 `FAULTRAY_AUTH_DISABLED=1`）。

---

## レート制限

デフォルトで**60リクエスト/分/クライアント**のレート制限が適用されます。制限を超えた場合は `429 Too Many Requests` が返されます。

---

## エンドポイント一覧

### ヘルスチェック

#### `GET /api/v1/health`

サービスの稼働状態とバージョンを確認します。

**レスポンス**:

```json
{
  "status": "healthy",
  "version": "10.2.0",
  "engines": 5
}
```

| フィールド | 型 | 説明 |
|-----------|---|------|
| `status` | string | サービス状態（`healthy` / `unhealthy`） |
| `version` | string | FaultRayバージョン |
| `engines` | integer | 利用可能なエンジン数 |

**cURLサンプル**:
```bash
curl http://localhost:8000/api/v1/health
```

---

### シミュレーション実行

#### `POST /api/v1/simulate`

インフラトポロジーに対してカオスシミュレーションを実行します。

**リクエストボディ**:

```json
{
  "topology_yaml": "components:\n  - id: api\n    type: application\n    replicas: 3\n  - id: db\n    type: database\n    replicas: 2\ndependencies:\n  - source: api\n    target: db\n    type: requires",
  "scenarios": "all",
  "engines": ["cascade"]
}
```

| フィールド | 型 | 必須 | デフォルト | 説明 |
|-----------|---|------|---------|------|
| `topology_yaml` | string | はい | - | YAML形式のインフラトポロジー定義 |
| `scenarios` | string | いいえ | `"all"` | シナリオフィルター: `all`, `critical`, またはカンマ区切りのシナリオ名 |
| `engines` | list[string] | いいえ | `["cascade"]` | 使用エンジン: `cascade`, `dynamic`, `ops`, `whatif`, `capacity` |

**レスポンス**:

```json
{
  "resilience_score": 72.5,
  "scenarios_tested": 152,
  "critical_count": 3,
  "warning_count": 45,
  "passed_count": 104,
  "availability_nines": 3.8
}
```

| フィールド | 型 | 説明 |
|-----------|---|------|
| `resilience_score` | float | 総合レジリエンススコア（0〜100） |
| `scenarios_tested` | integer | テスト済みシナリオ数 |
| `critical_count` | integer | CRITICALレベルの検出数 |
| `warning_count` | integer | WARNINGレベルの検出数 |
| `passed_count` | integer | PASSEDのシナリオ数 |
| `availability_nines` | float | 算出された可用性（nines単位。例: 3.8 = 99.98%） |

**cURLサンプル**:
```bash
curl -X POST http://localhost:8000/api/v1/simulate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "topology_yaml": "components:\n  - id: api\n    type: application\n    replicas: 3\n  - id: db\n    type: database\n    replicas: 2",
    "scenarios": "all",
    "engines": ["cascade"]
  }'
```

---

### コンプライアンス評価

#### `POST /api/v1/compliance/assess`

インフラのコンプライアンス準拠状況を評価します。

**リクエストボディ**:

```json
{
  "framework": "soc2",
  "evidence": {
    "has_encryption": true,
    "has_redundancy": true,
    "has_monitoring": true,
    "has_access_control": true,
    "has_backup": true,
    "has_dr_plan": false,
    "has_incident_response": true
  }
}
```

| フィールド | 型 | 必須 | 説明 |
|-----------|---|------|------|
| `framework` | string | はい | フレームワーク名: `soc2`, `iso27001`, `pci_dss`, `dora`, `hipaa`, `gdpr` |
| `evidence` | object | いいえ | インフラ構成のエビデンスマップ |

**evidenceフィールド**:

| フィールド | 型 | 説明 |
|-----------|---|------|
| `has_encryption` | boolean | TLS/暗号化が有効か |
| `has_redundancy` | boolean | 冗長構成があるか |
| `has_monitoring` | boolean | 監視が設定されているか |
| `has_access_control` | boolean | アクセス制御があるか |
| `has_backup` | boolean | バックアップが設定されているか |
| `has_dr_plan` | boolean | DR計画が策定されているか |
| `has_incident_response` | boolean | インシデント対応体制があるか |

**レスポンス**:

```json
{
  "framework": "soc2",
  "overall_score": 78.5,
  "compliant_count": 8,
  "non_compliant_count": 2,
  "critical_gaps": [
    "DR plan not established",
    "Backup recovery not tested"
  ],
  "recommendations": [
    "Implement disaster recovery plan with regular testing",
    "Schedule quarterly backup recovery drills"
  ]
}
```

| フィールド | 型 | 説明 |
|-----------|---|------|
| `framework` | string | 評価したフレームワーク名 |
| `overall_score` | float | 総合準拠スコア（0〜100） |
| `compliant_count` | integer | 準拠コントロール数 |
| `non_compliant_count` | integer | 非準拠コントロール数 |
| `critical_gaps` | list[string] | 重大なギャップ一覧 |
| `recommendations` | list[string] | 改善提案一覧 |

**cURLサンプル**:
```bash
curl -X POST http://localhost:8000/api/v1/compliance/assess \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "framework": "dora",
    "evidence": {
      "has_encryption": true,
      "has_redundancy": true,
      "has_monitoring": true,
      "has_access_control": true
    }
  }'
```

---

### コスト影響分析

#### `POST /api/v1/cost/analyze`

インフラ障害によるコスト影響（収益損失、SLAペナルティ、復旧コスト）を分析します。

**リクエストボディ**:

```json
{
  "topology_yaml": "components:\n  - id: api\n    type: application\n    replicas: 3\n  - id: db\n    type: database\n    replicas: 2",
  "revenue_per_hour": 50000,
  "incidents_per_year": 12
}
```

| フィールド | 型 | 必須 | デフォルト | 説明 |
|-----------|---|------|---------|------|
| `topology_yaml` | string | はい | - | YAML形式のインフラトポロジー |
| `revenue_per_hour` | float | いいえ | 10000 | 時間あたりの収益（USD） |
| `incidents_per_year` | float | いいえ | 12 | 年間予想インシデント数 |

**レスポンス**:

```json
{
  "expected_annual_cost": 240000.0,
  "worst_case_annual_cost": 1200000.0,
  "top_scenarios": [
    {"name": "Full region outage", "cost": 100000},
    {"name": "Database failure", "cost": 50000}
  ]
}
```

| フィールド | 型 | 説明 |
|-----------|---|------|
| `expected_annual_cost` | float | 予想年間障害コスト（USD） |
| `worst_case_annual_cost` | float | 最悪ケースの年間コスト（USD） |
| `top_scenarios` | list[object] | コスト影響の大きいシナリオ上位 |

**cURLサンプル**:
```bash
curl -X POST http://localhost:8000/api/v1/cost/analyze \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "topology_yaml": "components:\n  - id: api\n    type: application\n    replicas: 3",
    "revenue_per_hour": 50000,
    "incidents_per_year": 12
  }'
```

---

## エラーレスポンス

全エラーは統一フォーマットで返されます:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Model must contain at least one node",
    "details": {}
  }
}
```

| HTTPステータス | エラーコード | 説明 |
|--------------|-----------|------|
| 400 | `VALIDATION_ERROR` | リクエストボディが不正 |
| 401 | `UNAUTHORIZED` | APIキーが無効または未指定 |
| 404 | `NOT_FOUND` | リソースが見つからない |
| 429 | `RATE_LIMITED` | レート制限超過 |
| 500 | `INTERNAL_ERROR` | サーバー内部エラー |

---

## Swagger UI / ReDoc

FaultRayはOpenAPI仕様を自動生成し、インタラクティブなAPIドキュメントを提供します。

### Swagger UI

`http://localhost:8000/docs` にアクセスすると、ブラウザ上でAPIを直接試すことができます。

- リクエストパラメータの入力フォーム
- レスポンスのライブプレビュー
- リクエスト/レスポンスのスキーマ表示

### ReDoc

`http://localhost:8000/redoc` にアクセスすると、より読みやすいドキュメント形式で閲覧できます。

---

## Pythonクライアント例

```python
import httpx

BASE_URL = "http://localhost:8000/api/v1"
HEADERS = {"Authorization": "Bearer YOUR_API_KEY"}

# ヘルスチェック
resp = httpx.get(f"{BASE_URL}/health", headers=HEADERS)
print(resp.json())

# シミュレーション実行
topology = """
components:
  - id: api
    type: application
    replicas: 3
  - id: db
    type: database
    replicas: 2
dependencies:
  - source: api
    target: db
    type: requires
"""

resp = httpx.post(
    f"{BASE_URL}/simulate",
    headers=HEADERS,
    json={
        "topology_yaml": topology,
        "scenarios": "all",
        "engines": ["cascade", "dynamic"],
    },
)
result = resp.json()
print(f"レジリエンススコア: {result['resilience_score']}")
print(f"テスト済みシナリオ: {result['scenarios_tested']}")
print(f"CRITICAL: {result['critical_count']}")

# コンプライアンス評価
resp = httpx.post(
    f"{BASE_URL}/compliance/assess",
    headers=HEADERS,
    json={
        "framework": "soc2",
        "evidence": {
            "has_encryption": True,
            "has_redundancy": True,
            "has_monitoring": True,
        },
    },
)
compliance = resp.json()
print(f"SOC 2 スコア: {compliance['overall_score']}%")
```

---

## 環境変数

| 環境変数 | デフォルト | 説明 |
|---------|---------|------|
| `FAULTRAY_AUTH_DISABLED` | `0` | `1`に設定するとAPI認証を無効化 |
| `FAULTRAY_PROMETHEUS_URL` | (未設定) | PrometheusのURL（設定するとバックグラウンド監視が起動） |
| `FAULTRAY_PROMETHEUS_INTERVAL` | `60` | Prometheus監視の取得間隔（秒） |

---

## 次のステップ

- [クイックスタート](getting-started.md) -- CLIからの基本的な使い方
- [5つのシミュレーションエンジン](engines.md) -- エンジンの詳細仕様
- [コンプライアンス評価](compliance.md) -- 規制フレームワーク対応の詳細
- [業界別ユースケース](usecases.md) -- 具体的な活用事例
