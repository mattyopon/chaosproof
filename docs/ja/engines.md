# FaultRay 5つのシミュレーションエンジン

FaultRayは5つのシミュレーションエンジンを統合し、インフラの障害耐性をあらゆる角度から評価します。各エンジンは独立して動作しますが、組み合わせることで包括的な耐性評価が可能です。

```
+-----------------------------------------------------+
|                    FaultRay                          |
+----------+----------+----------+--------------------+
| Cascade  | Dynamic  |   Ops    |  What-If           |
| Engine   | Engine   |  Engine  |  Engine            |
+----------+----------+----------+--------------------+
|              Capacity Engine                         |
+-----------------------------------------------------+
|          Dependency Graph (NetworkX)                 |
+----------+----------+----------+--------------------+
|   YAML   |Terraform |Prometheus| Cloud APIs         |
|  Loader  | Importer |Discovery |  (AWS/GCP/Azure)   |
+----------+----------+----------+--------------------+
```

---

## 1. Cascadeエンジン（静的シミュレーション）

### 概要

依存関係グラフ（NetworkX DAG）を通じた**障害伝搬のモデリング**を行うコアエンジンです。単一障害点（SPOF）の検出、複合障害シナリオの生成、カスケード障害パスの追跡を実行します。

### 仕組み

1. ターゲットコンポーネントを障害状態に設定
2. 依存関係エッジを通じて障害を伝搬（BFS/DFSトラバーサル）
3. 冗長性・フェイルオーバーパスを評価
4. エンドユーザーへの可用性影響を算出

### 生成されるシナリオ（30カテゴリ）

| カテゴリ | 例 |
|---------|---|
| **単一障害** | コンポーネントダウン、CPU飽和、OOM、ディスク満杯、ネットワーク分断 |
| **トラフィック** | 1.5x, 2x, 3x, 5x, 10x（DDoS級）のトラフィックスパイク |
| **複合障害** | 全ペアワイズ C(n,2) + トリプル C(n,3) の同時障害 |
| **DB固有** | ログ爆発、レプリケーション遅延、コネクション嵐、ロック競合 |
| **Cache固有** | キャッシュスタンピード、エビクション嵐、スプリットブレイン |
| **Queue固有** | バックプレッシャー、ポイズンメッセージ |
| **LB固有** | ヘルスチェック失敗、TLS証明書期限切れ、設定リロード失敗 |
| **App固有** | メモリリーク、スレッド枯渇、GCポーズ、不良デプロイ |
| **インフラ** | ゾーン障害、連鎖タイムアウト、全面メルトダウン、ローリングリスタート |
| **実世界** | ブラックフライデー（10x+キャッシュ圧力）、ノイジーネイバー |
| **セキュリティフィード** | CISA/NVD/Krebs等から自動生成 |

### 使い方

```bash
# YAML定義をロードしてシミュレーション
faultray load infra.yaml
faultray simulate --html report.html

# シナリオ絞り込み
faultray simulate --scenarios critical

# JSON出力
faultray simulate --json
```

### 出力

- **レジリエンススコア**: 0〜100（SPOF 30% + カスケード 25% + 冗長性 25% + 地理分散 20%の加重平均）
- **重大度レベル**: CRITICAL（7.0-10.0）/ WARNING（4.0-6.9）/ PASSED（0.0-3.9）
- **カスケードパス**: 障害伝搬の経路を視覚化
- **SPOF一覧**: 単一障害点の特定と改善提案

### 3層可用性限界モデル

Cascadeエンジンの最大の特徴は、**システムの可用性上限を数学的に証明する3層限界モデル**です。

| 層 | 名称 | 上限 | 説明 |
|---|---|---|---|
| **Layer 3** | 理論限界 | 6.65 nines | 完全な冗長性 + 瞬時フェイルオーバーを仮定（到達不可能な数学的上限） |
| **Layer 2** | ハードウェア限界 | 5.91 nines | コンポーネントMTBF x 冗長係数から算出される物理的上限 |
| **Layer 1** | ソフトウェア限界 | 4.00 nines | デプロイ失敗・設定ドリフト・ヒューマンエラーを考慮した実用上限 |

**活用例**: SLO目標が99.99%だがLayer 1限界が99.95%の場合、アーキテクチャ変更なしにはギャップを埋められないことが数学的に証明されます。

---

## 2. Dynamicエンジン（動的シミュレーション）

### 概要

**時間ステップ方式**のシミュレーションで、トラフィックパターン、オートスケーリング、サーキットブレーカー、フェイルオーバーを時系列で再現します。「ピーク時のトラフィックにインフラは耐えられるか？」という問いに答えます。

### 仕組み

1. 時間ステップごとにトラフィック量を算出
2. 各コンポーネントの負荷をメトリクスとして計算
3. オートスケーリングポリシーを適用
4. 過負荷コンポーネントの障害をトリガー
5. サーキットブレーカー・フェイルオーバーの動作をシミュレート

### 10種類のトラフィックモデル

| パターン | 説明 | ユースケース |
|---------|------|------------|
| `CONSTANT` | 定常トラフィック | ベースライン測定 |
| `RAMP` | 線形増加 | キャンペーン・新機能リリース |
| `SPIKE` | 瞬時スパイク | TV放映・SNSバズ |
| `WAVE` | 正弦波パターン | 周期的ワークロード |
| `DDoS_VOLUMETRIC` | 大量DDoSアタック | DDoS耐性テスト |
| `DDoS_SLOWLORIS` | Slowloris型DDoS | アプリケーション層DDoS |
| `FLASH_CROWD` | バイラル急増 | プレスリリース・バズ |
| `DIURNAL` | 日中サイクル | 通常運用パターン |
| `DIURNAL_WEEKLY` | 週間サイクル | 平日/週末の差異 |
| `GROWTH_TREND` | 長期成長 | オーガニック成長 |

### 使い方

```bash
# 24時間の日中パターンシミュレーション
faultray dynamic infra.yaml --traffic diurnal --duration 24h --step 1min

# DDoS耐性テスト
faultray dynamic infra.yaml --traffic ddos_volumetric --duration 2h

# ブラックフライデーシナリオ
faultray dynamic infra.yaml --traffic spike --duration 12h
```

### 出力例

時間ステップごとの状態推移：

```
[T=00:00] STABLE  | api: 45% CPU | db: 30% CPU | cache: 20% CPU
[T=08:00] STABLE  | api: 72% CPU | db: 55% CPU | cache: 35% CPU
[T=12:00] WARNING | api: 89% CPU | db: 78% CPU  -> autoscaling triggered
[T=12:05] STABLE  | api: 65% CPU (scaled 3->5) | db: 78% CPU
[T=18:00] STABLE  | api: 50% CPU | db: 40% CPU | cache: 25% CPU
```

---

## 3. Opsエンジン（運用シミュレーション）

### 概要

**数日〜数週間の長期運用**をシミュレートし、SLO準拠状況、インシデント発生パターン、デプロイイベントの影響を追跡します。「今月のエラーバジェットは持つか？」「週次デプロイが可用性に与える影響は？」に答えます。

### 仕組み

1. 長時間の時間ステップでシミュレーション実行
2. 確率的にインシデントを発生させる
3. デプロイイベント（ローリングアップデート等）を挿入
4. SLOに対する準拠率を継続計測
5. エラーバジェット消費量を追跡

### 使い方

```bash
# 7日間の運用シミュレーション（5分間隔）
faultray ops-sim infra.yaml --days 7 --step 5min

# デフォルト設定で実行
faultray ops-sim --defaults
```

### 出力例

```
=== 7-Day Operational Simulation ===

SLO Compliance: 99.82% (target: 99.9%)  BELOW TARGET
Error Budget Consumed: 127% (EXCEEDED)

Incidents:
  Day 1 12:34  SEV-2  API latency spike (95th: 2.3s)  MTTR: 45min
  Day 3 03:12  SEV-3  Cache eviction storm             MTTR: 15min
  Day 5 09:45  SEV-1  Database failover triggered       MTTR: 8min
  Day 6 14:00  ---    Deployment event (v2.1.3)        No impact

Recommendation:
  - Error budget exceeded. Freeze non-critical deployments until budget recovers.
  - Cache cluster needs capacity increase (eviction rate > 5%).
```

### ユースケース

- **SLO交渉前の可用性予測**: 「99.9% SLOを契約して大丈夫か？」を事前に検証
- **デプロイ頻度の最適化**: デプロイ間隔と可用性のトレードオフを分析
- **インシデント対応訓練**: 予測されるインシデントパターンの把握
- **エラーバジェット運用**: Google SRE方式のエラーバジェット消費シミュレーション

---

## 4. What-Ifエンジン（感度分析）

### 概要

**パラメータスイープ**により、「もし〜だったら？」という仮説検証を行います。MTTRを半分にしたら可用性はどう変わるか、レプリカ数を増やしたらリスクスコアはどう改善するか、といった感度分析を自動化します。

### 仕組み

1. 対象パラメータと値の範囲を指定
2. 各値でシミュレーションを再実行
3. パラメータ値とレジリエンススコアの関係をプロット
4. ブレークポイント（急激にリスクが変化する閾値）を検出

### 使い方

```bash
# MTTR係数のスイープ
faultray whatif infra.yaml --parameter mttr_factor --values "0.5,1.0,2.0,4.0"

# デフォルトパラメータスイープ
faultray whatif infra.yaml --defaults

# レプリカ数の感度分析
faultray whatif infra.yaml --parameter replicas --values "1,2,3,5"
```

### 出力例

```
=== What-If Analysis: mttr_factor ===

Parameter: mttr_factor (Mean Time To Recovery multiplier)

  Value  | Score | Delta |  Status
  -------+-------+-------+---------
  0.5    |  82   | +10   |  IMPROVED
  1.0    |  72   |  --   |  BASELINE
  2.0    |  58   | -14   |  DEGRADED
  4.0    |  31   | -41   |  CRITICAL

Breakpoint detected: mttr_factor > 2.5 causes cascade failure risk
Recommendation: Keep MTTR below 2.0x for acceptable resilience
```

### ユースケース

- **投資対効果の定量化**: 「レプリカを1台追加するとリスクスコアがどれだけ改善するか」
- **SLA交渉の根拠**: 「MTTR 30分を保証するとSLO達成率はいくつになるか」
- **障害対応時間の最適化**: 「復旧時間が2倍になった場合の影響度はどの程度か」
- **コスト最適化**: 「最小限の投資で最大限のスコア改善を得るにはどのパラメータを変えるべきか」

---

## 5. Capacityエンジン（キャパシティ計画）

### 概要

**成長予測とリソース枯渇予測**を行い、SLO準拠を維持しつつコスト最適化を実現するエンジンです。HAガード（最低2レプリカ）とクォーラムガード（最低3レプリカ）により、過剰なリソース削減を防止します。

### 仕組み

1. 現在のリソース使用率を基準に成長率を適用
2. 将来の各時点でのリソース使用率を予測
3. 枯渇予測日を算出
4. ライトサイジング推奨を生成（HA/クォーラムガード適用）
5. SLO準拠を確認

### HA & クォーラムガード

| ガード | 対象 | 最低レプリカ数 | 理由 |
|-------|------|-------------|------|
| **HAガード** | LB, DNS, フェイルオーバー対象 | 2 | アクティブ-スタンバイ構成の維持 |
| **クォーラムガード** | Cache（Redis等）, Queue（Kafka等） | 3 | クォーラム合意（過半数）の維持 |

### 使い方

```bash
# 年15%成長、SLO 99.9%でキャパシティ計画
faultray capacity infra.yaml --growth 0.15 --slo 99.9

# 月次成長率での予測
faultray capacity infra.yaml --growth 0.02 --monthly --slo 99.95
```

### 出力例

```
=== Capacity Planning Report ===

Growth Rate: 15% annual | SLO Target: 99.9%

Component       | Current | 6mo  | 12mo | Exhaustion   | Action
----------------+---------+------+------+--------------+-------
api (app)       | 65% CPU | 75%  | 86%  | 14 months    | Scale at 80%
postgres (db)   | 72% disk| 83%  | 95%  | 8 months     | URGENT: expand storage
redis (cache)   | 35% mem | 40%  | 46%  | >24 months   | OK
nginx (lb)      | 25% CPU | 29%  | 33%  | >24 months   | OK

Right-sizing Recommendations:
  api:      3 -> 4 replicas (growth headroom)
  postgres: 100GB -> 250GB disk (exhaustion in 8mo)
  redis:    3 replicas (quorum guard: minimum 3)  [no reduction]
  nginx:    2 replicas (HA guard: minimum 2)       [no reduction]

SLO Compliance at 12 months: 99.87%  WARNING (below 99.9% target)
  Action: Scale api to 5 replicas before month 10
```

### ユースケース

- **予算計画**: 来年度のインフラコストを根拠をもって見積もる
- **SLA保証**: 成長しても契約SLAを維持できることを証明する
- **リソース最適化**: 過剰プロビジョニングを解消しつつ安全マージンを確保する
- **リスク予測**: いつどのコンポーネントがボトルネックになるかを事前に特定する

---

## エンジンの組み合わせ

### 推奨ワークフロー

```
1. Cascade     まずSPOFとカスケード障害を把握する
       |
2. Dynamic     トラフィックパターンを適用して動的耐性を検証する
       |
3. What-If     パラメータ調整で改善可能な領域を特定する
       |
4. Capacity    成長予測で将来のボトルネックを予測する
       |
5. Ops         長期運用でSLO準拠を確認する
```

### 統合実行例

```bash
# 全エンジンを順番に実行
faultray load infra.yaml
faultray simulate --html cascade-report.html
faultray dynamic infra.yaml --traffic diurnal --duration 24h
faultray whatif infra.yaml --defaults
faultray capacity infra.yaml --growth 0.15 --slo 99.9
faultray ops-sim infra.yaml --days 7
```

## 次のステップ

- [クイックスタート](getting-started.md) -- インストールと最初のシミュレーション
- [コンプライアンス評価](compliance.md) -- 規制フレームワーク準拠チェック
- [API リファレンス](api.md) -- プログラマティックアクセス
- [業界別ユースケース](usecases.md) -- 具体的な活用事例
