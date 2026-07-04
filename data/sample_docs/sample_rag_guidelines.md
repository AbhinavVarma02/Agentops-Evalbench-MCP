# Northwind Labs — RAG System Guidelines

_Fictional document used as sample RAG content for AgentOps EvalBench MCP._

## Retrieval Design

Retrieval-augmented generation systems must ground their answers in retrieved
context. The retriever returns the top chunks most relevant to the user's
question, and the generator must only use information found in those chunks.

- Default retrieval returns the top 4 chunks per question.
- Chunk size defaults to roughly 800 characters with a 100-character overlap so
  that context is not cut mid-sentence.
- If no relevant chunk is found, the assistant must say it does not know rather
  than inventing an answer.

## Grounding and Hallucination

An answer is **grounded** when its claims are supported by the retrieved context.
A **hallucination** is any claim that is not supported by the context. Northwind
treats hallucinations as the highest-severity quality defect because they erode
user trust. Reviewers should always inspect failed cases to see whether the model
fabricated facts or simply retrieved the wrong context.

## Evaluation Metrics

Each answer is scored on several metrics:

- **Groundedness** measures how well the answer is supported by the context.
- **Hallucination risk** measures how much of the answer is unsupported.
- **Answer relevance** measures how directly the answer addresses the question.
- **Retrieval quality** measures whether the retrieved chunks contain the
  information needed to answer.

These scores are combined with latency, token usage, and estimated cost to decide
whether a run is ready for deployment.

## Prompt Guidance

Prompts should instruct the model to answer using only the provided context, to
cite the relevant portion when possible, and to refuse when the context is
insufficient. Prompt changes must be versioned and compared against the previous
version before rollout.
