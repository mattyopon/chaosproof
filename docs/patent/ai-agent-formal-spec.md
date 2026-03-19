# FaultRay AI Agent Failure Simulation — Formal Specification

## 1. Formal Definition of Hallucination Probability

### Definition

Let **H(a, D, I)** denote the probability of hallucination for agent **a**, given:

- **D** = set of data sources available to agent a (grounding databases, retrieval indices, tool outputs)
- **I** = infrastructure state (mapping of each component to {HEALTHY, DEGRADED, DOWN, OVERLOADED})

### Base Hallucination Rate

Every agent a has an intrinsic base hallucination rate:

```
h₀(a) ∈ [0, 1]
```

This reflects the model's inherent tendency to produce ungrounded outputs even when all data sources are available. It is determined by model quality, prompt engineering, and temperature settings.

### Data Source Dependency Weights

For each data source **d ∈ D(a)**, define:

- **w(d)** ∈ [0, 1]: the dependency weight — how critical data source d is to agent a's grounding. Sum of all w(d) need not equal 1; each weight represents an independent contribution to hallucination risk.

### Per-Source Hallucination Contribution

For each data source d that agent a depends on, compute the per-source hallucination probability **h_d** based on the infrastructure state of d:

```
If status(d, I) = HEALTHY:
    h_d = h₀(a)                                          (no additional risk)

If status(d, I) = DOWN:
    h_d = h₀(a) + (1 - h₀(a)) × w(d)                    (full dependency risk)

If status(d, I) = DEGRADED:
    h_d = h₀(a) + (1 - h₀(a)) × w(d) × δ               (partial risk)
    where δ ∈ (0, 1) is the degradation factor (default: 0.5)

If status(d, I) = OVERLOADED:
    h_d = h₀(a) + (1 - h₀(a)) × w(d) × ω               (overload risk)
    where ω ∈ (0, 1) is the overload factor (default: 0.3)
```

The formula `h₀(a) + (1 - h₀(a)) × w(d)` ensures:
- When h₀ = 0 and w(d) = 1: h_d = 1 (total hallucination when fully dependent source is down)
- When h₀ = 1: h_d = 1 regardless of data source state (already hallucinating)
- h_d is always ∈ [h₀(a), 1]

### Combined Hallucination Probability

The combined probability uses the complementary product (independence assumption):

```
H(a, D, I) = 1 - ∏_{d ∈ D(a), status(d,I) ≠ HEALTHY} (1 - h_d)
```

When all data sources are HEALTHY: H(a, D, I) = h₀(a) (falls back to base rate).

When no data sources exist (D(a) = ∅): H(a, D, I) = h₀(a).

### Properties

1. **Monotonicity**: H increases as more data sources fail
2. **Boundedness**: H(a, D, I) ∈ [h₀(a), 1]
3. **Compositionality**: Each data source contributes independently
4. **Infrastructure-dependent**: H is a function of I, linking agent behavior to infrastructure state

---

## 2. Cross-Layer Cascade Model

### Layer Definitions

| Layer | Name | Domain | Examples |
|-------|------|--------|----------|
| L1 | Infrastructure | Physical/virtual component failures | Server crash, disk full, network partition |
| L2 | Data Availability | Grounding source accessibility | Database down, cache miss, API timeout |
| L3 | Agent Behavior | AI-specific failure modes | Hallucination, context overflow, tool failure |
| L4 | Downstream Impact | Propagation to consumers | Agent output fed to other agents/systems |

### Formal Transition Model

```
L1: Infrastructure fault F occurs on component c
    ↓
    For each data source d reachable from c in dependency graph G:
        status(d, I) transitions from HEALTHY to {DEGRADED, DOWN, OVERLOADED}

L2: Data source d becomes unavailable/degraded
    ↓
    For each agent a where d ∈ D(a):
        H(a, D, I) is recomputed using updated status(d, I)
        If H(a, D, I) > threshold_hallucination:
            agent a enters DEGRADED state (hallucination mode)

L3: Agent a produces unreliable output
    ↓
    For each downstream consumer b that receives output from a:
        If b is an agent:
            b's effective input quality degrades
            H(b, D', I) increases (tainted input acts as degraded data source)
        If b is a system/user:
            Impact propagates as corrupted data

L4: Compound cascade
    ↓
    Agent-to-agent propagation follows the same graph traversal
    as infrastructure cascades, but in the agent dependency subgraph
```

### Cascade Severity at Each Layer

```
severity(L1) = f(component criticality, redundancy)
severity(L2) = f(number of affected data sources, dependency weights)
severity(L3) = f(H(a, D, I), agent criticality, output consumers)
severity(L4) = ∑ severity(L3_i) for all agents i in cascade chain
```

---

## 3. Agent Failure Taxonomy (Complete)

### 3.1 Hallucination

- **ID**: `hallucination`
- **Definition**: Agent produces confident but factually incorrect output that is not grounded in available data sources.
- **Formal condition**: Output O of agent a satisfies ¬∃d ∈ D(a): O is derivable from d
- **Health impact**: DEGRADED (agent still responds, but outputs are unreliable)
- **Trigger**: Data source dependency severed; H(a, D, I) exceeds threshold
- **Recovery**: Restore data source access; no time-based recovery (wrong output persists)

### 3.2 Context Overflow

- **ID**: `context_overflow`
- **Definition**: Input to agent exceeds the model's token limit, causing loss of critical context from earlier in the conversation or request.
- **Formal condition**: |tokens(input)| > max_context_tokens(a)
- **Health impact**: DOWN (agent cannot process the request)
- **Trigger**: Cumulative input tokens across chained requests exceed context window
- **Recovery**: Context reset (estimated 5 seconds)

### 3.3 Token Exhaustion

- **ID**: `token_exhaustion`
- **Definition**: API token budget is fully consumed; no further API calls can be made.
- **Formal condition**: consumed_tokens(a) >= budget_tokens(a)
- **Health impact**: DOWN (agent is completely non-functional)
- **Trigger**: High-volume usage without budget controls
- **Recovery**: Manual budget replenishment (no automatic recovery)

### 3.4 Prompt Injection

- **ID**: `prompt_injection`
- **Definition**: Adversarial input in external data hijacks the agent's behavior, causing it to follow attacker-controlled instructions instead of its intended purpose.
- **Formal condition**: ∃ substring s in input: s overrides system prompt directives
- **Health impact**: DEGRADED (agent responds, but behavior is compromised)
- **Trigger**: Unsanitized external input containing directive text
- **Recovery**: No automatic recovery; requires input sanitization

### 3.5 Tool Call Loop

- **ID**: `agent_loop`
- **Definition**: Agent enters an infinite or excessively long cycle of tool invocations without making progress toward completing the task.
- **Formal condition**: |tool_calls(a, window_t)| > max_iterations(a) ∧ ¬progress(a)
- **Health impact**: DOWN (agent consumes resources without producing useful output)
- **Trigger**: Ambiguous task, broken tool responses, reasoning loops
- **Recovery**: Manual intervention required (kill and restart)

### 3.6 Confidence Miscalibration

- **ID**: `confidence_miscalibration`
- **Definition**: Agent assigns high confidence scores to incorrect outputs, causing downstream systems to trust unreliable information.
- **Formal condition**: confidence(a, O) > θ_high ∧ correctness(O) < θ_low
- **Health impact**: DEGRADED (agent produces output, but confidence signals are misleading)
- **Trigger**: Distribution shift in input data; model fine-tuning artifacts; degraded grounding
- **Recovery**: Recalibration or model update required

### 3.7 Chain-of-Thought Collapse

- **ID**: `cot_collapse`
- **Definition**: Agent's intermediate reasoning degrades partway through a multi-step generation, producing a correct-looking prefix followed by incoherent or incorrect continuation.
- **Formal condition**: quality(reasoning_step_i) > θ for i < k, quality(reasoning_step_i) < θ for i >= k
- **Health impact**: DEGRADED (partial output may be usable, but final answer is unreliable)
- **Trigger**: Token budget pressure; context saturation; high complexity tasks
- **Recovery**: Retry with reduced complexity or increased token budget

### 3.8 Output Amplification

- **ID**: `output_amplification`
- **Definition**: A hallucinated or incorrect output from agent A is consumed by agent B, which treats it as ground truth and amplifies the error in its own output, potentially propagating to further agents.
- **Formal condition**: H(a) > 0 ∧ output(a) ∈ input(b) → H_effective(b) > H(b, D, I)
- **Health impact**: DEGRADED to DOWN (depends on chain length and criticality)
- **Trigger**: Agent-to-agent data flow without validation gates
- **Recovery**: Requires breaking the cascade chain; validation at agent boundaries

### 3.9 Grounding Data Staleness

- **ID**: `grounding_staleness`
- **Definition**: The data sources used for grounding are technically available but contain outdated information, causing the agent to produce responses that were correct at cache time but are no longer accurate.
- **Formal condition**: age(data(d)) > max_freshness(d) ∧ status(d, I) = HEALTHY
- **Health impact**: DEGRADED (agent responds with stale but structurally valid data)
- **Trigger**: Cache TTL expiry not detected; replication lag; stale index
- **Recovery**: Cache invalidation; data refresh

### 3.10 Rate Limit Cascade

- **ID**: `llm_rate_limit`
- **Definition**: API provider throttles requests, causing dependent agents to experience timeouts that cascade through the orchestration layer, with each retry amplifying the load.
- **Formal condition**: request_rate(a) > rate_limit(endpoint) → queue_depth grows → timeout cascade
- **Health impact**: OVERLOADED (requests are throttled, not failed)
- **Trigger**: Traffic spike; concurrent agent invocations; retry storms
- **Recovery**: Rate limit window reset (estimated 60 seconds)

---

## 4. Agent-to-Agent Cascade Propagation Model

### Definition

When agents form a directed acyclic graph (DAG) of data flow, a failure in one agent can propagate through the graph:

```
Given agent graph G_agent = (A, E) where:
    A = set of agents
    E = set of directed edges (a_i → a_j) meaning a_j consumes output of a_i

For a source agent a_s with hallucination probability H(a_s):
    For each edge (a_s → a_t) ∈ E:
        amplification_factor(a_s, a_t) = 1.0 if a_t has no independent verification
                                       = v(a_t) ∈ [0, 1) if a_t can partially verify
        H_effective(a_t) = 1 - (1 - H(a_t, D, I)) × (1 - H(a_s) × amplification_factor(a_s, a_t))
```

### Compound Cascade Probability

For a chain of agents [a₁, a₂, ..., aₙ]:

```
H_chain(aₙ) = 1 - ∏_{i=1}^{n} (1 - H_effective(aᵢ))
```

This models the compounding effect where each agent in the chain adds its own hallucination risk on top of inherited risk from upstream agents.

### Properties

1. **Amplification**: H_chain(aₙ) >= max(H(aᵢ)) for all i — the chain is at least as risky as its riskiest member
2. **Monotonic growth**: Adding agents to the chain never decreases compound risk
3. **Mitigation**: Validation gates between agents reduce amplification_factor, bounding cascade growth

---

## 5. Novelty Claims

### Prior Art

1. **Chaos Engineering for Infrastructure** (Gremlin, Chaos Monkey, LitmusChaos): Injects infrastructure-level faults (kill process, network partition, disk fill) into live or staging environments. Operates exclusively at the infrastructure layer (L1). Does not model AI agent behavior.

2. **ML Model Testing** (MLOps tools, model validation frameworks): Tests model accuracy, drift, and bias. Operates at the model layer only. Does not connect model failures to infrastructure root causes.

3. **LLM Evaluation Frameworks** (benchmarks, red-teaming tools): Evaluate LLM outputs for hallucination, toxicity, and correctness. Operate at the prompt/response level. Do not simulate infrastructure conditions that cause hallucinations.

### Novel Contributions

1. **Cross-Layer Simulation (Infrastructure + AI Agent Behavior in a Unified Model)**: FaultRay is the first system to model infrastructure components and AI agents in a single directed graph, enabling simulation of how infrastructure faults propagate through data availability layers to affect agent behavior. No prior system combines L1-L4 in one simulation.

2. **Hallucination Probability as a Function of Infrastructure State**: The formal model H(a, D, I) defines hallucination probability as a computable function of which infrastructure components are up, down, or degraded. This is fundamentally different from prior art that treats hallucination as a static property of the model. Prior art: hallucination = f(model). Novel: hallucination = f(model, infrastructure_state).

3. **Agent Cascade Propagation**: The model of agent-to-agent cascade — where agent A's hallucination is fed to agent B, producing compound failure — is not addressed by any existing chaos engineering or ML testing tool. The compound probability H_chain formally quantifies multi-agent failure amplification.

4. **Complete Agent Failure Taxonomy Integrated with Infrastructure Simulation**: The 10-mode taxonomy (hallucination, context overflow, token exhaustion, prompt injection, tool call loop, confidence miscalibration, chain-of-thought collapse, output amplification, grounding data staleness, rate limit cascade) is the first to be formally defined with infrastructure-state triggers and integrated into a cascade simulation engine.

5. **Predictive Hallucination Thresholds from Topology Analysis**: The system can predict, before any fault occurs, which infrastructure failures would push agent hallucination probability above acceptable thresholds — enabling proactive monitoring rule generation from topology alone.
