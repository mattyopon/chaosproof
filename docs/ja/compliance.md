# FaultRay コンプライアンス評価ガイド

FaultRayは、インフラの障害耐性シミュレーション結果を規制フレームワークの要件にマッピングし、準拠状況を自動評価します。監査対応のエビデンスとして活用でき、改善が必要な領域（ギャップ）と具体的な改善提案を出力します。

---

## 対応フレームワーク

| フレームワーク | 対象業界 | FaultRayの評価範囲 |
|--------------|---------|-------------------|
| **SOC 2 Type II** | SaaS・クラウドサービス全般 | 可用性基準（A1.1, A1.2）、セキュリティ（CC6.1, CC6.6）、監視（CC7.2）、処理の完全性（PI1.3） |
| **ISO 27001** | 全業界（ISMS認証取得企業） | 事業継続（A.17）、運用セキュリティ（A.12）、暗号化（A.10）、アクセス制御（A.9） |
| **PCI DSS** | クレジットカード決済を扱う企業 | セキュアシステム（Req-6）、監査証跡（Req-10）、PCI対象コンポーネントの暗号化・ネットワーク分離 |
| **DORA** | EU圏の金融機関 | ICTリスク管理、インシデント報告、デジタル運用レジリエンステスト、第三者リスク管理 |
| **HIPAA** | 医療機関・医療データ取扱企業 | 技術的安全管理措置（暗号化、アクセス制御、監査ログ）、災害復旧計画、データバックアップ |
| **GDPR** | EU圏の個人データ取扱企業 | 適切な技術的・組織的措置（Art.32）、データ保護影響評価、セキュリティインシデント通知体制 |

---

## 各フレームワークの詳細

### SOC 2 Type II

**対象企業**: SaaS/クラウドサービスを提供する企業（顧客がSOC 2レポートを要求するケースが多い）

**FaultRayが評価するコントロール**:

| コントロールID | 説明 | FaultRayの検証内容 |
|--------------|------|-------------------|
| CC6.1 | 論理的・物理的アクセス制御 | Auth/WAFコンポーネントの存在 |
| CC6.6 | 通信データの暗号化 | TLS（ポート443）の使用状況 |
| CC7.2 | システム監視と異常検出 | 監視コンポーネント（Prometheus, OTel等）の存在 |
| A1.2 | 可用性：冗長性とフェイルオーバー | レプリカ数 >= 2の確認、フェイルオーバー設定 |
| PI1.3 | 処理の完全性：サーキットブレーカー | 依存関係エッジのサーキットブレーカーカバレッジ |

**実行方法**:
```bash
faultray simulate -m model.json --compliance soc2 --output soc2-report.html
```

### ISO 27001

**対象企業**: ISMS（情報セキュリティマネジメントシステム）認証を取得・維持する企業

**FaultRayが評価するコントロール**:

| コントロールID | 説明 | FaultRayの検証内容 |
|--------------|------|-------------------|
| A.17.1.1 | 情報セキュリティ継続の計画 | DRリージョンの存在、フェイルオーバー設定 |
| A.17.1.2 | 冗長性の実装 | 依存コンポーネントのレプリカ数 |
| A.17.2.1 | 情報処理施設の可用性 | オートスケーリング設定 |
| A.10.1.1 | 暗号化制御方針 | TLS暗号化の適用状況 |
| A.12.4.1 | イベントログ取得 | 集中ログ収集・監視コンポーネントの存在 |
| A.9.1.1 | アクセス制御方針 | 認証・認可コンポーネントの存在 |

**実行方法**:
```bash
faultray simulate -m model.json --compliance iso27001 --output iso27001-report.html
```

### PCI DSS

**対象企業**: クレジットカード情報を保存・処理・伝送する企業

**FaultRayが評価するコントロール**:

| コントロールID | 説明 | FaultRayの検証内容 |
|--------------|------|-------------------|
| Req-1.3 | カード会員データ環境への直接パブリックアクセスの禁止 | PCI対象コンポーネントのネットワーク分離 |
| Req-3.4 | PANの読取不能化 | PCI対象コンポーネントの保存時暗号化 |
| Req-6.1 | セキュリティ脆弱性の特定とアドレス | 監視・サーキットブレーカー |
| Req-6.2 | 既知の脆弱性からの保護 | Auth/WAF + TLS暗号化 |
| Req-6.5 | 一般的なコーディング脆弱性対策 | サーキットブレーカー（エラーハンドリング） |
| Req-10.1 | 監査証跡の実装 | 監視・ロギングコンポーネント |
| Req-10.5 | 監査証跡の改ざん防止 | TLS暗号化 |
| Req-10.6 | ログ・セキュリティイベントの定期レビュー | 監視コンポーネント |

**PCI対象コンポーネントの指定方法**:
```yaml
components:
  - id: payment-db
    type: database
    compliance_tags:
      pci_scope: true
    security:
      encryption_at_rest: true
      network_segmented: true
```

**実行方法**:
```bash
faultray simulate -m model.json --compliance pci_dss --output pci-report.html
```

### DORA（Digital Operational Resilience Act）

**対象企業**: EU圏の金融機関（銀行、保険会社、投資会社、フィンテック）

**FaultRayが評価する要件**:

| 要件 | 説明 | FaultRayの検証内容 |
|------|------|-------------------|
| ICTリスク管理 | ICT資産の特定・保護 | インフラ構成の可視化、冗長性評価 |
| インシデント報告 | 重大ICTインシデントの報告体制 | 監視・アラートコンポーネントの存在 |
| レジリエンステスト | 定期的なICTツールとシステムのテスト | シミュレーション結果のエビデンス |
| 第三者リスク管理 | クラウドプロバイダー等の依存リスク | 外部依存のSPOF分析 |

**実行方法**:
```bash
faultray simulate -m model.json --compliance dora --output dora-report.html
```

### HIPAA

**対象企業**: 米国の医療機関、医療データを扱う企業（保険会社、HIT企業、EHRベンダー）

**FaultRayが評価する要件**:

| 要件 | 説明 | FaultRayの検証内容 |
|------|------|-------------------|
| 技術的安全管理措置 | アクセス制御、監査証跡、伝送セキュリティ | Auth/WAF、暗号化、監視コンポーネント |
| 緊急時対応計画 | データバックアップ、災害復旧、事業継続 | DRリージョン、フェイルオーバー設定、レプリカ構成 |
| 伝送セキュリティ | ePHIの伝送時保護 | TLS暗号化の適用状況 |

**実行方法**:
```bash
faultray simulate -m model.json --compliance hipaa --output hipaa-report.html
```

### GDPR

**対象企業**: EU圏の個人データを取り扱う企業（所在地を問わない）

**FaultRayが評価する要件**:

| 条項 | 説明 | FaultRayの検証内容 |
|------|------|-------------------|
| Art.32 | 適切な技術的・組織的措置 | 暗号化、冗長性、フェイルオーバー、監視 |
| Art.35 | データ保護影響評価 | インフラリスク評価のエビデンス |
| Art.33/34 | セキュリティインシデント通知 | 監視・アラートコンポーネント |

**実行方法**:
```bash
faultray simulate -m model.json --compliance gdpr --output gdpr-report.html
```

---

## 複数フレームワーク同時評価

```bash
# SOC 2 + ISO 27001 + PCI DSS を同時評価
faultray simulate -m model.json --compliance soc2,iso27001,pci_dss --output multi-compliance.html
```

---

## レポートの内容

各コンプライアンスレポートには以下が含まれます:

### 1. コントロールマッピング
レジリエンス検証結果を各フレームワークのコントロールに対応付け

### 2. エビデンス
シミュレーション結果をコントロール準拠のエビデンスとして提示（監査提出用）

### 3. ギャップ分析
現状のアーキテクチャでは満たせないコントロールを特定

### 4. 改善提案
ギャップを埋めるための具体的なインフラ変更を提示:
- 「レプリカを2以上に設定して冗長性を確保してください」
- 「サーキットブレーカーを全依存関係エッジに設定してください」
- 「TLS暗号化（ポート443）を全外部向けコンポーネントに適用してください」

### 5. 監査証跡
タイムスタンプ付きのシミュレーション実行記録

---

## CI/CDパイプラインへの統合

コンプライアンスチェックをデプロイ前の品質ゲートとして自動実行できます:

```bash
# コンプライアンススコアが80%未満ならデプロイを阻止
faultray evaluate -m model.json --compliance soc2 --threshold 80
```

終了コード:
- `0`: コンプライアンススコアが閾値以上
- `3`: コンプライアンススコアが閾値未満（デプロイブロック）

### GitHub Actions例

```yaml
- name: Compliance Gate
  run: |
    faultray tf-import --state terraform.tfstate --output /tmp/model.json
    faultray evaluate -m /tmp/model.json --compliance soc2,pci_dss --threshold 80
```

---

## Pythonから直接使用

```python
from faultray.simulator.compliance_engine import ComplianceEngine
from faultray.model.graph import InfraGraph

graph = InfraGraph.from_yaml("infra.yaml")
engine = ComplianceEngine(graph)

# SOC 2チェック
soc2_report = engine.check_soc2()
print(f"SOC 2 準拠率: {soc2_report.compliance_percent}%")
print(f"  合格: {soc2_report.passed} / 不合格: {soc2_report.failed} / 一部適合: {soc2_report.partial}")

for check in soc2_report.checks:
    if check.status == "fail":
        print(f"  [{check.control_id}] {check.description}")
        print(f"    改善提案: {check.recommendation}")

# ISO 27001チェック
iso_report = engine.check_iso27001()

# PCI DSSチェック
pci_report = engine.check_pci_dss()
```

### ComplianceFrameworksEngine（6フレームワーク対応）

```python
from faultray.simulator.compliance_frameworks import (
    ComplianceFramework,
    ComplianceFrameworksEngine,
    InfrastructureEvidence,
)

evidence = InfrastructureEvidence(
    has_encryption=True,
    has_redundancy=True,
    has_monitoring=True,
    has_access_control=True,
)
engine = ComplianceFrameworksEngine(evidence)

# DORA評価
dora_report = engine.assess(ComplianceFramework.DORA)
print(f"DORA 準拠スコア: {dora_report.overall_score:.1f}%")
print(f"  重大ギャップ: {dora_report.critical_gaps}")
print(f"  改善提案: {dora_report.recommendations}")
```

---

## 次のステップ

- [クイックスタート](getting-started.md) -- インストールと最初のシミュレーション
- [5つのシミュレーションエンジン](engines.md) -- 各エンジンの詳細
- [API リファレンス](api.md) -- REST APIからのコンプライアンス評価
- [業界別ユースケース](usecases.md) -- 金融・医療・SaaS向け活用事例
