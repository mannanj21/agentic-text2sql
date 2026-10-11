# ADR: Exact Nearest Neighbor Search (No ANN Index)

## Status
Accepted

## Context
We are implementing vector search to retrieve relevant schema tables and columns based on a user's question. `pgvector` supports exact nearest neighbor search (exact scan) as well as Approximate Nearest Neighbor (ANN) indexes like IVFFlat and HNSW. 

We need to decide which indexing strategy to use for `schema_tables.embedding`, `schema_columns.embedding`, and `glossary_terms.embedding`.

## Decision
We will use **exact nearest neighbor search (no index)** for vector retrieval.

## Rationale
1. **Scale of Data:** Schema metadata is very small. A typical enterprise database might have hundreds of tables and a few thousand columns. `pgvector` can perform exact distance calculations on thousands of vectors in just a few milliseconds.
2. **Recall Requirements:** In Text-to-SQL tasks, missing the right table/column can cause the LLM to hallucinate or fail entirely. ANN indexes sacrifice 100% recall for speed, which is unacceptable given our scale. Exact search guarantees 100% recall for the nearest neighbors.
3. **Simplicity:** No need to configure `m` and `ef_construction` for HNSW, or maintain `lists` for IVFFlat. 

## Consequences
- Retrieval is deterministic and accurate.
- Query latency scales linearly with the number of columns, which is perfectly acceptable up to ~100k vectors.
- No index maintenance required.
