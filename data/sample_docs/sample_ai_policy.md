# Northwind Labs — AI Deployment Policy (v3)

_Fictional document used as sample RAG content for AgentOps EvalBench MCP._

## 1. Purpose

This policy defines how teams at Northwind Labs build, review, and deploy
production AI systems. It applies to every large language model (LLM) feature
that reaches external users, including retrieval-augmented generation (RAG)
assistants and autonomous agents.

## 2. Approval Gates

Every AI feature must pass three gates before production release:

1. **Safety Review** — a documented review of prompt-injection, data-leakage,
   and harmful-output risks. Sign-off is required from the Responsible AI lead.
2. **Evaluation Gate** — an automated evaluation run must meet the minimum
   quality thresholds defined in Section 4. Runs are stored and auditable.
3. **On-call Readiness** — a named on-call owner and a rollback plan must exist
   before launch.

A feature may not ship if any gate is skipped. Emergency exceptions require
written approval from the VP of Engineering and must be reviewed within 5 days.

## 3. Data Handling Rules

- Customer data used for retrieval must stay within the approved vector store.
- Personally identifiable information (PII) must be redacted before indexing.
- Prompts and completions are retained for 30 days for debugging, then deleted.
- Secrets (API keys, database URLs) must never be embedded in prompts or logs.

## 4. Minimum Quality Thresholds

The Evaluation Gate uses these thresholds. A run **passes** only if every
threshold is met:

- Groundedness must be at least 0.80.
- Hallucination risk must be at most 0.20.
- Retrieval quality must be at least 0.75.
- Answer relevance must be at least 0.70.
- End-to-end latency must be at most 5 seconds per answer.

If a run falls below any threshold, the feature is blocked until the owner fixes
the regression and re-runs the evaluation.

## 5. Model and Prompt Versioning

Every deployment records the model name and a prompt version string (for example
`v1`, `v2`). Comparisons between a baseline run and a candidate run are required
whenever the model or prompt changes, so reviewers can see whether quality
improved or regressed before approving the change.

## 6. Cost Controls

Teams must track estimated cost per evaluation run. The default production model
is `gpt-4o-mini`. Switching to a larger model requires a cost/benefit note in the
pull request, because larger models increase both latency and cost per answer.
