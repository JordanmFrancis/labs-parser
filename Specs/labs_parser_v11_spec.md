---
date: 2026-04-13
type: deliverable
tags: [dev, claude, research]
project: learning-python
---

# Lab Parser v11 Spec — Embeddings + RAG

Related: [[labs_parser_roadmap]] · [[labs_parser_v10_spec]]

By v10 my parser ingests files, stores them, exposes them via REST + MCP, and runs analysis on demand. But every query is structured — "give me my LDL history." I can't ask "show me everything related to inflammation" or "find labs that look like the time I felt awful in 2024." v11 adds semantic search by embedding every lab marker, every analysis summary, and every note into a vector database.

This is also where the marker-name normalization problem from v5 actually gets solved. "LDL" and "LDL Cholesterol" and "Low-Density Lipoprotein" embed to nearly the same vector — semantic match instead of string match.

## What I Want to Learn

- What an embedding is (a vector that represents meaning) and why they enable similarity search
- Voyage AI embeddings (Anthropic's recommended embedding provider) — different model sizes, when to use which
- pgvector — the Postgres extension for vector storage and similarity queries
- Cosine similarity vs dot product vs L2 distance, when to use each
- Chunking strategies — how to break documents into embedding-sized pieces
- The full RAG pattern: query → embed → retrieve top-k → stuff into context → ask Claude
- Hybrid search — combining semantic (vector) and keyword (BM25/Postgres FTS) for better results

## What Gets Embedded

Three kinds of records, all in the same `embeddings` table:

| Record type | Source | Why embed it |
|-------------|--------|--------------|
| Marker descriptors | Each unique marker name + units | Solves "LDL" vs "LDL Cholesterol" matching |
| Analysis summaries | Each v6 streaming summary, full text | Find past analyses that look like a current one |
| User notes | Free-text notes I attach to draws | "Find labs from when I was on TRT" without remembering dates |

Lab values themselves don't get embedded — they're numeric, not semantic. The metadata around them does.

## Schema Addition

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE embeddings (
    id BIGSERIAL PRIMARY KEY,
    record_type TEXT NOT NULL,        -- 'marker' | 'summary' | 'note'
    record_id BIGINT NOT NULL,        -- FK to draws/lab_values/notes (no real FK, polymorphic)
    text TEXT NOT NULL,               -- the source text that was embedded
    embedding vector(1024),           -- voyage-3 produces 1024-dim vectors
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_embeddings_vector ON embeddings
    USING hnsw (embedding vector_cosine_ops);

CREATE INDEX idx_embeddings_type ON embeddings(record_type);
```

HNSW index makes nearest-neighbor queries fast even at 100k+ rows.

## Embedding Pipeline

```python
import voyageai

vo = voyageai.Client()  # reads VOYAGE_API_KEY

async def embed_text(text: str) -> list[float]:
    result = vo.embed([text], model="voyage-3", input_type="document")
    return result.embeddings[0]

async def embed_query(text: str) -> list[float]:
    result = vo.embed([text], model="voyage-3", input_type="query")
    return result.embeddings[0]
```

Note `input_type` matters — "document" embeddings and "query" embeddings are tuned differently for asymmetric retrieval. Same model, different prompts under the hood.

## Triggering Embeddings

- On `import_draw`: embed each unique marker name (skip if already embedded)
- After `analyze_draw` finishes: embed the summary
- On note creation: embed the note text
- One-shot backfill script for the first run after deploying v11

Embed in a background task. The user-facing import should not block on embedding.

## Semantic Search Endpoint

```python
@app.get("/search")
async def semantic_search(q: str, k: int = 10, types: list[str] = None):
    query_vec = await embed_query(q)
    sql = """
        SELECT id, record_type, record_id, text,
               1 - (embedding <=> :vec) AS similarity
        FROM embeddings
        WHERE (:types IS NULL OR record_type = ANY(:types))
        ORDER BY embedding <=> :vec
        LIMIT :k
    """
    return await db.fetch_all(sql, {"vec": query_vec, "types": types, "k": k})
```

`<=>` is pgvector's cosine distance operator. `1 - distance` converts to similarity score. Returns top-k matches across all embedded content.

## RAG-Powered Analysis Tool

Add a 4th MCP tool / API endpoint: `analyze_with_context`. Pulls in semantically related past summaries before running analysis on a current draw.

```python
async def analyze_with_context(draw_id: int) -> str:
    current_draw = await db.get_draw(draw_id)
    flagged_text = format_flagged(current_draw)

    # Find past analyses similar to this one
    related = await semantic_search(
        q=flagged_text,
        k=5,
        types=["summary"]
    )

    context = "\n\n".join(f"Past analysis ({r.created_at}): {r.text}" for r in related)

    return await stream_summary_with_context(flagged_text, context)
```

Now Claude isn't analyzing this draw in isolation — it sees the 5 most semantically similar past analyses and can say "this matches the pattern from your March 2025 draws when X intervention helped."

## Marker Canonicalization (Solving the v5 Issue)

When a new draw imports a marker name, embed it and run a similarity search against existing marker embeddings. If similarity > 0.95, treat it as the same marker. If 0.85-0.95, ask the user to confirm. If <0.85, treat as a new marker.

```python
async def canonicalize_marker(name: str) -> str:
    vec = await embed_query(name)
    matches = await db.fetch_all("""
        SELECT text, 1 - (embedding <=> :vec) AS sim
        FROM embeddings WHERE record_type = 'marker'
        ORDER BY embedding <=> :vec LIMIT 1
    """, {"vec": vec})
    if matches and matches[0].sim > 0.95:
        return matches[0].text   # canonical name
    return name                  # new marker, store as-is, embed for next time
```

## Hybrid Search (Optional Stretch)

Pure vector search misses exact matches sometimes ("hsCRP" the abbreviation might not vector-match "high-sensitivity C-reactive protein" the spelled-out form perfectly). Combine:

1. Postgres full-text search (keyword) — top-20 results
2. Vector cosine similarity — top-20 results
3. Reciprocal Rank Fusion to merge the two lists into final top-10

Worth doing but not blocking the v11 ship.

## Cost Considerations

Voyage embeddings are cheap. ~$0.06 per 1M tokens. My total lab corpus is maybe 50k tokens. Embedding everything costs cents. Not a concern.

Storage: 1024-dim float32 vector = 4KB per row. 10k rows = 40MB. Postgres free tier is fine forever.

## Edge Cases

| Case | Behavior |
|------|----------|
| Voyage API down | Background task retries with exponential backoff, log failure, continue without embedding |
| Embedding model upgrade (voyage-3 → voyage-4) | Migration: re-embed everything in a background job, swap the column. Document the runbook. |
| Search query returns nothing relevant | Return empty list, frontend shows "no related results" |
| User uploads PII in a note | Same as v9 — encrypt at rest, never log content, don't embed and ship to a third-party model if user opts out |
| Vector index gets corrupted | `REINDEX` the HNSW index, document recovery |

## Files to Add

- `embeddings.py` — Voyage client wrapper, embed functions
- `migrations/004_add_embeddings.py` — Alembic migration adding pgvector + table
- `core/search.py` — semantic + hybrid search
- `core/canonicalize.py` — marker canonicalization
- `requirements`: `voyageai`, `pgvector` (Python adapter)

## What's New vs v10

| Concept | v10 | v11 |
|---------|----|-----|
| Search | exact match (SQL `WHERE marker = ?`) | semantic similarity across all content |
| Storage | rows + columns | + vector embeddings with HNSW index |
| Marker matching | string equality | vector similarity (handles synonyms/abbreviations) |
| Analysis context | only the current draw | + top-k semantically similar past analyses |
| Query interface | structured | natural language ("inflammation", "fatigue era") |

## Out of Scope for v11

- Re-ranking models (Voyage rerank-2, Cohere rerank) — adds quality but more complexity
- Multi-modal embeddings (embedding the actual lab PDF images) — voyage-multimodal-3 supports it, save for v13
- LangChain or LlamaIndex — overkill; pgvector + raw SQL is simpler and I learn more
- Fine-tuned embeddings on my own data — not enough data
