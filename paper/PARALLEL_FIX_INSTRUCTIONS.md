# FaultRay v12 並列修正指示書

**作成日**: 2026-04-16
**対象**: WEAKNESS_ANALYSIS.md の Tier 0 (6件) + Tier 1 (10件) = 16件
**方針**: 4ウィンドウで並列修正。ファイル/行範囲の衝突を完全排除。

---

## ファイル担当マップ（衝突防止）

| ファイル | Window 1 | Window 2 | Window 3 | Window 4 |
|---|---|---|---|---|
| `cascade.py` (903行) | **全域** | 読取のみ | — | — |
| `faultray-paper.tex` §4 (L429-679) | — | **専有** | — | — |
| `faultray-paper.tex` §5+§7 (L683-1098) | — | — | **専有** | — |
| `faultray-paper.tex` §2+bib (L159-350, L1343-1501) | — | — | — | **専有** |
| `availability_model.py` (490行) | — | — | **全域** | — |
| CLI (`cli/simulate.py`, `cli/main.py`) | **全域** | — | — | — |
| tests/ | **全域** | — | — | — |

**ルール**: 各ウィンドウは「専有」列のファイル/行範囲のみ編集する。他ウィンドウの担当ファイルは Read のみ許可。

---

## Window 1: Cascade Engine コード修正

### 担当ファイル
- `src/faultray/simulator/cascade.py` (全域)
- `src/faultray/cli/simulate.py` (D_max CLI化)
- `tests/` 配下のカスケード関連テスト

### 修正項目 (4件)

#### 1-1. [Tier 0] O: Rule 6 に max 追加 — 単調性違反の修正

**問題**: Rule 6 (Circuit Breaker Trip) が `DEGRADED` を無条件セットしている。コンポーネントが既に `OVERLOADED` or `DOWN` の場合、health が改善してしまい Theorem 3 (Monotonicity) に違反する。

**修正箇所**: `cascade.py` L314-332 付近の circuit breaker 処理

**修正内容**:
```python
# Before (current):
# CB trip → sets component to DEGRADED unconditionally

# After (fix):
# CB trip → sets component to max(DEGRADED, current_health)
# This preserves monotonicity: health can only worsen or stay the same
```

具体的には、CB trip で DEGRADED を設定する箇所で、現在の health status と比較して悪い方を採用する。`_HEALTH_RANK` (L677-681) を使って比較可能。

**検証**: 以下のテストケースを追加:
```
Component C が既に OVERLOADED → CB trip → C は OVERLOADED のまま (DEGRADED にならない)
Component C が既に DOWN → CB trip → C は DOWN のまま
Component C が HEALTHY → CB trip → C は DEGRADED (従来動作を維持)
```

#### 1-2. [Tier 0] N1: Rule 3 (replicas > 1) の実装

**問題**: 論文 (L491-499) では `replicas(c) > 1` の場合に依存先を `DOWN` ではなく `DEGRADED` にする Rule 3 を定義しているが、`cascade.py` の `_calculate_cascade_effect()` (L796-903) にレプリカ数チェックが存在しない。`requires` 依存は常に一律 `DOWN`。

**修正箇所**: `_calculate_cascade_effect()` (L796-903) と `_propagate()` (L684-783)

**修正内容**:
```python
# requires 依存で upstream が DOWN の場合:
# if upstream.replicas > 1:
#     dependent → DEGRADED (Rule 3: capacity reduced but not failed)
# else:
#     dependent → DOWN (Rule 2: single point of failure)
```

- コンポーネントの `replicas` 属性を参照する。Infrastructure Graph model でどう保持されているか確認すること（`ComponentConfig` or 類似のデータクラス）
- 既存の soft-weight (weight ≤ 0.1) ロジックとの相互作用に注意

**検証**: 以下のテストケースを追加:
```
DB (replicas=3) が DOWN → 依存する app_server は DEGRADED (not DOWN)
DB (replicas=1) が DOWN → 依存する app_server は DOWN (従来動作)
```

#### 1-3. [Tier 1] N3: D_max を configurable 化

**問題**: D_max=20 が cascade.py の L713 と L288 にリテラルでハードコードされている。論文は「configurable engineering parameter」(L669) と記載。

**修正箇所**:
- `cascade.py`: `CascadeEngine.__init__()` に `max_depth: int = 20` パラメータ追加
- `cascade.py` L713: `if depth > 20` → `if depth > self.max_depth`
- `cascade.py` L288: `MAX_LATENCY_DEPTH = 20` → `self.max_depth` 参照
- `cli/simulate.py`: `--max-depth` オプション追加

**検証**: `--max-depth 5` で実行し、depth 6 以上で停止することを確認

#### 1-4. [Tier 1] B4 (コード部分): async に delayed propagation 追加

**問題**: Rule 4 (optional) と Rule 5 (async) が同一の処理。async に遅延伝播の意味論を追加して差別化する。

**修正箇所**: `_propagate()` と `_calculate_cascade_effect()` の dependency type 判定部分

**修正内容**:
```python
# async dependency の場合:
# 1. 伝播自体は optional と同じく DEGRADED に attenuation
# 2. ただし simulation time T を edge latency τ 分だけ進める
#    （optional は即時伝播、async は遅延伝播）
# これにより cascade_chain のタイムスタンプが異なり、
# severity scoring で差が出る
```

- `CascadeChain` の `timestamp` フィールドを活用
- 既存テストが壊れないことを確認

### 注意事項
- `faultray-paper.tex` は編集しない（Window 2 が担当）
- `availability_model.py` は編集しない（Window 3 が担当）
- 修正後は `pytest tests/test_cascade*.py -x` で既存テストが通ることを確認

---

## Window 2: LaTeX §4 Cascade Engine 形式仕様修正

### 担当ファイル
- `paper/faultray-paper.tex` の **L429-679 のみ**（§4 Cascade Engine 全体）

### 修正項目 (5件)

#### 2-1. [Tier 0] B6: Theorem 3 proof sketch — Rule 2 の記述修正

**問題**: Proof sketch (L609) で Rule 2 を「sets H(c') ← max(H(c), H(c')) or Down」と書いているが、実際の Rule 2 の式 (L482-488) は無条件に `H[c' ↦ Down]`。

**修正箇所**: L607-610

**修正内容**:
```latex
% Before:
Rule~2 (Required): sets $H(c') \leftarrow \max(H(c), H(c'))$ or
\textsc{Down}, both $\ge H(c')$.

% After:
Rule~2 (Required, single replica): sets $H(c') \leftarrow \textsc{Down}$,
which is the maximum health status and therefore $\ge H(c')$ for any
prior health.
Rule~3 (Required, multiple replicas): sets
$H(c') \leftarrow \max(\textsc{Degraded}, H(c'))$, preserving
monotonicity by the $\max$ operator.
```

#### 2-2. [Tier 0] H7: Theorem 3 proof sketch — Rule 1 の Degraded ケース追加

**問題**: Proof sketch (L607) で Rule 1 を「sets H(c₀) ← Down」と書いているが、実際の Rule 1 では `effect(latency_spike) = Degraded` もありうる。

**修正箇所**: L607-608

**修正内容**:
```latex
% Before:
Rule~1 (Injection): sets $H(c_0) \leftarrow \textsc{Down}$, which is
$\ge$ any prior health.

% After:
Rule~1 (Injection): sets $H(c_0) \leftarrow \mathit{effect}(f.\mathit{type})$.
Since $\mathit{effect}$ returns a health status $\ge \textsc{Degraded}$
and the target is initially \textsc{Healthy}, the result is $\ge H(c_0)$.
For re-injection on an already-degraded component, $\max$ semantics
should be applied; we note this as a modeling constraint.
```

#### 2-3. [Tier 0] O (LaTeX部分): Rule 6 の式に max 追加

**問題**: Rule 6 (L529-537) が `H[c' ↦ DEGRADED]` を無条件適用しており、Theorem 3 に違反する。

**修正箇所**: L533-534 の Rule 6 の式

**修正内容**:
```latex
% Before:
(H[c' \mapsto \textsc{Degraded}], L, T, V \cup \{c'\})

% After:
(H[c' \mapsto \max(\textsc{Degraded}, H(c'))], L, T, V \cup \{c'\})
```

同時に Theorem 3 proof sketch の Rules 6-7 部分 (L616-617) も更新:
```latex
% Before:
Rules~6--7 (CB Trip, Timeout): set $H(c') \leftarrow \textsc{Degraded}$
or \textsc{Down}, both $\ge \textsc{Healthy}$.

% After:
Rule~6 (CB Trip): sets $H(c') \leftarrow \max(\textsc{Degraded}, H(c'))$,
which preserves monotonicity by the $\max$ operator.
Rule~7 (Timeout): sets $H(c') \leftarrow \textsc{Down}$, which is
$\ge H(c')$ for any prior health.
```

#### 2-4. [Tier 1] B4 (LaTeX部分): Rule 5 に delayed propagation 意味論追加

**問題**: Rule 4 (L504-511) と Rule 5 (L518-524) が同一の式。

**修正箇所**: L518-524 の Rule 5

**修正内容**:
```latex
% Rule 5 (Async Dependency) を以下に変更:
% health 遷移は optional と同じだが、simulation time が edge latency 分進む

\textbf{Rule 5 (Async Dependency).}
If $c'$ has an \texttt{async} dependency on~$c$, the cascade is
attenuated (as with optional) but propagation is \emph{delayed}
by the edge latency $\tau(c', c)$:
\begin{equation}
  \frac{\mathit{dep}(c', c) = \texttt{async} \quad
        H(c) \ge \textsc{Degraded}}
  {(H, L, T, V) \xrightarrow{\textit{prop}(c, c')}
   (H[c' \mapsto \max(\textsc{Degraded}, H(c'))], L,
    T + \tau(c', c), V \cup \{c'\})}
\end{equation}
The delay models the asynchronous nature of the dependency:
message queues, event buses, and batch pipelines propagate
failures with latency rather than immediately.
```

#### 2-5. [Tier 1] H8: Theorem 6 の statement を required-dep に限定

**問題**: Theorem 6 (L639-650) が「blast radius is limited」と主張するが、optional/async chain で全ノードが DEGRADED になりうる。

**修正箇所**: L649-650

**修正内容**:
```latex
% Before:
... and since \textsc{Degraded} does not trigger further
required-dependency cascade propagation, the blast radius is limited.

% After:
... and since \textsc{Degraded} does not trigger further
\texttt{requires}-dependency cascade to \textsc{Down}
(Rule~2 requires $H(c) = \textsc{Down}$), the
\emph{severity} of cascade through optional/async paths is bounded
at \textsc{Degraded}. However, the \emph{extent} (number of affected
components) is bounded only by the reverse-reachable set
(Theorem~\ref{thm:blast}), as \textsc{Degraded} propagation through
chains of optional/async edges can reach all transitively connected
components.
```

### 注意事項
- `cascade.py` は編集しない（Window 1 が担当）
- L680 以降は編集しない（Window 3 が担当）
- L350 以前は編集しない（Window 4 が担当）
- 修正後は `pdflatex faultray-paper.tex` でコンパイルエラーがないことを確認

---

## Window 3: LaTeX §5 Availability + §7 Evaluation 修正

### 担当ファイル
- `paper/faultray-paper.tex` の **L683-1098 のみ**（§5 + §7）
- `src/faultray/simulator/availability_model.py` (全域)

### 修正項目 (6件)

#### 3-1. [Tier 0] H9: 全 Layer 公式に値域クランプ追加

**問題**: L4 公式 `A_L4 = 1 - (n_inc · t_resp) / (8760 · p_cov)` で A_L4 < 0 が起こりうる。

**修正箇所**: §5 の各 Layer 定義 (L782, L803, L824, L838, L849)

**修正内容**: 各 Layer の Definition/式の直後に以下を追加:
```latex
All layer availabilities are clamped to $[0, 1]$:
$A_{\text{Lk}} = \max(0, \min(1, \ldots))$.
```

同時に `availability_model.py` でも `compute_five_layer_model()` 内の各 Layer 計算結果に `max(0.0, min(1.0, value))` を適用する。

#### 3-2. [Tier 1] B3: L3 公式から L2 依存を除去

**問題**: `A_L3 = A_L2 · (1 - p_loss) · (1 - f_gc)` (L825) で L3 ≤ L2 が常に成立。min(L2, L3) = L3 が常に真で L2 が実質無意味。

**修正箇所**: L824-833 の §5.3 Layer 3 定義

**修正内容**:
```latex
% Before:
A_{\text{L3}} = A_{\text{L2}} \cdot (1 - \bar{p}_{\text{loss}})
  \cdot (1 - \bar{f}_{\text{gc}})

% After:
A_{\text{L3}} = (1 - \bar{p}_{\text{loss}}) \cdot (1 - \bar{f}_{\text{gc}})
```

L2 への乗算を除去し、L3 を独立した runtime noise floor として定義する。
§5.3 の説明文も「L2 を基準として…」ではなく「runtime 環境固有の上限として…」に修正。

同時に `availability_model.py` の `compute_five_layer_model()` 内の L3 計算も同様に修正。

#### 3-3. [Tier 1] H11: 楽観バイアスの議論追加

**問題**: min-composition が product より 0.01-0.10 pp 高い（楽観的）。レジリエンスツールが classical method より楽観的な結果を出す設計は直感に反する。

**修正箇所**: L762-777 の sensitivity analysis 段落の末尾

**追加内容** (1段落、約10行):
```latex
\paragraph{Direction of the gap.}
The min-composition is more \emph{optimistic} (higher availability estimate)
than the series-product. For a resilience analysis tool, this direction
warrants caution: practitioners who rely on the ceiling estimate may
under-estimate risk relative to the classical approach. We recommend
that practitioners compute both operators on their topology and treat
the series-product as a pessimistic lower bound and the min-composition
as an optimistic upper bound. The gap between the two quantifies the
sensitivity to the independence assumption.
```

#### 3-4. [Tier 1] H5: L5 内部の correlated SLA 議論追加

**問題**: L5 = ∏ a_i で series-product を使っているが、同一 cloud provider の複数サービスは correlated。

**修正箇所**: L847-852 の §5.5 Layer 5 定義の末尾

**追加内容** (5行):
```latex
When multiple external services are hosted by the same cloud
provider, their SLAs are correlated (a provider-level outage
degrades all). In such cases, the series-product over-estimates
the compounding effect; practitioners should group co-located
services and apply $\min$ within each provider group.
```

#### 3-5. [Tier 1] H10: 7件不完全インシデントの breakdown 表追加

**問題**: 7/36 件が F1 < 1.000 だが、個別の原因分析がゼロ。

**修正箇所**: L982-993 の「Baseline imperfection」段落の直後

**追加内容**: 7件の表（インシデント名は tests/incidents/*.yaml のファイル名から特定）:
```latex
\begin{table}[h]
\centering
\caption{Seven incidents with imperfect cascade reproduction.}
\small
\begin{tabular}{@{}llll@{}}
\toprule
\textbf{Incident} & \textbf{Year} & \textbf{Mode} & \textbf{Root Cause} \\
\midrule
... (7件) ...
\bottomrule
\end{tabular}
\end{table}
```

**注意**: 7件の特定には `tests/incidents/` ディレクトリの YAML ファイルを確認し、実際に cascade engine を実行して F1 < 1.000 のものを特定する必要がある。特定できない場合は、段落内に over-propagation/under-propagation の原因を一般論として記述する。

#### 3-6. [Tier 0] P: 54件評価への cross-reference 追加

**問題**: arXiv (36件/F1=0.971) と ICSE-NIER (54件/F1=0.87) で数値が不整合。

**修正箇所**: L993 の「Baseline imperfection」段落の末尾

**追加内容** (1文):
```latex
A separate evaluation on a 54-incident superset spanning 21 providers
and 2017--2024 shows $F_1 = 0.87$ and recall $= 0.81$, consistent
with the modeling limitations described above; details are reported
in a companion short paper.
```

### 注意事項
- `faultray-paper.tex` の L679 以前は編集しない（Window 2 が担当）
- `faultray-paper.tex` の L1098 以降は編集しない（Window 4 が担当）
- `cascade.py` は編集しない（Window 1 が担当）
- 修正後は `pdflatex faultray-paper.tex` でコンパイルエラーがないことを確認

---

## Window 4: LaTeX §2 Related Work + bib + Discussion 修正

### 担当ファイル
- `paper/faultray-paper.tex` の **L159-350**（§2 Related Work）と **L1098以降**（§8-§10 + bib）

### 修正項目 (4件)

#### 4-1. [Tier 1] J1: Krasnovsky DPA 受賞の記載

**問題**: Krasnovsky が ICSE 2026 Distinguished Paper Award を受賞したが、論文に記載がない。記載しないと「知らなかったのか、意図的に隠したのか」と疑われる。

**修正箇所**: L176-195 の §2.2 (In-Memory Graph Simulation)

**修正内容**: L177 の引用に DPA を追記:
```latex
% Before:
Krasnovsky~\cite{krasnovsky2026} (ICSE-NIER~2026, arXiv:2506.11176)

% After:
Krasnovsky~\cite{krasnovsky2026} (ICSE-NIER~2026, Distinguished Paper
Award; arXiv:2506.11176)
```

同時に bibentry (L1414-1420) も更新:
```latex
% note フィールドを追加:
note = {Distinguished Paper Award},
```

#### 4-2. [Tier 1] J3: Nasar 2026 の追加引用

**問題**: TLA+ によるインフラ信頼性の形式検証が 2026 年に出版済み。FaultRay が「TLA+ verification is future work」と書いている間に、他の研究者は同年に適用済み。

**修正箇所**: L225-239 の §2.4 (Formal Methods for Distributed Systems)

**追加内容**: VLSTS の後に 1 文追加:
```latex
More recently, Nasar~\cite{nasar2026} applied TLA+ to formally verify
microgrid reliability models, demonstrating that mechanical
verification of infrastructure availability properties is feasible
with current tools. \textsc{FaultRay}'s proof sketches have not been
mechanically verified (\S\ref{sec:discussion}); we consider this an
important gap.
```

bib に追加:
```latex
\bibitem{nasar2026}
M.~Nasar,
``Formal validation for microgrid reliability based on TLA+,''
\textit{Journal of Electrical Engineering}, vol.~77, no.~1,
pp.~46--56, 2026. doi:10.2478/jee-2026-0006.
```

#### 4-3. [Tier 1] J4: 参考文献の non-peer-reviewed 率改善

**問題**: 24 references のうち 7 件 (29%) が non-peer-reviewed。tool 4 件を survey 引用に統合すれば 12% に改善可能。

**修正箇所**: bib (L1343-1501) と §2.1 (L161-172) の本文参照

**修正内容**:
Gremlin, Steadybit, AWS FIS, LitmusChaos の 4 件は本文中で個別に引用する代わりに、chaos-mlr-2025 survey で包括的に参照する。

```latex
% §2.1 Before:
Commercial platforms---Gremlin~\cite{gremlin2020},
Steadybit~\cite{steadybit2023},
and AWS Fault Injection Simulator (FIS)~\cite{aws-fis}---provide
managed fault injection ...
LitmusChaos~\cite{litmuschaos} and Chaos Mesh are CNCF projects ...

% §2.1 After:
Commercial platforms (Gremlin, Steadybit, AWS~FIS) and open-source
CNCF projects (LitmusChaos, Chaos Mesh) provide managed fault
injection in production or staging environments; a comprehensive
survey is provided by Joshua et~al.~\cite{chaos-mlr-2025}.
```

ただし Table 1 (L330-350) で Gremlin 等を行として使っている場合は、表の注釈で URL を記載しつつ bib entry 自体は残す。**表との整合性を確認してから削除を判断する**こと。

#### 4-4. [Tier 1] J5 (ボーナス): AI reliability survey の追加引用

**修正箇所**: Discussion §9 の scope 削除理由 (L1217-1233)

**追加内容**: L1226 の MAST 引用の後に 1 文追加:
```latex
A broader framework for AI agent reliability engineering has been
proposed by [cite]; we defer to these domain-specific efforts.
```

bib に追加:
```latex
\bibitem{airel2026}
[Author et al.],
``Towards a Science of AI Agent Reliability,''
arXiv:2602.16666, Feb.~2026.
```

**注意**: arXiv:2602.16666 の正確な著者名を WebSearch で確認してから記載すること。

### 注意事項
- `faultray-paper.tex` の L350-L1098 は編集しない（Window 2, 3 が担当）
- `cascade.py`, `availability_model.py` は編集しない
- §2 の編集は L350 まで。Table 1 (L321-350) を変更する場合は行を追加するだけで削除しない
- 修正後は `pdflatex faultray-paper.tex && bibtex faultray-paper` でコンパイルエラーがないことを確認

---

## 実行順序と統合

```
4ウィンドウ同時開始
     │
     ├── Window 1: cascade.py (コード) ─────────────────────┐
     ├── Window 2: tex §4 (形式仕様) ──────────────────────┤
     ├── Window 3: tex §5+§7 + availability_model.py ──────┤
     └── Window 4: tex §2+bib+§8-10 ──────────────────────┤
                                                            │
                                                            ▼
                                                    全ウィンドウ完了後
                                                            │
                                                            ▼
                                               pdflatex 3回 + bibtex
                                               pytest 全テスト実行
                                               統合コンパイル確認
```

### 統合時の注意
- Window 2, 3, 4 は同じ .tex ファイルの異なる行範囲を編集する
- 行挿入による行番号ズレに注意。各ウィンドウは自分の担当範囲の末尾に追加する形を推奨
- 統合後に `pdflatex` 3回 + `bibtex` 1回でクリーンコンパイルを確認

---

## 各ウィンドウへのコピペ用プロンプト

### Window 1 に貼るプロンプト:
```
FaultRay v12 修正作業。あなたは Window 1 担当: cascade.py のコード修正。

指示書を読んで作業してください:
cat /home/user/repos/faultray/paper/PARALLEL_FIX_INSTRUCTIONS.md

担当: 項目 1-1, 1-2, 1-3, 1-4 の4件。
編集対象: cascade.py, cli/simulate.py, tests/ のみ。
faultray-paper.tex と availability_model.py は読取のみ、編集禁止。

弱点の詳細は /home/user/repos/faultray/paper/WEAKNESS_ANALYSIS.md を参照。
```

### Window 2 に貼るプロンプト:
```
FaultRay v12 修正作業。あなたは Window 2 担当: LaTeX §4 Cascade Engine の形式仕様修正。

指示書を読んで作業してください:
cat /home/user/repos/faultray/paper/PARALLEL_FIX_INSTRUCTIONS.md

担当: 項目 2-1, 2-2, 2-3, 2-4, 2-5 の5件。
編集対象: faultray-paper.tex の L429-679 のみ。
他の行範囲、cascade.py、availability_model.py は編集禁止。

弱点の詳細は /home/user/repos/faultray/paper/WEAKNESS_ANALYSIS.md を参照。
```

### Window 3 に貼るプロンプト:
```
FaultRay v12 修正作業。あなたは Window 3 担当: LaTeX §5 Availability + §7 Evaluation + availability_model.py。

指示書を読んで作業してください:
cat /home/user/repos/faultray/paper/PARALLEL_FIX_INSTRUCTIONS.md

担当: 項目 3-1, 3-2, 3-3, 3-4, 3-5, 3-6 の6件。
編集対象: faultray-paper.tex の L683-1098 と availability_model.py のみ。
他の行範囲、cascade.py は編集禁止。

弱点の詳細は /home/user/repos/faultray/paper/WEAKNESS_ANALYSIS.md を参照。
```

### Window 4 に貼るプロンプト:
```
FaultRay v12 修正作業。あなたは Window 4 担当: LaTeX §2 Related Work + bib + Discussion。

指示書を読んで作業してください:
cat /home/user/repos/faultray/paper/PARALLEL_FIX_INSTRUCTIONS.md

担当: 項目 4-1, 4-2, 4-3, 4-4 の4件。
編集対象: faultray-paper.tex の L159-350 と L1098以降のみ。
L350-L1098 の範囲、cascade.py、availability_model.py は編集禁止。

弱点の詳細は /home/user/repos/faultray/paper/WEAKNESS_ANALYSIS.md を参照。
```
