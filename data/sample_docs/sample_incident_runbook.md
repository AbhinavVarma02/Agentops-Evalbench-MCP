# Northwind Labs — AI Incident Runbook

_Fictional document used as sample RAG content for AgentOps EvalBench MCP._

## When to Declare an Incident

Declare an AI incident when any of the following happens in production:

- Groundedness drops below the 0.80 threshold on the live evaluation set.
- Hallucination risk rises above 0.20 for two consecutive runs.
- Answer latency exceeds 5 seconds for more than 10% of requests.
- A data-leakage or prompt-injection report is confirmed.

## Response Steps

1. **Acknowledge** the alert within 15 minutes and page the on-call owner.
2. **Contain** the issue by rolling back to the last known-good prompt/model
   version. Every deployment must have a documented rollback target.
3. **Diagnose** using stored evaluation runs and trace logs. Compare the failing
   run against the last passing baseline to locate the regression.
4. **Fix and verify** by re-running the evaluation gate until all thresholds pass.
5. **Write a postmortem** within 3 business days describing the root cause and the
   preventive action.

## Rollback Rule

The default rollback target is the most recent evaluation run that passed every
quality threshold. Because each run stores its model name, prompt version, and
metrics, on-call engineers can identify and restore a known-good configuration
quickly.

## Communication

During an active incident, post status updates every 30 minutes in the
`#ai-incidents` channel until the issue is resolved and the evaluation gate is
green again.
