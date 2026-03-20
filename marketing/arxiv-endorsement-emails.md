# arXiv Endorsement Request Emails

**Submitter:** Yutaro Maeda (independent researcher)
**Target category:** cs.SE (Software Engineering)
**Endorsement code:** F4NYWP
**Paper title:** *(your arXiv submission title)*
**GitHub:** https://github.com/mattyopon/faultray

---

## Contact Information (verified)

| Paper | Lead Author | Contact |
|-------|-------------|---------|
| arXiv 2506.11176 | Anatoly A. Krasnovsky | Innopolis University, Dept. of CS&E — a.krasnovsky@innopolis.university *(email format inferred from institution; verify via arXiv show-email link)* |
| arXiv 2511.07865 | Daisuke Kikuta | NTT Research Engineer — daisuke.kikuta@ntt.com *(confirmed via public sources)* |
| arXiv 2412.01416 | Joshua Owotogbe | Tilburg University / JADS — j.s.owotogbe@tilburguniversity.edu *(confirmed via public sources)* |

> Note: Krasnovsky's email was not found in public sources. Use the arXiv "view email" link at https://arxiv.org/show-email/2b8ad631/2506.11176 to retrieve it before sending.

---

## Email 1 — To Anatoly A. Krasnovsky (arXiv 2506.11176)

**Paper:** "Model Discovery and Graph Simulation: A Lightweight Gateway to Chaos Engineering"
**Affiliation:** Innopolis University, Russia
**Why this connection:** Krasnovsky's paper and FaultRay share an almost identical core thesis — that a lightweight graph topology model is sufficient to estimate availability under fail-stop faults, without touching real infrastructure. His "model discovery" concept maps directly to FaultRay's topology ingestion pipeline.

---

**Subject:** arXiv Endorsement Request — Graph-Based Infrastructure Resilience Simulation (cs.SE)

Dear Dr. Krasnovsky,

I'm Yutaro Maeda, an independent researcher and the author of FaultRay, an open-source system for zero-risk chaos engineering via graph simulation (GitHub: https://github.com/mattyopon/faultray).

Your paper "Model Discovery and Graph Simulation" (arXiv 2506.11176) directly informed my work. You demonstrate that a connectivity-only topological model suffices for fast availability estimation under fail-stop faults — FaultRay operationalizes the same principle: infrastructure topology is ingested as a directed graph, and failure scenarios are simulated entirely in memory, producing a quantitative resilience score before any real change is applied. My paper extends this with a formally specified cascade engine and a multi-layer availability ceiling model, and has been filed as a US provisional patent application.

I would be honored if you would endorse my submission to arXiv cs.SE. The endorsement code is **F4NYWP**. Instructions are at https://arxiv.org/auth/endorse.

I recognize this is a favor and am happy to share a preprint if helpful.

Thank you for your time.

Yutaro Maeda
https://github.com/mattyopon/faultray

---

## Email 2 — To Daisuke Kikuta (arXiv 2511.07865)

**Paper:** "LLM-Powered Fully Automated Chaos Engineering: Towards Enabling Anyone to Build Resilient Software Systems at Low Cost"
**Affiliation:** NTT (Nippon Telegraph and Telephone)
**Email:** daisuke.kikuta@ntt.com
**Why this connection:** Kikuta's ChaosEater uses an LLM agent to automate chaos engineering workflows end-to-end. FaultRay's patent covers AI agent failure simulation — specifically modeling how infrastructure failures propagate into LLM agent hallucination. The two papers are complementary: ChaosEater automates the *injection* side; FaultRay provides the *simulation-before-injection* and *agent failure modeling* side.

---

**Subject:** arXiv Endorsement Request — Graph-Based Infrastructure Resilience Simulation (cs.SE)

Dear Mr. Kikuta,

I'm Yutaro Maeda, an independent researcher and the author of FaultRay, an open-source system for zero-risk chaos engineering via graph simulation (GitHub: https://github.com/mattyopon/faultray).

Your paper "LLM-Powered Fully Automated Chaos Engineering" (arXiv 2511.07865) is closely related to my work. ChaosEater targets the automation of chaos experiment workflows using LLMs — FaultRay takes a complementary approach: rather than injecting faults into live systems, it simulates thousands of failure scenarios in memory from a graph model of the infrastructure, and — uniquely — also models how infrastructure failures propagate into LLM agent behavior (hallucination probability as a function of infrastructure state, agent-to-agent cascade). This has been filed as a US provisional patent application.

I would be grateful if you would endorse my submission to arXiv cs.SE. The endorsement code is **F4NYWP**. Instructions are at https://arxiv.org/auth/endorse.

I'm happy to share a preprint if that would help you assess the fit.

Thank you for your time.

Yutaro Maeda
https://github.com/mattyopon/faultray

---

## Email 3 — To Joshua Owotogbe (arXiv 2412.01416)

**Paper:** "Chaos Engineering: A Multi-Vocal Literature Review"
**Affiliation:** Jheronimus Academy of Data Science / Tilburg University, Netherlands
**Email:** j.s.owotogbe@tilburguniversity.edu
**Why this connection:** Owotogbe's multi-vocal literature review systematically analyzed 88 sources across academic and grey literature on chaos engineering practices and gaps. FaultRay addresses several open research challenges his review surfaces — particularly the lack of zero-risk pre-production resilience evaluation tools and the absence of AI agent failure modeling in the chaos engineering literature.

---

**Subject:** arXiv Endorsement Request — Graph-Based Infrastructure Resilience Simulation (cs.SE)

Dear Mr. Owotogbe,

I'm Yutaro Maeda, an independent researcher and the author of FaultRay, an open-source system for zero-risk chaos engineering via graph simulation (GitHub: https://github.com/mattyopon/faultray).

Your multi-vocal literature review "Chaos Engineering: A Multi-Vocal Literature Review" (arXiv 2412.01416) maps the field thoroughly and helped me position my contribution clearly. Two gaps your review identifies are directly addressed by FaultRay: (1) the risk and cost barrier of live fault injection — FaultRay eliminates this by running simulations entirely in memory against a graph model — and (2) the absence of chaos engineering frameworks for AI agent systems — FaultRay models LLM agent failure modes (hallucination, context overflow, agent-to-agent cascade) as functions of underlying infrastructure state. The system has been filed as a US provisional patent application.

I would be honored if you would endorse my submission to arXiv cs.SE. The endorsement code is **F4NYWP**. Instructions are at https://arxiv.org/auth/endorse.

Thank you for your time, and for the thorough survey — it's a valuable resource for the field.

Yutaro Maeda
https://github.com/mattyopon/faultray

---

## Notes for Sender

- **Word counts:** Email 1: ~190 words | Email 2: ~195 words | Email 3: ~195 words (all under 200).
- **Krasnovsky email:** Not publicly confirmed. Retrieve from https://arxiv.org/show-email/2b8ad631/2506.11176 before sending.
- **Kikuta email** (`daisuke.kikuta@ntt.com`) and **Owotogbe email** (`j.s.owotogbe@tilburguniversity.edu`) are confirmed via public sources.
- Send one email at a time. Wait for a response (or ~1 week) before moving to the next endorser.
- arXiv endorsement instructions for endorsers: https://arxiv.org/help/endorsement
