# FaultRay Paper Rewrite Plan (v12 Draft)

**Date**: 2026-04-08
**Author**: Yutaro Maeda
**Status**: Draft (post-competitive-review pivot)

## Why this rewrite

The v11 paper (`faultray-paper.tex`, 1021 lines) was framed as a joint
infrastructure + AI-agent reliability paper. Competitive review on 2026-04-08
established the following hard constraints:

1. **10-mode AI agent failure taxonomy is pre-dated** by:
   - MAST (arXiv:2503.13657, NeurIPS 2025) — 14-mode, kappa=0.88, 1600+ annotated traces
   - Microsoft "Taxonomy of Failure Mode in Agentic AI Systems" whitepaper
   - Winston et al. AST 2025 "Tool-Augmented LLM Failure Taxonomy"
   - arXiv:2509.18970 "LLM-based Agents Suffer from Hallucinations"
   - arXiv:2508.02121 "A Survey on AgentOps"
   - arXiv:2601.22984 PIES Taxonomy
   - arXiv:2507.15330 QSAF
   - Contesting §6.4 as a research contribution is unwinnable.

2. **Hallucination probability model δ/ω parameters are hardcoded engineering
   judgment**, not empirical measurement. The v11 §9 Discussion already
   self-discloses this. Presenting §6 as empirical research is indefensible
   without a real LLM calibration study.

3. **F1=1.000 backtest is post-hoc fit to 18 known incidents.** The v11
   §7.1 already self-discloses this. The cascade engine §4 has formal proofs
   (termination, O(|C|+|E|), monotonicity, causality, blast radius bound) but
   the prospective prediction claim is weak.

4. **12 prior works checked** (MAST / 2509.18970 / 2508.02121 / PIES / 2505.03096
   / ChaosEater / QSAF / ReliabilityBench / Microsoft / Winston / agent-chaos /
   flakestorm) do **not** duplicate §4 Cascade Engine LTS + §5 N-Layer
   Availability Model + §6 cross-layer H(a,D,I). This is the surviving
   defensible contribution.

## Target rewrite: "FaultRay: A Formal Cascade Propagation Semantics and N-Layer Availability Decomposition Tool for In-Memory Infrastructure Resilience Simulation"

### Strip these sections entirely

| Section | Current lines | Reason to strip |
|---|---|---|
| §6 AI Agent Cross-Layer Failure Simulation | 588-718 | Taxonomy contribution pre-dated; H(a,D,I) empirical validation missing. Move remaining LTS-compatible pieces into a tool section appendix. |
| §6.3 10-Mode Failure Taxonomy (Table 2) | 663-693 | MAST covers this ground with higher empirical rigor. Drop entirely. |
| §6.5 Agent-to-Agent Compound Cascade | 695-718 | Functional in the tool, but presenting it as a research contribution is the weakest angle and overlaps with arXiv:2603.04474 "From Spark to Fire" (SIS/SIR infection model on dependency graphs). Drop or relegate to §Implementation. |

### Keep as core contributions

| Section | Current lines | Strengthen how |
|---|---|---|
| §4 Cascade Engine — Formal Specification | 287-490 | (1) Expand termination proof from sketch to full LTS argument. (2) Add a cyclic graph case study (current Corollary 1 D_max=20 is hand-waved). (3) Add a **prospective experiment**: apply the cascade engine to a previously-unreported incident (e.g., a 2026-Q1 cloud outage that's published after v11 was written) and measure precision/recall on unseen topology. (4) Compare against HPE SPOF patent (static) and Chaos Mesh (real fault) quantitatively. |
| §5 N-Layer Availability Limit Model | 491-587 | (1) Justify the `min(A_L1..A_L5)` composition theoretically (Why min and not product?). (2) Add a sensitivity analysis: which layer dominates for different infrastructure classes (startup vs enterprise vs regulated FI). (3) Compare against classical MTBF/MTTR (Trivedi 2001) and explain what the additional decomposition buys. |

### Empirical work to do before submission

1. **Prospective cascade validation (3-5 weeks)**
   - Build 3-5 topology graphs for recent (post-v11-paper-date) incidents
   - Pick from 2026 Q1 outages (AWS/GCP/Azure/Cloudflare — public post-mortems)
   - Inject documented root cause, measure cascade prediction vs ground truth
   - Report honest precision/recall/F1 (**not** the post-hoc 1.000)
   - Include failure cases (incidents FaultRay got wrong)

2. **Prospective N-Layer validation (2-3 weeks)**
   - Pick 5-10 real systems with published SLA numbers + architecture
   - Compute FaultRay's L1..L5 decomposition
   - Compare predicted ceiling vs actual reported availability
   - Sensitivity analysis: which assumptions dominate?

3. **Optional: §6 calibration study (4-6 weeks)**
   - If time permits and the reliability venue isn't tight on scope
   - Measure actual hallucination rate on GPT-4 / Claude / Llama3 under
     controlled RAG degradation (DB down / cache miss / partial retrieval)
   - Fit δ and ω from data instead of hardcoded 0.5 / 0.3
   - Report the calibration error bars
   - **If this fails** (e.g., δ turns out to vary by 3x across models),
     keep §6 as "limitation + future work" and drop the empirical claim

### Target venues (in priority order)

| Venue | Type | Deadline | Fit |
|---|---|---|---|
| **SRECon EMEA 2026** (Dublin, October) | Industry talk + short paper | ~August 2026 | **Strongest fit**. SRE community, chaos engineering central, tool papers welcomed |
| **DSN 2027 Tool Track** | Peer-reviewed tool paper | ~December 2026 | Formal LTS proofs + real incident backtest = exact fit for DSN tools track |
| **SoCC 2026 / 2027** | Systems conference | ~May / June | Competitive but tool papers with formal proofs land |
| **IEEE TSE / TOSEM** | Journal | Rolling | Slower, higher bar, requires prospective study |
| **arXiv tool paper** | Preprint | Immediate | Do first as insurance, update with venue version later |

**Priority**: arXiv first (1-2 weeks), then aim for SRECon EMEA as primary
target. DSN tool track as backup.

### Avoid these venues

- **NeurIPS / ICLR / AAAI** — LLM agent reliability track. Direct MAST collision, review is brutal. Do not submit.
- **FAccT / AIES** — FAI/ML fairness track, wrong audience.
- **DEFCON / BlackHat** — security conference, wrong framing.

### Rewrite checklist

- [ ] Create new branch: `paper/v12-rewrite`
- [ ] Copy v11 to `paper/faultray-paper-v11-archive.tex`
- [ ] Rewrite Abstract (drop AI agent claim, emphasize formal cascade + N-layer)
- [ ] Rewrite Introduction (remove AI agent motivation, focus on chaos engineering gap)
- [ ] Rewrite §2 Related Work — expand chaos engineering subsection with:
  - [ ] Chaos Mesh (CNCF incubating)
  - [ ] LitmusChaos
  - [ ] AWS FIS details
  - [ ] Azure Chaos Studio
  - [ ] SteadyBit
  - [ ] Google DiRT / Resilience teams (public papers)
  - [ ] Acknowledge MAST / 2505.03096 / agent-chaos / flakestorm as **orthogonal** (LLM-MAS focused, not infrastructure cascade)
- [ ] Strip §6 entirely (move to appendix or new §Implementation subsection as a tool feature)
- [ ] Add §4.5 Prospective Validation (new experiment results)
- [ ] Rewrite §7 Evaluation:
  - [ ] Move 18-incident backtest to §4.6 as "Historical Reproduction"
  - [ ] Add new prospective experiment results as §7.1
  - [ ] Add sensitivity analysis as §7.2
  - [ ] Honest limitations section
- [ ] Rewrite §9 Discussion — keep δ/ω self-disclosure if §6 remains as tool feature
- [ ] Rewrite Conclusion — drop "first to bridge infrastructure and AI agent reliability" claim
- [ ] Update BibTeX with MAST + related works as Related Work citations

### Estimated timeline

| Week | Task |
|---|---|
| 1 | Branch + Abstract/Intro rewrite + venue CFP check |
| 2-3 | Prospective cascade validation experiment |
| 4-5 | §2 Related Work full expansion + §4 termination proof expansion |
| 6 | §5 N-Layer sensitivity analysis + §7 Evaluation rewrite |
| 7-8 | §6 tool section rewrite + Conclusion + final editing |
| 9 | Internal review (self-review + optional external reader) |
| 10 | arXiv submit + BigTeX polish |
| 11-12 | SRECon CFP submit + prepare talk draft |

**Total**: ~3 months part-time (10-15 h/week) assuming no day-job interruption.
Realistic for post-transfer downtime or weekend project.

### Hard constraints / non-negotiables

1. **No overclaim in the rewrite.** The v11 Discussion self-disclose pattern (δ/ω engineering judgment, F1 post-hoc) is the right template. Extend to the new prospective experiment.
2. **No DORA / compliance claims.** Regulatory framing is out. If the paper mentions DORA at all, it's as a motivation in §1 Introduction, not as a capability claim.
3. **No AI agent reliability as a contribution.** The AI agent extension is a **tool feature** (appendix or §Implementation), not a research contribution.
4. **No "first to bridge" claims** without a concrete differentiator table against 2505.03096, agent-chaos, flakestorm. If we can't articulate the difference in one sentence, drop the "bridge" framing.
5. **Honest Related Work.** Every paper in the 12-work list gets a citation. No pretending they don't exist.

### Ground truth anchors

These facts are from 2026-04-08 competitive review. Do not re-litigate:

- `paper/faultray-paper.tex` v11 is the starting point (1021 lines, Zenodo DOI 10.5281/zenodo.19139911)
- USPTO provisional 64/010,200 filed 2026-03-19, non-provisional deadline 2027-03-19
- The cascade engine is implemented in `src/faultray/simulator/cascade.py` (and `agent_cascade.py` for the AI agent extension)
- The N-layer model is implemented in `src/faultray/simulator/availability_model.py`
- 65% of simulator/*.py files are external-reference-zero (islands). Do not cite them as evidence of "100+ engines" in the paper unless each is individually exercised in the prospective experiment.
- MAST paper Semantic Scholar: https://www.semanticscholar.org/paper/Why-Do-Multi-Agent-LLM-Systems-Fail-Cemri-Pan/c83b6a023a5c5ec71b44920a41b41fc007266c44
