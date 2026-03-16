# FaultRay 業界別ユースケース

FaultRayは業界を問わずインフラの障害耐性を評価できますが、特にコンプライアンス要件やSLA保証が厳しい業界で大きな価値を発揮します。ここでは代表的な4業界の活用事例を紹介します。

---

## 金融機関

### 課題

- **DORA（Digital Operational Resilience Act）への準拠**: EU圏の金融機関は2025年1月からDORA対応が必須
- **PCI DSS準拠**: クレジットカード決済処理のセキュリティ要件
- **ダウンタイムコストが極めて高い**: 1時間のダウンタイムが数千万〜数億円の損失に直結
- **レギュレーターへの報告義務**: インシデント発生時、規制当局への報告が必要

### FaultRayの活用方法

#### 1. DORA準拠のレジリエンステスト

DORAが求める「定期的なICTツールとシステムのテスト」を、本番環境に触れることなく実施できます。

```bash
# 金融基幹システムの定義をロード
faultray load banking-core.yaml

# DORA準拠評価
faultray simulate -m banking-core.json --compliance dora --output dora-report.html

# 動的シミュレーション（取引ピーク時）
faultray dynamic banking-core.yaml --traffic diurnal --duration 24h

# コスト影響分析（時間単位の収益を設定）
faultray cost-report banking-core.yaml --revenue-per-hour 5000000
```

#### 2. 決済システムのSPOF分析

```yaml
# payment-system.yaml
components:
  - id: api-gateway
    type: load_balancer
    replicas: 2
  - id: payment-api
    type: application
    replicas: 3
    dependencies: [api-gateway, payment-db, fraud-engine]
  - id: payment-db
    type: database
    replicas: 2
    compliance_tags:
      pci_scope: true
    security:
      encryption_at_rest: true
      network_segmented: true
  - id: fraud-engine
    type: application
    replicas: 2
```

#### 3. ダウンタイムコストの定量化

```bash
# 年間の障害コストを算出
faultray cost-report payment-system.yaml \
  --revenue-per-hour 5000000 \
  --output cost-impact.html
```

**出力イメージ**:
```
予想年間障害コスト:     $2,400,000
最悪ケース年間コスト:    $12,000,000
SLAペナルティリスク:     $500,000/年

トップリスクシナリオ:
  1. 全リージョン障害      $5,000,000/インシデント
  2. 決済DB障害           $2,500,000/インシデント
  3. 不正検知エンジン障害  $1,000,000/インシデント
```

### 得られる価値

- **DORA準拠エビデンスの自動生成**: 規制当局への提出資料を効率的に作成
- **リスクの定量化**: 経営層に対して「年間X円のリスクをY円の投資で回避できる」と説明
- **決済PCI DSS準拠の証明**: カード会員データ環境の保護状況をシミュレーション結果で証明

---

## 医療機関

### 課題

- **HIPAA準拠**: ePHI（電子保護対象医療情報）の技術的安全管理措置
- **EHR（電子健康記録）システムの可用性**: 患者ケアに直結するため、ダウンタイムは許容できない
- **災害復旧計画**: 自然災害やランサムウェア攻撃からの復旧体制
- **複雑な相互接続**: HIS、PACS、RIS、薬局システム等の多系統連携

### FaultRayの活用方法

#### 1. HIPAA準拠の技術的安全管理措置評価

```bash
# 医療情報システムの評価
faultray load ehr-system.yaml

# HIPAA準拠評価
faultray simulate -m ehr-system.json --compliance hipaa --output hipaa-report.html

# 災害復旧シナリオ
faultray dynamic ehr-system.yaml --traffic constant --duration 168h
```

#### 2. EHRシステムの定義例

```yaml
# ehr-system.yaml
components:
  - id: web-portal
    type: load_balancer
    replicas: 2
  - id: ehr-api
    type: application
    replicas: 3
    dependencies: [web-portal, patient-db, pacs, pharmacy]
  - id: patient-db
    type: database
    replicas: 2
    compliance_tags:
      contains_pii: true
    security:
      encryption_at_rest: true
      network_segmented: true
  - id: pacs
    type: application
    replicas: 2
    # 医用画像保管通信システム
  - id: pharmacy
    type: application
    replicas: 2
    # 薬局連携システム
  - id: backup-region
    type: application
    replicas: 1
    # DRリージョン
```

#### 3. ランサムウェア耐性テスト

```bash
# 全コンポーネント同時障害（ランサムウェアシナリオ）
faultray simulate --scenarios "total_meltdown"

# 復旧シナリオの評価
faultray whatif ehr-system.yaml --parameter mttr_factor --values "1.0,2.0,4.0,8.0"
```

### 得られる価値

- **HIPAA監査対応の効率化**: 技術的安全管理措置のエビデンスを自動生成
- **患者安全の保証**: EHRシステムの可用性上限を数学的に証明し、患者ケアへの影響を最小化
- **DR計画の妥当性検証**: 災害時のRTO/RPOが目標を満たせるか事前に確認
- **ランサムウェア対策**: 全系統停止時の復旧能力を事前にシミュレーション

---

## SaaS企業

### 課題

- **SLA保証**: 顧客契約のSLA（99.9%〜99.99%）を確実に達成する必要がある
- **マルチテナント耐性**: 特定テナントの異常が他テナントに影響しないことの証明
- **SOC 2 Type II認証**: 顧客（特に大企業）がSOC 2レポートを要求
- **スケーラビリティ**: 急成長時にインフラがボトルネックにならないことの保証

### FaultRayの活用方法

#### 1. SLA保証のシミュレーション

```bash
# SaaS基盤の定義をロード
faultray load saas-platform.yaml

# 99.9% SLOでの7日間運用シミュレーション
faultray ops-sim saas-platform.yaml --days 30 --step 5min

# 成長予測（月10%成長）
faultray capacity saas-platform.yaml --growth 0.10 --monthly --slo 99.9
```

#### 2. マルチテナント構成の定義例

```yaml
# saas-platform.yaml
components:
  - id: cdn
    type: load_balancer
    replicas: 2
  - id: api-gateway
    type: load_balancer
    replicas: 3
    dependencies: [cdn]
  - id: tenant-router
    type: application
    replicas: 3
    dependencies: [api-gateway]
  - id: app-service
    type: application
    replicas: 5
    dependencies: [tenant-router, primary-db, cache-cluster, queue]
  - id: primary-db
    type: database
    replicas: 2
  - id: cache-cluster
    type: cache
    replicas: 3
  - id: queue
    type: queue
    replicas: 3
  - id: worker
    type: application
    replicas: 3
    dependencies: [queue, primary-db]
```

#### 3. SOC 2 + エラーバジェット管理

```bash
# SOC 2準拠評価
faultray simulate -m saas-platform.json --compliance soc2 --output soc2-report.html

# エラーバジェットシミュレーション（99.9% SLO = 月間43分のダウンタイム許容）
faultray ops-sim saas-platform.yaml --days 30

# What-If分析（レプリカ数の感度分析）
faultray whatif saas-platform.yaml --parameter replicas --values "2,3,5,8"
```

#### 4. CI/CDパイプラインへの統合

```yaml
# .github/workflows/resilience-gate.yml
name: Resilience Gate
on: [pull_request]
jobs:
  faultray:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install FaultRay
        run: pip install faultray
      - name: Resilience Check
        run: |
          faultray load infra.yaml
          faultray evaluate --threshold 70
          faultray evaluate --compliance soc2 --threshold 80
```

### 得られる価値

- **SLA違反の防止**: 契約前にSLA達成可能性を数学的に検証
- **SOC 2監査の効率化**: コンプライアンスレポートを自動生成し監査コストを削減
- **スケーリング計画の根拠**: 「いつ何台追加すべきか」をデータで示す
- **リリースゲート**: PRごとにレジリエンスチェックを自動実行

---

## EC/小売

### 課題

- **セール・イベント時のトラフィック急増**: ブラックフライデー、タイムセール、TV放映後の急増
- **決済システムの信頼性**: カート放棄率の低減、決済失敗の最小化
- **在庫管理システムとの連携**: 在庫不整合が発生すると二重販売のリスク
- **ダウンタイムの直接的な売上損失**: 1分のダウンタイムが売上に直結

### FaultRayの活用方法

#### 1. ブラックフライデー耐性テスト

```bash
# EC基盤をロード
faultray load ec-platform.yaml

# 通常の10倍トラフィック（ブラックフライデー想定）
faultray dynamic ec-platform.yaml --traffic spike --duration 12h

# フラッシュセール想定（バイラル急増）
faultray dynamic ec-platform.yaml --traffic flash_crowd --duration 4h

# DDoS耐性テスト
faultray dynamic ec-platform.yaml --traffic ddos_volumetric --duration 2h
```

#### 2. EC基盤の定義例

```yaml
# ec-platform.yaml
components:
  - id: cdn
    type: load_balancer
    replicas: 2
  - id: web-frontend
    type: application
    replicas: 5
    dependencies: [cdn]
  - id: product-api
    type: application
    replicas: 4
    dependencies: [web-frontend, product-db, cache, search-engine]
  - id: cart-api
    type: application
    replicas: 4
    dependencies: [web-frontend, cart-db, cache]
  - id: payment-api
    type: application
    replicas: 3
    dependencies: [cart-api, payment-gateway, order-db]
  - id: product-db
    type: database
    replicas: 2
  - id: cart-db
    type: database
    replicas: 2
  - id: order-db
    type: database
    replicas: 2
    compliance_tags:
      pci_scope: true
    security:
      encryption_at_rest: true
  - id: cache
    type: cache
    replicas: 3
  - id: search-engine
    type: application
    replicas: 2
  - id: payment-gateway
    type: application
    replicas: 2
    # 外部決済ゲートウェイ連携
  - id: inventory-queue
    type: queue
    replicas: 3
  - id: inventory-worker
    type: application
    replicas: 3
    dependencies: [inventory-queue, product-db]
```

#### 3. 決済障害のコスト分析

```bash
# セール期間中のコスト影響分析（時間収益 = 通常の5倍）
faultray cost-report ec-platform.yaml --revenue-per-hour 250000

# 決済ゲートウェイ障害の影響分析
faultray whatif ec-platform.yaml --parameter replicas --values "1,2,3"
```

#### 4. キャパシティ計画（セール前の増強計画）

```bash
# 年末商戦に向けたキャパシティ計画
faultray capacity ec-platform.yaml --growth 0.50 --slo 99.95

# 出力例:
# cart-api: 4 -> 8 replicas needed (Black Friday peak)
# product-db: disk exhaustion in 6 months at current growth
# cache: 3 replicas OK (quorum guard maintained)
```

### 得られる価値

- **セール前の安心感**: トラフィック10倍にもインフラが耐えられることを事前に証明
- **売上機会損失の最小化**: 決済システムのSPOFを排除し、カート放棄率を低減
- **キャパシティ計画の精度向上**: 感覚ではなくデータに基づいたスケーリング判断
- **PCI DSS準拠**: 決済関連コンポーネントのコンプライアンス自動評価

---

## 共通の導入パターン

### ステップ1: 現状評価

```bash
# 既存インフラをスキャン（AWS/GCP/K8s）
faultray scan --provider aws --output current-infra.json

# または Terraform stateからインポート
faultray tf-import --state terraform.tfstate --output current-infra.json

# 現状のレジリエンススコアを確認
faultray simulate -m current-infra.json --html baseline-report.html
```

### ステップ2: ギャップ特定

```bash
# コンプライアンス評価
faultray simulate -m current-infra.json --compliance soc2,iso27001 --output compliance-report.html

# コスト影響分析
faultray cost-report current-infra.yaml --revenue-per-hour YOUR_REVENUE

# What-If分析で改善可能領域を特定
faultray whatif current-infra.yaml --defaults
```

### ステップ3: 改善計画

What-If分析の結果から、最もコスト効率の高い改善策を特定:

- SPOFの冗長化（レプリカ追加）
- サーキットブレーカーの導入
- DR戦略の策定
- オートスケーリングの設定

### ステップ4: 継続的検証

```bash
# CI/CDパイプラインに統合
faultray evaluate -m model.json --threshold 70 --compliance soc2 --threshold 80
```

---

## 次のステップ

- [クイックスタート](getting-started.md) -- インストールと最初のシミュレーション
- [5つのシミュレーションエンジン](engines.md) -- 各エンジンの詳細仕様
- [コンプライアンス評価](compliance.md) -- 規制フレームワーク準拠の詳細
- [API リファレンス](api.md) -- REST APIエンドポイント
