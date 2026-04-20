---
date: 2026-04-13
type: deliverable
tags: [dev, claude, research]
project: learning-python
---

# Lab Parser Roadmap — v4 through v12

Related: [[labs_parser_v2_spec]] · [[labs_parser_v3_spec]] · [[projects]]

This is my full curriculum for turning Lab Parser from a working v3 script into a real, deployed, multi-surface app while learning every major Python + AI engineering concept I haven't touched yet. Each version adds one feature AND teaches one concept I don't already know. No filler versions.

## Where I Am After v3

I've shipped: CSV parsing, out-of-range flagging, trend detection, single-shot API summarization (v2), tool use loop with 3 tools including Claude-as-a-tool (v3). I know: variables, lists, dicts, list comps, functions, file I/O (CSV), env vars, JSON, the Anthropic SDK, multi-turn messages, tool use, defensive parsing, git, pip.

## What I Still Don't Know

- Binary file parsing (PDF) and the vision API (multimodal)
- Databases — schemas, CRUD, SQL
- Pydantic models / structured outputs
- Streaming API responses
- Web frameworks and async/await
- Frontend (React, Tailwind, fetch)
- Deployment, Docker, secrets management, logging
- MCP protocol — building servers, not just using them
- Embeddings, vector DBs, RAG
- Agentic patterns — planning, multi-step autonomous workflows

## The Plan

| Version | Feature | New Concepts | Why It Matters |
|---------|---------|--------------|----------------|
| v4 | Parse PDFs, screenshots, and phone photos | Binary I/O, `pdfplumber`, regex, vision API (single + multi-image), HEIC handling, EXIF rotation, fallback chain | I get labs every way: PDFs, portal screenshots, photos of paper. CSV is a toy input. |
| v5 | Multi-upload + history database | SQLite, schemas, SQL, dataclasses/Pydantic models | CSV-as-database breaks the moment I have 2 lab dates. |
| v6 | Streaming output + structured tool outputs | Streaming responses, Pydantic models, `tool_choice`, replacing `strip_code_fences` hack | Modern API patterns. UX win + type safety. |
| v7 | FastAPI backend | Web frameworks, async/await, REST endpoints, file uploads, OpenAPI docs | Turn the script into a service anyone can call. |
| v8 | React frontend | HTML/CSS/JS, React, Tailwind, fetch, forms, multipart upload UI | Make it usable by humans, not just terminals. |
| v9 | Deploy to Render | Docker, env management, secrets, logging, CI basics | Get a live URL. The thing isn't real until it's online. |
| v10 | MCP server version | MCP protocol, async server, tool registration, Claude Desktop integration | Claude can call my tool directly. Highest portfolio leverage. |
| v11 | Semantic search + RAG | Embeddings, pgvector (Supabase), chunking, retrieval pipelines | "Show me labs related to inflammation" — semantic queries across history. |
| v12 | Agentic protocol generator | Agent loops, planning, multi-tool orchestration, memory | "Compare my last 3 lipid panels and propose interventions" — Claude plans + executes. |

## Concept-to-Version Map

If I'm trying to learn a specific concept, here's where it shows up first:

- **Binary file I/O** → v4
- **Vision API / multimodal (PDFs, screenshots, photos)** → v4
- **HEIC + EXIF image handling** → v4
- **Multi-image API messages** → v4
- **Regex** → v4
- **SQLite / SQL** → v5
- **Schema design** → v5
- **Dataclasses / Pydantic** → v5 (intro), v6 (structured outputs)
- **Streaming** → v6
- **Async/await** → v7
- **FastAPI / web framework** → v7
- **REST API design** → v7
- **HTML/CSS/JS basics** → v8
- **React + Tailwind** → v8
- **fetch / multipart upload** → v8
- **Docker** → v9
- **Cloud deployment** → v9
- **Logging (real, not print)** → v9
- **Secrets management** → v9
- **MCP protocol** → v10
- **Embeddings** → v11
- **Vector databases** → v11
- **RAG architecture** → v11
- **Agent loops** → v12
- **Planning + memory** → v12

## How I'll Work Through This

- One version at a time. Don't skip ahead.
- Each version starts with re-reading its spec, then I write the code (with Claude pairing).
- Every version ends with: tests pass on real lab data, README updated, commit + push to GitHub, tagged release (e.g., `v4.0`).
- Decision points where the spec gives me options (e.g., `pypdf` vs vision API in v4) get answered in the moment based on what I want to learn.
- If I get stuck for >30 min, I ask Claude to debug — but I write the code.

## What This Becomes

By v12 I have: a deployed web app, an MCP server Claude can call, semantic search across all my historical labs, and an agentic mode that can plan multi-step analysis. That's not a toy. That's a real product. And by then I know Python, async, web, frontend, databases, deployment, MCP, RAG, and agents — which is the entire AI engineering stack.

## Out of Scope for the Whole Roadmap

- Mobile app (web is enough)
- User accounts / multi-tenancy (single-user is fine for portfolio)
- HIPAA compliance (it's my data on my deploy)
- Payment / monetization (not the point)
- Bring-your-own-key UI (until I want strangers using it)

These can be v13+ if I ever care.
