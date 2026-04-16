# FaultRay 論文 弱点分析

**対象**: `faultray-paper.tex` (v12 draft, 1504行)
**分析日**: 2026-04-16
**目的**: 査読者視点での弱点洗い出し。v12 rewrite / patent strategy の判断材料

---

## A. 致命的弱点（査読で即リジェクトレベル）

### A1. 評価が循環論法

- F1=1.000 は「インシデント報告からトポロジーを構築した」ため構造的にトートロジー。論文自身が「trivially achievable by construction」と認めている (L878-879)
- **Binary F1 は naive reverse-BFS と全36トポロジーで同一結果** (L1071-1072)。LTS形式化の付加価値がゼロであることを論文自身が証明している
- perturbation analysis は non-degeneracy しか示さない。「壊したら壊れる」は当たり前

**査読者の問い**: 「BFS で同じ結果が出るなら、LTS 形式化の意味は?」

### A2. Prospective validation 完全欠如

- Krasnovsky (ICSE-NIER 2026) は DeathStarBench で MAE≤0.0004 の定量結果を持つ。FaultRay は**定量比較ゼロ**
- 論文が明示的に「no quantitative comparison to any baseline exists in this paper」(L1066-1067) と書いている
- 未知トポロジーでの予測能力が示されていない以上、実用的価値を主張できない

**査読者の問い**: 「prospective evaluation なしで何を conclude できるのか?」

### A3. 形式化が proof sketch 止まり

- 全 Theorem (1-7) が informal proof sketch。Coq/Isabelle/TLA+ 検証なし (L564-566)
- **Krasnovsky との差別化ポイントが「formal」なのに、その formal が sketch レベル**。差別化の根拠が崩壊する
- Theorem 1 (Termination) の証明で「each rule adds at least one component to V」と言いつつ、cyclic graph では D_max=20 の「additional guard」が必要と認めている (L580-584)。visited set だけでは termination が保証されない可能性がある

**査読者の問い**: 「proof sketch を formal guarantee と呼んでよいのか?」

---

## B. 重大な技術的弱点

### B1. LTS ≡ BFS 問題

- 論文が自認: cascade engine の binary 予測は naive reverse-BFS と全く同じ (L1071)
- 「severity differentiation が added value」と主張するが、severity accuracy は 0.819 で mediocre、かつこのメトリクスの詳細評価がない
- 査読者は「BFS の上に形式化を被せて何を得たのか?」に答えられないと判断する

**深刻度**: Contribution の根幹を揺るがす

### B2. min-composition の正当化が弱い

- 論文自身が「modeling choice, not a theorem」(L1208)
- min と product の差が平均 0.02 pp (L1088)。**差が微小すぎて contribution として弱い**
- 「which operator better matches operational experience」は empirical question だが、**その実験をしていない**

**深刻度**: N-layer contribution の practical significance がない

### B3. L3 の公式が L2 に依存 → min 構造が崩壊

- `A_L3 = A_L2 · (1 - p_loss) · (1 - f_gc)` (L825)
- 数学的に L3 ≤ L2 が**常に成立**するため、`min(L2, L3) = L3` が常に真
- L2 が min-composition に寄与しない構造になっている。5層と言いつつ**実質4層以下**

**深刻度**: N-layer モデルの整合性に疑問

### B4. Rule 4 と Rule 5 が完全に同一

- optional と async の transition rule が式レベルで全く同じ (L504-524)
- 同一ルールに2つの名前を付けて dependency type の分類を主張しているが、意味論的に区別がない

**査読者の問い**: 「optional と async を区別する意味論的根拠は?」

### B5. Circuit breaker モデルが単純すぎる

- Rule 6 は latency 超過のみでトリップ (L529-537)
- 実際の circuit breaker (Hystrix/Resilience4j) は failure rate、half-open state、configurable threshold を持つ
- 「formal model」を名乗るなら、実務と乖離した単純化を正当化すべき

**深刻度**: 実用性への信頼を損なう

### B6. Monotonicity proof (Theorem 3) の Rule 2 記述が不正確

- Proof sketch 内で Rule 2 を「sets H(c') ← max(H(c), H(c')) or Down」と書いている (L609)
- しかし実際の Rule 2 の式 (L482-488) は無条件に `H[c' ↦ Down]` であり、max は使っていない
- proof sketch と rule definition の間に不一致がある

**深刻度**: 形式的正確性を主張する論文で致命的

---

## C. 構造的弱点

### C1. テストトポロジーが小さすぎる

- 36トポロジー、各3-7コンポーネント (L1275-1276)
- 実運用は数百〜数千コンポーネント。スケーラビリティの実証がない
- 論文の Threats to validity で自認しているが、解決策を示していない

### C2. ハードコード・未検証パラメータの山

| パラメータ | 値 | 根拠 |
|---|---|---|
| α(optional) | ≤ 0.5 | engineering judgment |
| α(async) | ≤ 0.3 | engineering judgment |
| D_max | 20 | 最大観測深度×3 (arbitrary) |
| default MTBF/MTTR | app:2160h/5min, db:4320h/30min | engineering estimates |
| p_human, p_drift | 不明 | 記載なし |
| severity thresholds | critical≥7.0, major≥4.0, minor≥1.0 | 不明 |

- α のsensitivity analysis が欠如
- D_max は言及あるが定量評価なし
- severity threshold の根拠が明示されていない

### C3. 静的トポロジー仮定

- auto-scaling、container rescheduling、DNS failover、service mesh の動的変化を一切モデル化しない
- cloud-native 環境では topology 自体が秒単位で変わる
- 「in-memory simulation」の価値が最も発揮される場面（デプロイ前の予測）で、静的仮定が最も壊れやすい

### C4. 4段階 health model が粗すぎる

- Degraded at 2x latency と 10x latency が同じ扱い (L1195-1199)
- Overloaded at 71% CPU と 99% CPU が同じ扱い
- 論文自身が認めているが、連続値への拡張は「future work」で片付けている

### C5. Gray failure のモデル化欠如

- 実システムで最も危険な障害パターンは gray failure（部分的・間欠的な劣化）
- Healthy/Degraded/Overloaded/Down の離散モデルでは intermittent failure を表現できない
- 参考: Huang et al. "Gray Failure: The Achilles' Heel of Cloud-Scale Systems" (HotOS 2017)

---

## D. 信頼性・採択の弱点

### D1. 単著・独立研究者・外部検証ゼロ

- 共著者なし、所属機関なし（Independent Researcher, Chigasaki, Japan）
- GitHub star 13 / fork 0 / 外部contributor 0
- PyPI 1,231 DL/月 (bot比率不明)
- 実際に使ったユーザーからのフィードバックなし

### D2. Contribution の新規性が thin

- 論文自身: 「novelty is not in the LTS formalism itself」(L238)
- 「specific combination」novelty は査読で最も弱い novelty 類型
- min vs product の差が 0.02pp では combination の付加価値を実証できない

### D3. コードベース品質

- 512ファイル中65%が孤島コード（243ファイル中158ファイルが外部参照ゼロ）
- 「30,000+ test functions」と書いているが、core は 12 files / 2,000 LOC (L1013-1016)
- 大量の dead code を含むコードベースは信頼性を損なう

### D4. AI drafting acknowledgment

- Claude (Anthropic) による drafting 支援を acknowledgments に記載 (L1341)
- Solo author + AI drafting の組み合わせは査読者に追加の検証負荷を生じさせる
- 技術的内容の正確性は著者責任と明記しているが、B6 のような不一致があると信頼性が低下する

---

## E. 弱点の深刻度ランキング

| Rank | ID | 弱点 | 影響 | 対処可能性 |
|---|---|---|---|---|
| 1 | A2+B1 | Prospective validation ゼロ + BFS等価 | 全体の contribution が「形式化した BFS」に帰着する | DeathStarBench 実験が必要（工数大） |
| 2 | A3+B6 | Proof sketch 止まり + 不一致 | Krasnovsky との唯一の差別化根拠が不十分 | TLA+ / Coq で検証（工数大） |
| 3 | B2+B3 | min-composition の実用的差 0.02pp + L3⊂L2 | N-layer contribution の practical significance がない | L3公式修正 + 実データ比較（工数中） |
| 4 | C1 | テスト規模 3-7 components | 実用性の証拠なし | 大規模トポロジー生成（工数中） |
| 5 | C3+C4+C5 | 静的トポロジー + 粗い health + gray failure 欠如 | cloud-native 環境への適用可能性に疑問 | モデル拡張（工数大） |
| 6 | B4 | Rule 4 ≡ Rule 5 | 形式化の設計に疑問 | async に遅延伝播の意味論を追加（工数小） |
| 7 | D1+D2 | 単著 + thin novelty | 採択ハードルが高い | 共著者獲得 or positioning 変更（工数中） |

---

## F. v12 rewrite への示唆

### patent enablement + arXiv preprint としての評価

現在の honest framing 戦略（overclaim 排除、limitation 明示）は **patent enablement の目的に対しては十分**。USPTO は peer review ではなく enablement (当業者が再現可能か) を見るため、上記弱点の多くは patent には影響しない。

### 対処推奨（v12 scope 内、工数小〜中）

1. **B3 修正**: L3 公式から L2 への依存を除去し、各層を独立に定義する
2. **B4 修正**: async に遅延伝播 (delayed propagation) の意味論を追加し、optional との差別化を明確にする
3. **B6 修正**: Theorem 3 の proof sketch を Rule 2 の実際の定義と整合させる
4. **C2 部分対処**: α パラメータの sensitivity analysis を 1 段落追加する

### 対処非推奨（v12 scope 外、I' 戦略と矛盾）

- Prospective validation 実験 (DeathStarBench)
- TLA+/Coq による mechanized proof
- 大規模トポロジー実験
- Gray failure / dynamic topology モデル拡張

これらは「研究としての完成」に必要だが、I' Gate 型 Real Option 戦略（Month 6 Gate 2026-10-08 で Go/No-Go）と矛盾するため、inbound signal がない限り投資しない。

---

## G. venue 別の採択可能性

| Venue | 種別 | 採択可能性 | 主要障壁 |
|---|---|---|---|
| ICSE/FSE/SOSP | Top-tier | 極低 (< 5%) | A1+A2+A3 全てが致命的 |
| ISSRE Fast Abstract | Workshop | 中 (30-50%) | 2ページなので limitation を深く問われない |
| ICSE-NIER 2027 | New Ideas | 低〜中 (15-30%) | Krasnovsky 2026 が同 venue で採択済み、差別化が弱い |
| arXiv preprint | 非査読 | 確実 (endorsement 次第) | 技術的弱点は問われない |
| Zenodo | 非査読 | 確実 | 既に DOI 取得済み |

---

## H. 追加弱点（2026-04-16 追加調査分）

### H1. 著者の複数原稿間でインシデント数が不整合

| 原稿 | incident 数 |
|---|---|
| Main paper (arXiv v12 draft) | 36 |
| ICSE 2027 NIER (`icse2027-nier.tex`) | 54 |
| ISSRE 2026 Fast Abstract (`issre2026-fast-abstract.tex`) | 54 |

- 同一著者・同一ツールの同時期原稿で数字が揃っていない
- 査読者が cross-reference した場合（特に ICSE NIER は double-blind だが、FaultRay で検索すれば main paper に到達する）、**データの信頼性に red flag**
- 36→54 に増やしたのか、54→36 に絞ったのか、理由の説明がどちらの原稿にもない

**対処**: 全原稿でインシデント数を統一するか、差分の理由を明示する。ICSE NIER が 54 なら main paper も 54 に更新すべき（18件のトポロジーYAMLを追加、またはなぜ除外したか記載）

**深刻度**: 査読で integrity 疑義になりうる

### H2. Patent + Apache 2.0 の IP テンション

- Apache 2.0 §3 に express patent grant が含まれる（OSS ユーザーは特許の実施許諾を自動取得）
- 一方で論文は「the provisional filing preserves rights for uses outside the scope of the Apache license (e.g., independent reimplementation)」(L1250-1253) と記載
- この記述は OSS コミュニティに**混乱と不信を与える**
  - 「Apache 2.0 だから自由に使える」と思ったユーザーが、independent reimplementation には特許が及ぶと知った場合の反発
  - CNCF / OSS コミュニティでの adoption barrier になりうる
- 査読者視点: 論文の学術的貢献と商業的 IP 保護の動機が混在しており、読者にとって uncomfortable

**対処**: patent status の記載は必要だが、「independent reimplementation への権利保持」の文言はトーンダウンするか、FAQ 的に補足する

**深刻度**: 採択には直接影響しないが、community reception を損なう

### H3. ユーザースタディ / 実務者フィードバック完全欠如

- ツール論文（tool paper）としての側面を持つにもかかわらず、**実務者がFaultRayを使って価値を感じたかのエビデンスがゼロ**
- GitHub star 13 / fork 0 / external contributor 0 / paying user 0 (D1 で触れているが、ユーザースタディの欠如として明示的に指摘)
- ICSE tool track や ISSTA tool demo では usability evaluation が事実上必須
- 「useful operating point」(L1288) と主張するが、useful だと感じた人間が著者以外にいない

**対処**: v12 scope 外（I' 戦略下で追求しない）。arXiv preprint には不要

### H4. 手構築トポロジーの再現性問題

- 36件のインシデントトポロジーは著者が post-mortem レポートを読んで手作業で構築
- 同じ post-mortem を別の研究者が読んだ場合、**異なるトポロジーを構築する可能性が高い**
  - コンポーネントの粒度（load balancer を1ノードにするか、L4/L7 で分けるか）
  - 依存関係の種別判断（requires vs optional の境界）
  - 暗黙の依存関係（DNS、shared storage など）の含否
- 論文は reproducibility を主張（fixed seed 42, pinned deps, YAML files in repo）しているが、**トポロジー構築プロセス自体の再現性は担保されていない**
- inter-rater reliability の測定なし（単著なので不可能だが、それ自体が弱点）

**対処**: topology construction guidelines を1段落追加し、各トポロジーの構築判断を incident YAML のコメントに記録する（工数小）

**深刻度**: construct validity への脅威。Threats to validity に追記すべき

### H5. L5 (External SLA) で product を使っている矛盾

- cross-layer composition は min を使う（correlated failure を理由に）
- しかし L5 内部: `A_L5 = Π(a_i)` (L849-851) で **series-product を使用**
- L2 内部: `A_L2 = Π A'_tier(c)` (L816-818) でも series-product
- 層内は independence 仮定で product、層間は correlated で min、という使い分けの正当化が**L749-752の1段落だけ**
- 査読者の問い: 「external SLA 同士も correlated ではないのか?（同一 cloud provider の複数サービスを使っている場合）」

**対処**: L5 内部でも correlated SLA のケース（同一 provider の複数サービス）への言及を追加（工数小）

### H6. Perturbation analysis の設計が弱い

- Edge deletion: 「ランダムに1本削除」→ which edge を削除するかで結果が大きく変わるはずだが、分散・標準偏差の報告なし
- Edge addition: 「new component を追加」→ 論文自身が「somewhat artificial」(L976) と認めている。既存ノード間の spurious edge が現実的
- Dependency type swap: 1本のみ → 複数本の同時 swap や、requires→async（最大の attenuation 変化）の効果が不明
- **統計的検定なし**: p-value / confidence interval / effect size のいずれも報告していない
- サンプルサイズ 36 で averaged delta F1 を報告しているが、36 topologies の variance が不明

**対処**: 各 perturbation の variance / CI を追加し、random seed を変えた複数試行の結果を報告（工数中）

### H7. Theorem 3 (Monotonicity) — Rule 1 の case analysis が不完全

> B6 は Rule 2 の proof sketch 不整合を指摘。これは **Rule 1** に関する別の不備。

- Proof sketch (L607): 「Rule 1 (Injection): sets H(c₀) ← **Down**, which is ≥ any prior health」
- 実際の Rule 1 定義 (L468-476): `h = effect(f.type)` で、`effect(latency_spike) = Degraded`
- **Rule 1 は常に Down にセットしない**。Degraded injection もありうる
- proof sketch は Down のケースのみで monotonicity を検証しており、**Degraded injection のケースを未検証**
- Degraded → Degraded は trivially monotone だが、proof が全ケースをカバーしていない事実が問題

**深刻度**: B6 と合わせて Theorem 3 に **2箇所の不正確さ**。formal を差別化ポイントにしている論文で、中心定理の証明に2つの穴は致命的

### H8. Theorem 6 (Attenuation) — Degraded がさらに伝播するケースを無視

- L649: 「Degraded does not trigger further required-dependency cascade propagation」→ **Rule 2 については正しい**（H(c)=Down を要求）
- しかし **Rule 4 (L504-511) と Rule 5 (L518-524) は H(c) ≥ Degraded で発火**
- optional/async エッジ経由で Degraded になったコンポーネントは、**さらに別の optional/async エッジを通じて他コンポーネントに伝播する**
- チェーン: Degraded →(optional)→ Degraded →(optional)→ Degraded ... が visited set で止まるまで続く
- Theorem 6 の「blast radius is limited」は **required-dependency に限定した主張**であるべきだが、論文はそう限定していない
- 最悪ケース: 全コンポーネントが optional/async エッジで接続 → 全コンポーネントが Degraded（blast radius = |C|）

**査読者の問い**: 「optional chain で全ノードが Degraded になる場合、blast radius のバウンドは何か?」

**対処**: Theorem 6 の statement を「required-dependency cascade に限定」と修正し、optional/async chain の伝播範囲を別途議論（工数小）

### H9. Layer 4 公式の値域エラー — A_L4 < 0 が起こりうる

- L839: `A_L4 = 1 - (n_inc · t_resp) / (8760 · p_cov)`
- 数値例: n_inc=500（年間500件）, t_resp=20h, p_cov=0.33（平日のみ）
  - A_L4 = 1 - (500 × 20) / (8760 × 0.33) = 1 - 10000/2890.8 = 1 - 3.46 = **-2.46**
- 可用性は [0, 1] の範囲であるべきだが、公式に `max(0, ...)` クランプがない
- 他の Layer (L1, L2, L3, L5) も同様に負値を取りうるが、L4 が最も現実的なパラメータ範囲で発生する
- 実装がクランプしていたとしても、**論文の数式レベルで値域制約を明記すべき**

**対処**: 全 Layer の公式に `A_Lk = max(0, min(1, ...))` を追加（工数極小）

### H10. 7件の不完全インシデント — 原因分析が一切ない

- 29/36 が F1=1.000（by construction で当然）、**7件が imperfect**
- L985-993: over-propagation 6件、under-propagation 1件と記載
- **個別の原因分析がゼロ**:
  - どのインシデントが imperfect か不明（名前なし）
  - over-propagation: どの Rule が誤伝播を起こしたか?
  - under-propagation: 何が欠けていたか? 依存関係の欠落? 新しい Rule が必要?
- これは論文中で**最も有益なデータ**。モデルの限界と改善方向を直接示す
- 例: 「Incident X では optional dependency の attenuation が不十分で、実際は完全に分離されていたサービスに Degraded が伝播した」→ Rule 4 改善の根拠
- **不作為の工数は小さい**（7件のYAMLを読んで1-2段落書くだけ）のに、やっていない

**査読者の問い**: 「7件の不完全ケースの breakdown を見せてほしい。モデルの限界を理解するのに不可欠」

**対処**: Table に 7件の incident 名 + failure mode (over/under) + 原因の1行サマリを追加（工数小）

### H11. min-composition が「楽観方向」にバイアス — レジリエンスツールとして逆効果

> B2 の補足。差が小さいだけでなく、**方向が問題**。

- L766-770: min は product より 0.01-0.10 pp **高い**（楽観的）
- FaultRay の目的は「インフラのレジリエンス弱点を発見する」
- 古典的手法（product）より**リスクを過小評価する方向にバイアス**がかかっている
- レジリエンス分析文脈では、false negative（見逃し）> false positive（過検出）のコストが高い
- 論文は min を「ceiling（超えられない上限）」と解釈 (L736-740) → ceiling が actual より高い場合、ceiling の意味がない
- product が pessimistic、min が optimistic なら、**conservative な tool は product を使うべき**

**査読者の問い**: 「レジリエンスツールが classical method より楽観的な結果を出す設計は正しいのか?」

**対処**: §5 sensitivity analysis に「楽観方向バイアスの意味と、どのケースで min が適切か」の1段落追加（工数小）

---

## I. 弱点の総数と分類サマリ（2026-04-16 更新）

| カテゴリ | 件数 | IDs |
|---|---|---|
| 致命的 (reject 直結) | 3 | A1, A2, A3 |
| 重大な技術的弱点 | 6 | B1-B6 |
| 構造的弱点 | 5 | C1-C5 |
| 信頼性・採択の弱点 | 4 | D1-D4 |
| 追加弱点 (Session 1) | 6 | H1-H6 |
| 追加弱点 (Session 2) | 5 | H7-H11 |
| **合計** | **29** | |

### 即時対処可能な修正（H7-H11 分）

| ID | 修正内容 | 工数 | LaTeX影響行数 |
|---|---|---|---|
| H9 | 全Layer公式に `max(0, min(1, ...))` 追加 | 極小 | ~5行 |
| H7 | Theorem 3 proof: Rule 1 に Degraded ケース追記 | 極小 | ~3行 |
| H8 | Theorem 6 statement を required-dep に限定 | 小 | ~5行 |
| H10 | 7件不完全インシデントの表を追加 | 小 | ~15行 |
| H11 | §5 に楽観バイアスの議論1段落追加 | 小 | ~10行 |
| **合計** | | | **~38行** |

---

## J. Genspark リサーチ追加知見 (2026-04-16 Session 3)

**ソース**: gsk search 6件 + gsk crawl 試行。詳細 → `/tmp/genspark-research-latest.md`

### J1. Krasnovsky が ICSE 2026 Distinguished Paper Award を受賞 [A2 深刻度↑↑]

- **確認元**: conf.researchr.org ICSE 2026 NIER track、DockerHub `akras/socialnet-resilience`、GitHub `a-a-k/socialnet-resilience`
- **事実**: Krasnovsky の "Model Discovery and Graph Simulation" は ICSE-NIER 2026 で **Distinguished Paper Award** を受賞
- **影響**: A2 の深刻度が決定的に悪化。FaultRay の「complementary」positioning は DPA 受賞論文に対して通用しない。DPA は「この手法が正しい方向」という学会のお墨付き
- ICSE-NIER 2027 に出す場合、**前年の同 track で DPA を取った手法との比較が確実**。prospective evaluation なしでは劣後が明白
- Krasnovsky の再現パッケージ: DeathStarBench + Jaeger traces + Docker Compose + 定量指標。FaultRay の手構築 YAML + post-hoc 再現とは**再現性の質が根本的に異なる** (H4 補強)

### J2. AWS 形式検証15年の実績 — CACM 2025 [A3 深刻度↑]

- **出典**: "Systems Correctness Practices at Amazon Web Services", Communications of the ACM, May 2025
- AWS は **2011年から** TLA+, Alloy, P言語で DynamoDB, S3, EBS, IAM 等を **機械的に検証**
- 2023 re:Invent で P Framework を紹介。業界は proof sketch → mechanized verification → runtime verification と進化中
- **影響**: FaultRay が「formal」をタイトルと abstract で主張しつつ proof sketch 止まりであることのギャップ拡大。AWS 出身の査読者なら「sketch ≠ formal」は即指摘

### J3. Nasar 2026: TLA+ によるインフラ信頼性の形式検証が同年出版済み [A3 深刻度↑]

- **出典**: M. Nasar, "Formal validation for microgrid reliability based on TLA+", Journal of Electrical Engineering, 2026 (doi:10.2478/jee-2026-0006)
- マイクログリッド（電力インフラ）の信頼性を TLA+ で形式検証。ドメインは異なるが「TLA+ でインフラ信頼性を形式検証する」方法論は直接先行
- **影響**: FaultRay が「TLA+ verification is future work」(L566, L1182) と書いている間に、他の研究者は同年に適用・出版済み。「future work」が **不作為** に見える
- Related Work §2.4 に引用すべき

### J4. 参考文献の29%が non-peer-reviewed [D 系補強]

24 references のうち7件 (29%) が peer-reviewed でない:

| bibkey | 種別 | 対処案 |
|---|---|---|
| gremlin2020 | 企業HP | chaos-mlr-2025 (TOSEM) に統合 |
| steadybit2023 | 企業HP | 同上 |
| aws-fis | 製品ページ | 同上 |
| litmuschaos | プロジェクトHP | CNCF reliability paper or survey |
| meta2021 | 企業ブログ | **正当** (incident primary source) |
| cloudflare2022 | 企業ブログ | **正当** (同上) |
| aws-s3-2017 | インシデント報告 | **正当** (同上) |

- incident reports 3件は primary source として正当
- tool 4件を chaos-mlr-2025 survey に統合すれば non-peer-reviewed 率 **29% → 12%** に改善可能
- **工数**: 小（引用の書き換えのみ）

### J5. "Towards a Science of AI Agent Reliability" (arXiv:2602.16666, Feb 2026)

- AI agent の信頼性を工学的フレームワークで扱う2026年の包括的サーベイ
- Discussion §9 の scope 削除理由 (L1218-1226) にこの論文を追加引用すると、AI agent 部分の削除判断の正当性がさらに強化される

---

## K. 弱点深刻度ランキング 最終改訂版 (J 節反映)

| Rank | ID | 弱点 | J節による変動 |
|---|---|---|---|
| 1 | A2+B1+**J1** | Prospective validation ゼロ + BFS等価 + **Krasnovsky DPA受賞** | **↑↑ 致命的悪化** |
| 2 | A3+B6+H7+**J2+J3** | Proof sketch + 不一致2箇所 + **AWS 15年実績 + Nasar 2026同年** | **↑ 悪化** |
| 3 | B2+B3+H5+H11 | min-composition 0.02pp + L3⊂L2 + L5内product矛盾 + 楽観バイアス | 変動なし |
| 4 | H1 | インシデント数不整合 (36 vs 54) | 変動なし |
| 5 | H8+H9+H10 | Theorem 6 不備 + L4値域エラー + 7件原因分析欠如 | 変動なし |
| 6 | C1+H4+**J1** | テスト規模 3-7 + トポロジー再現性 + **artifact格差** | **↑ 微悪化** |
| 7 | D1+D2+**J4** | 単著 + thin novelty + **参考文献29% non-peer-reviewed** | **↑ 微悪化** |

---

## L. v12 scope 内で対処可能な J 節項目

| 項目 | 対処 | 工数 | 効果 |
|---|---|---|---|
| J1 (Krasnovsky DPA) | Related Work §2.2 に DPA 受賞を明記 | 小 | 既知事実の不記載リスク排除 |
| J3 (Nasar 2026) | Related Work §2.4 に追加引用 | 小 | formal methods 網羅性向上 |
| J4 (参考文献品質) | tool 4件を survey 参照に統合 | 小 | non-peer-reviewed 29%→12% |
| J5 (AI reliability survey) | Discussion §9 に追加引用 | 小 | scope 削除判断の補強 |

### v12 scope 外（I' 戦略下で signal 待ち）

- J1 対抗: DeathStarBench prospective evaluation (工数大)
- J2/J3 対抗: TLA+ mechanized proof (工数大。Theorem 1 単体なら工数中)
- J1 対抗: Docker-based reproducibility package (工数中)

---

## N. 論文と実装コードの乖離（コード検証: 2026-04-16 Session 4）

> `cascade.py` および `availability_model.py` を Read/Grep で実際に検証した結果。
> A-L の「論文内の問題」とは別軸: **形式仕様どおりに実装されているか**。

### N1. Rule 3 (Required Dependency — Multiple Replicas) が未実装

- **論文の主張** (L491-499): `replicas(c) > 1` の場合、依存先は `Down` ではなく `Degraded` に遷移
- **実装の実態**: `cascade.py` `_calculate_cascade_effect()` (付近L796-903) に**レプリカ数チェックが存在しない**。`requires` 依存は常に一律 `Down` 遷移
- **影響**: 8 transition rules のうち 1 つが paper-only。backtest の F1 結果は Rule 3 なしで計算されている → F1 数値は 7/8 rules のエンジンで出た値
- **特許影響**: claim が「8 rules の LTS」を含む場合、Rule 3 の enablement 不足 (35 USC §112(a))

**深刻度**: 高。形式仕様と実装の不一致は、OSS 公開でコードを確認した査読者が即発見する

### N2. Attenuation factors α が実装に存在しない

- **論文の主張** (L857-866): `A_path(P) = ∏ α(dep(c_i, c_{i+1})) · A_system` で α(requires)=1.0, α(optional)≤0.5, α(async)≤0.3
- **実装の実態**: コードは health state 遷移の固定マッピング（optional/async → `DEGRADED`）。weight≤0.1 の threshold 判定はあるが**乗算的パス合成は非存在**
- **影響**: §5.7 Cascade Path Availability (L856-866) の公式全体が dead letter。evaluate にこの公式を使っていないなら論文整合性は保てるが、定義だけして使わない数式がある
- C2 の α sensitivity analysis 欠如とも連動

**深刻度**: 中。ただしこの数式を特許 claim に入れると enablement 問題

### N3. D_max=20 のハードコード

- **論文** (L669): 「configurable engineering parameter」
- **実装**: `cascade.py` L713 `if depth > 20: return` / L288 `MAX_LATENCY_DEPTH = 20` — リテラル値。設定ファイル/CLI arg/コンストラクタ引数による注入パスなし
- Corollary 1 (L662-667) は D_max 変更を前提とした記述。「For very large service meshes, a practitioner may increase D_max」(L676) は**コード直接編集が必要**

**深刻度**: 低〜中。「configurable」の定義次第だが、ツール論文で code edit required は通常 configurable とは呼ばない

---

## O. Rule 6 (Circuit Breaker Trip) の単調性違反可能性

> B6 は Rule 2 の proof sketch 不整合。H7 は Rule 1 の case 漏れ。本項は **Rule 6 自体**の意味論的問題で、B6・H7 とは独立。

### 問題の構造

- **Rule 6 の定義** (L529-537): CB trip 時に `H[c' ↦ DEGRADED]` を**無条件適用**
- **Theorem 3 (Monotonicity)** (L600-601): 「H'(c) ≥ H(c) for all c」
- **矛盾**: c' が既に `OVERLOADED` or `DOWN` の場合:
  - `H[c' ↦ DEGRADED]` → `DEGRADED < OVERLOADED < DOWN`
  - よって H'(c') < H(c') → **Theorem 3 に直接反する**

### Rule 4, 5 との対比

Rule 4 (L510): `H[c' ↦ max(DEGRADED, H(c'))]` — max 操作で既に悪い状態を保持。
Rule 6 にはこの `max` がない。**同じ著者が Rules 4-5 では max を使い Rule 6 で忘れた**パターン。

### 反例構成

```
Step 1: Component A →(requires)→ B →(optional)→ C
Step 2: Inject fault on A → B = DOWN (Rule 2)
Step 3: B DOWN → C = max(DEGRADED, HEALTHY) = DEGRADED (Rule 4) ✓
Step 4: 別経路で C が OVERLOADED に遷移（capacity超過 or 別fault）
Step 5: B の CB trip が C に発火 → C = DEGRADED (Rule 6) ← OVERLOADED→DEGRADED = 改善！
```

Step 4 が visited set で防がれるかは実装の BFS 探索順序に依存。

### Proof sketch の穴

Theorem 3 proof (L616-617):
> 「Rules 6-7: set H(c') ← DEGRADED or DOWN, both ≥ HEALTHY」

「≥ HEALTHY」は正しいが、Theorem 3 の条件は「≥ H(c')」。c' が OVERLOADED なら DEGRADED < OVERLOADED で**条件未証明**。

### Theorem 3 累積問題（B6 + H7 + O）

| 箇所 | 問題の種類 |
|---|---|
| B6: Rule 2 | proof sketch が rule definition と不一致 |
| H7: Rule 1 | Degraded injection ケースが未検証 |
| O: Rule 6 | max 欠如による実際の単調性違反可能性 |

Theorem 3 に **3箇所の問題**。formal を差別化軸にする論文で中心定理に 3 つの穴は壊滅的。

**深刻度**: 高。J2 (AWS の TLA+ 15年実績) と合わせると、「proof sketch ≠ formal」への批判が決定的

---

## P. arXiv v12 vs ICSE-NIER 2027 — 全メトリクス突合

> H1 は incident 数の不整合のみ指摘。本項は**全メトリクスの比較と帰結の分析**。

### 数値比較

| 指標 | arXiv v12 (L900-940) | ICSE-NIER (L46-51) | 差分 | 方向 |
|------|------|------|------|------|
| Incidents | 36 | 54 | +50% | 拡張 |
| Providers | 不記載 | 21 | — | — |
| Year range | 2017-2023 | 2017-2024 | +1y | CrowdStrike等 |
| **F1** | **0.971** | **0.87** | **-10.4%** | **劣化** |
| Precision | ≈1.000 | 1.00 | 一致 | — |
| **Recall** | **≈1.000** | **0.81** | **-19%** | **大幅劣化** |
| **Severity Acc.** | **0.819** | **0.58** | **-29.2%** | **壊滅** |

### 帰結

1. **汎化能力の低さ**: 18件追加で F1 が 10%下落。36件版は「うまくいくケースだけ」の cherry-picked subset という批判を招く
2. **Recall 0.81 の実務的意味**: cascade で影響を受ける 5 コンポーネントに 1 つを見逃す。resilience ツールとして「影響範囲を見逃す」は最も危険な failure mode
3. **Severity 0.58**: 4段階分類で chance 0.25 よりマシだが、「critical か minor か」を半分近く外す
4. **narrative の不整合**: arXiv v12 は「29/36 achieve F1=1.000」を前面に出す framing。ICSE 版 0.87 を知った査読者は arXiv 版を **misleading** と判断する可能性

### 対処選択肢

| 選択肢 | メリット | リスク |
|---|---|---|
| arXiv を 54件に統一 | 誠実、整合的 | F1=0.87 で narrative 書き直し必要 |
| ICSE を 36件に統一 | arXiv narrative 維持 | cherry-pick 批判 |
| 両方で差異を明示 + cross-reference | 最も誠実 | 「なぜ arXiv は subset？」の回答必要 |

**推奨**: 3番目（差異を明示）。arXiv に「A separate evaluation on a 54-incident superset (see [ICSE ref]) shows F1=0.87 and recall=0.81, consistent with the modeling limitations described in §9」を 1 文追加。工数極小。

---

## Q. 依存性モデリングの表現力不足

> C3 は「静的トポロジー」、B4 は「Rule 4≡5」、B5 は「CB 単純すぎ」。
> 本項は **3分類自体の表現力** と **グラフ走査の非決定性** を体系的に整理。

### Q1. requires/optional/async では現実のカップリングパターンの 80% をモデル化できない

| 現実のパターン | 表現可能か | 備考 |
|---|---|---|
| Circuit breaker half-open state | × | Rule 6 は open/closed のみ |
| Bulkhead isolation | × | resource 分離モデルなし |
| Retry w/ exponential backoff | △ | retry multiplier はあるが時間発展なし |
| Rate limiting | × | traffic 量ベースの動的制限なし |
| Graceful degradation (feature flag) | × | 部分機能低下モデルなし |
| Partial failure (shard 単位) | × | component は atomic、shard 障害不可 |
| Cascading timeout (retry storm) | △ | Rule 7 あるが connection pool 単純 |
| Back-pressure propagation | × | consumer→producer 方向の圧力伝播なし |
| Thundering herd | × | 復旧時の同時再接続負荷なし |
| Split-brain (network partition) | × | 部分ネットワーク分断なし |

10パターン中 ×8、△2。cloud-native 環境の主要障害パターンの**大半がモデル外**。
これは §9 Discussion の「modeling simplifications」(L1184-1191) で部分的に認めているが、上記の体系的リストは論文にない。

### Q2. 双方向依存とグラフ走査の非決定性

- 実システムでは**双方向依存**が頻繁（API gateway ↔ auth service のヘルスチェック相互参照、DB primary ↔ replica sync）
- Cycle は visited set + D_max で停止するが、**cycle 内のどのノードを先に visit するかで結果が変わる**
- 同一トポロジー・同一 fault injection でも、BFS queue の初期順序次第で affected set が異なりうる（**非決定性**）
- perturbation analysis の seed 42 は乱数制御であり、BFS queue の deterministic ordering を保証するかは別問題
- 論文はこの非決定性に**一切言及していない**
- Theorem 4 (Causality) は「少なくとも1つの依存先が先に遷移」を保証するが、**どの依存先が先に遷移するか**は保証しない

**深刻度**: 中。再現性の隠れたリスク。同じ入力で異なる結果が出る可能性は formal tool として最も避けるべき

---

## R. 特許 enablement への影響（N, O の帰結）

> USPTO enablement 要件 (35 USC §112(a)):「当業者 (PHOSITA) が過度な実験なく発明を再現できること」
> arXiv v12 が enablement evidence として patent attorney に参照される前提での分析。

### 論文-コード乖離が claim を弱めるシナリオ

| 乖離 | claim への影響 | リスクレベル |
|---|---|---|
| N1: Rule 3 未実装 | 「8 transition rules の LTS」claim → Rule 3 enablement 不足 | **高** |
| N2: α factor 未実装 | Cascade Path Availability を claim に含めると実装証拠なし | 中 |
| N3: D_max ハードコード | 「configurable depth limit」claim と実装矛盾 | 低 |
| O: Rule 6 単調性違反 | 「monotonicity guarantee」claim に反例構成リスク | **高** |

### 推奨アクション（本出願前・arXiv v12 upload 前）

| 優先度 | アクション | 工数 | 効果 |
|---|---|---|---|
| **P0** | O: Rule 6 に `max(DEGRADED, H(c'))` 追加 (論文+コード) | 数時間 | Theorem 3 の 3箇所問題の 1 つを解消 |
| **P0** | N1: Rule 3 実装 (replicas > 1 → DEGRADED 遷移) | 1日 | 8 rules claim の enablement 確保 |
| **P1** | N3: D_max を CLI arg / config 化 | 半日 | 「configurable」claim の正当化 |
| **P2** | N2: α factor は claims から除外、description のみ | 0 | リスク回避 |

### 特許 claims の安全な構成

```
Independent Claim 1 (Method):
  (a) receiving dependency graph G
  (b) executing LTS with 8 transition rules   ← N1修正後のみ
      [Rule 1-8 を列挙、Rule 6 は max 操作付き]  ← O修正後のみ
  (c) computing blast radius in O(|V|+|E|)
  (d) min-composition: A = min(A_L1..A_LN)
  (e) outputting availability ceiling

独立 claim から除外すべき:
  - α factor / Cascade Path Availability (N2: 未実装)
  - monotonicity (O 修正前)
  - configurable D_max (N3 修正前)
```

---

## S. 弱点の総数と分類サマリ（2026-04-16 全 Session 統合）

| カテゴリ | 件数 | IDs |
|---|---|---|
| 致命的 (reject 直結) | 3 | A1, A2, A3 |
| 重大な技術的弱点 | 6 | B1-B6 |
| 構造的弱点 | 5 | C1-C5 |
| 信頼性・採択の弱点 | 4 | D1-D4 |
| 追加弱点 (Session 1) | 6 | H1-H6 |
| 追加弱点 (Session 2) | 5 | H7-H11 |
| Genspark リサーチ追加 (Session 3) | 5 | J1-J5 |
| 実装乖離 (Session 4) | 3 | N1-N3 |
| 形式的欠陥 (Session 4) | 1 | O |
| 数値矛盾詳細 (Session 4) | 1 | P |
| モデリング不足 (Session 4) | 2 | Q1-Q2 |
| 特許リスク (Session 4) | 1 | R |
| **合計** | **42** | |

### 全 Session 統合: 即時対処推奨（v12 upload 前）

| ID | 修正内容 | 工数 | 対象 |
|---|---|---|---|
| O | Rule 6 に `max(DEGRADED, H(c'))` 追加 | 数時間 | LaTeX + cascade.py |
| N1 | Rule 3 実装 (replicas チェック) | 1日 | cascade.py + tests |
| N3 | D_max を CLI/config 化 | 半日 | cascade.py + CLI |
| H9 | 全Layer公式に `max(0, min(1, ...))` 追加 | 極小 | LaTeX ~5行 |
| H7 | Theorem 3 proof: Rule 1 に Degraded ケース追記 | 極小 | LaTeX ~3行 |
| H8 | Theorem 6 を required-dep に限定 | 小 | LaTeX ~5行 |
| H10 | 7件不完全インシデントの breakdown 表 | 小 | LaTeX ~15行 |
| H11 | §5 に楽観バイアスの議論 | 小 | LaTeX ~10行 |
| P | arXiv に 54件評価への cross-reference 1文追加 | 極小 | LaTeX ~3行 |
| J1 | Related Work に Krasnovsky DPA 受賞を明記 | 小 | LaTeX ~2行 |
| J3 | Related Work に Nasar 2026 追加引用 | 小 | LaTeX + bib |
| J4 | tool 4件を survey 引用に統合 | 小 | bib 書き換え |
| B6 | Theorem 3 proof: Rule 2 記述を式と整合 | 極小 | LaTeX ~2行 |
| **合計** | | **~3-5日** | |

---

## T. 統合優先順位マトリクス（全42件 → 4 Tier）

全セッション (A-R) の42件を **対処の緊急度 × 影響度** で4段階に整理。
v12 upload 前に P0/P1 を完了することを推奨。

### Tier 0: v12 upload をブロック（修正しないと出せない）

修正しなければ arXiv に出した瞬間にコード検証した読者が発見し、信頼性が崩壊する。

| # | ID | 弱点 | 修正内容 | 工数 | 対象 |
|---|---|---|---|---|---|
| 1 | **O** | Rule 6 の max 欠如 → Theorem 3 単調性違反 | Rule 6 に `max(DEGRADED, H(c'))` 追加 | 数時間 | LaTeX + cascade.py |
| 2 | **N1** | Rule 3 (replicas>1) が未実装 | replicas チェック追加、requires で replicas>1 → DEGRADED | 1日 | cascade.py + tests |
| 3 | **B6** | Theorem 3 proof sketch: Rule 2 の記述が式と不一致 | proof 内を `Down`（Rule 2 の実定義）に修正 | 極小 | LaTeX ~2行 |
| 4 | **H7** | Theorem 3 proof sketch: Rule 1 の Degraded injection ケース未検証 | `effect(f.type)` の全ケースを case analysis に追加 | 極小 | LaTeX ~3行 |
| 5 | **H9** | Layer 4 公式で A_L4 < 0 が起こりうる | 全 Layer 公式に `max(0, min(1, ...))` クランプ追加 | 極小 | LaTeX ~5行 |
| 6 | **P** | arXiv(36件/F1=0.971) vs ICSE-NIER(54件/F1=0.87) の数値矛盾 | arXiv に 54件評価への cross-reference 1文追加 | 極小 | LaTeX ~3行 |

**Tier 0 合計工数: ~2日**

---

### Tier 1: v12 の品質を大きく上げる（upload 前に強く推奨）

出さなくても致命傷ではないが、修正すれば査読者/読者の信頼性が格段に上がる。

| # | ID | 弱点 | 修正内容 | 工数 | 対象 |
|---|---|---|---|---|---|
| 7 | **H8** | Theorem 6: optional/async chain で blast radius=\|C\| になりうる | statement を required-dep cascade に限定、optional chain は別途記述 | 小 | LaTeX ~5行 |
| 8 | **H10** | 7件の不完全インシデントの原因分析ゼロ | 7件の名前+failure mode+原因1行の表を追加 | 小 | LaTeX ~15行 |
| 9 | **B3** | L3 = L2 × ... で L3 ≤ L2 が常に成立 → 5層が実質4層 | L3 公式から L2 依存を除去、独立に定義 | 中 | LaTeX + availability_model.py |
| 10 | **B4** | Rule 4 ≡ Rule 5（optional と async が同一式） | async に delayed propagation 意味論を追加 | 小 | LaTeX ~10行 + cascade.py |
| 11 | **H11** | min-composition が楽観方向にバイアス | §5 に楽観バイアスの意味と適用条件を1段落追加 | 小 | LaTeX ~10行 |
| 12 | **H5** | L5 内部で product を使う矛盾（同一 provider SLA は correlated） | L5 に correlated SLA ケースの議論を追加 | 小 | LaTeX ~5行 |
| 13 | **N3** | D_max=20 がハードコード。「configurable」は嘘 | CLI arg / config 注入パスを実装 | 半日 | cascade.py + CLI |
| 14 | **J1** | Krasnovsky が ICSE 2026 DPA 受賞 → 未記載 | Related Work §2.2 に DPA 受賞を明記 | 小 | LaTeX ~2行 |
| 15 | **J3** | Nasar 2026 (TLA+ infra reliability) が同年出版済み → 未引用 | Related Work §2.4 に追加 | 小 | LaTeX + bib |
| 16 | **J4** | 参考文献の 29% が non-peer-reviewed | tool 4件を chaos-mlr-2025 survey に統合 | 小 | bib 書き換え |

**Tier 1 合計工数: ~3日**

---

### Tier 2: あれば better だが I' 戦略下では optional

arXiv preprint / patent enablement の目的には直接影響しない。
Month 6 Gate (2026-10-08) で Go 判断した場合のみ対処。

| # | ID | 弱点 | 修正概要 | 工数 |
|---|---|---|---|---|
| 17 | **C2** | ハードコードパラメータの sensitivity analysis 欠如 | α, D_max, severity threshold の sensitivity 実験 + 1-2段落 | 中 |
| 18 | **H4** | トポロジー構築プロセスの再現性問題 | construction guidelines 1段落 + YAML コメント | 小 |
| 19 | **H6** | Perturbation analysis の統計的設計が弱い | variance/CI 追加、seed 変更複数試行 | 中 |
| 20 | **Q2** | 双方向依存でのグラフ走査非決定性 | BFS ordering の deterministic 保証 + 論文記載 | 中 |
| 21 | **H1** | インシデント数不整合 (36 vs 54) | 全原稿統一 or 差分理由明示 | 中 |
| 22 | **B5** | Circuit breaker モデルが単純 | half-open state, failure rate threshold 追加 | 中〜大 |
| 23 | **H2** | Patent + Apache 2.0 の IP テンション | 「independent reimplementation」の文言トーンダウン | 小 |
| 24 | **J5** | AI reliability survey (arXiv:2602.16666) 未引用 | Discussion §9 に追加 | 小 |
| 25 | **C4** | 4段階 health model が粗すぎる | 連続 health model への拡張検討 | 大 |
| 26 | **N2** | α factor が未実装（論文定義だけ） | claims から除外するか、実装するか決定 | 中 |
| 27 | **Q1** | 依存性モデルの表現力不足（10パターン中8が×） | 主要パターン 2-3 個を追加実装 | 大 |

---

### Tier 3: 構造的限界（v12 では対処不可、研究の次ステップ）

対処するには新規実験・大規模実装が必要。I' 戦略下では追求しない。
将来 startup 再挑戦 or 学術復帰時の roadmap として記録。

| # | ID | 弱点 | 対処に必要なもの | 工数 |
|---|---|---|---|---|
| 28 | **A2+B1** | Prospective validation ゼロ + LTS≡BFS | DeathStarBench 実験 + baseline 比較 | 大 |
| 29 | **A3+J2** | Proof sketch 止まり + AWS TLA+ 15年実績 | TLA+ or Coq で Theorem 1-3 を機械検証 | 大 |
| 30 | **A1** | 評価が循環論法 | unseen topology での prospective F1 測定 | 大 |
| 31 | **C1** | テスト規模 3-7 components | 100+ component synthetic topology 生成 + 評価 | 中〜大 |
| 32 | **C3** | 静的トポロジー仮定 | dynamic topology update model 設計+実装 | 大 |
| 33 | **C5** | Gray failure モデル化欠如 | intermittent failure 状態追加 + transition rule 拡張 | 大 |
| 34 | **D1** | 単著・外部検証ゼロ | 共著者 or external user study | 大 |
| 35 | **D2** | Contribution novelty が thin | 新 contribution (prospective validation 結果等) | 大 |
| 36 | **B2** | min-composition の practical significance (0.02pp) | 実運用データでの min vs product 比較実験 | 中〜大 |
| 37 | **H3** | ユーザースタディ / 実務者フィードバック欠如 | 5-10名の SRE に trial 依頼 | 大 |
| 38 | **D3** | コードベース 65% 孤島 | orphan code の experimental/ 移動 or git rm | 中 |
| 39 | **D4** | AI drafting acknowledgment | 構造的に解決不可（事実なので） | — |
| 40 | **R** | 特許 enablement リスク (N1/O 修正前提) | Tier 0 修正 + patent attorney consultation | 中 |
| 41 | **J1対抗** | Krasnovsky DPA 受賞への差別化 | 独自の prospective benchmark 構築 | 大 |
| 42 | **J2/J3対抗** | TLA+ mechanized proof | Theorem 1 単体から段階的に | 中〜大 |

---

### 意思決定サマリ

```
v12 upload deadline: 2026-05-05

今日 ────────── Tier 0 (2日) ── Tier 1 (3日) ──── upload
2026-04-16       2026-04-18      2026-04-21       2026-05-05
                                                   (2週間バッファ)

Tier 0: 修正しないと出せない。6件。工数2日。
Tier 1: 品質向上。10件。工数3日。Tier 0 と合わせて5日で完了可能。
Tier 2: optional。Month 6 Gate 後に判断。
Tier 3: 研究の次ステップ。v12 scope 外。
```

**最小実行パス**: Tier 0 のみ (2日) → upload
**推奨実行パス**: Tier 0 + Tier 1 (5日) → upload (品質差が大きい)

---

*このファイルは FaultRay 論文の内部レビュー用。外部公開しない。*
