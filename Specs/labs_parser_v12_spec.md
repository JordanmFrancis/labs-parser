---
date: 2026-04-13
type: deliverable
tags: [dev, claude, research]
project: learning-python
---

# Lab Parser v12 Spec — Agentic Protocol Generator

Related: [[labs_parser_roadmap]] · [[labs_parser_v11_spec]]

By v11 my parser is a real product: deployed, MCP-accessible, semantic search across my whole history. v12 is the version where it stops being a tool I query and starts being something that runs autonomous workflows on my behalf. Ask "review my last 6 months and propose interventions" and a planner agent breaks the goal into steps, calls multiple tools across multiple iterations, synthesizes findings, and delivers a structured protocol recommendation with citations.

This is also the version where the project becomes a useful argument for "agentic AI" — not a chatbot, an agent that does work.

## What I Want to Learn

- The plan-execute-reflect agent pattern
- Multi-step tool orchestration (chains of >10 tool calls per goal)
- Structured planning — using one Claude call to produce a JSON plan, then executing it
- Memory primitives — short-term (working memory in the loop), long-term (DB-backed, semantic recall via v11 embeddings)
- Sub-agents — delegating subtasks to scoped Claude calls with their own tool sets
- Output validation and self-correction loops
- Cost + iteration tracking — knowing when to stop
- The difference between an agent and an LLM with tools (the difference is the loop, the planner, and the memory)

## Conceptual Model

Three layers:

1. **Planner** — a Claude call that turns a user goal into a step-by-step JSON plan
2. **Executor** — the tool-use loop from v3/v6, but driven by the plan instead of free-form Claude reasoning
3. **Reflector** — a Claude call that reviews the executor's output, decides if the goal is met, and either replans or finalizes

```
Goal → Planner → Plan → Executor → Result → Reflector → (replan | done)
                              ↑                ↓
                              └────────────────┘
```

## The Planner

```python
class PlanStep(BaseModel):
    id: int
    description: str
    tool: str | None              # which tool to use, if any
    inputs: dict | None
    depends_on: list[int] = []    # other step ids
    rationale: str

class Plan(BaseModel):
    goal: str
    steps: list[PlanStep]
    success_criteria: str

async def make_plan(goal: str) -> Plan:
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        tools=[{
            "name": "submit_plan",
            "input_schema": Plan.model_json_schema()
        }],
        tool_choice={"type": "tool", "name": "submit_plan"},
        system=PLANNER_SYSTEM,
        messages=[{"role": "user", "content": f"Goal: {goal}\n\nAvailable tools:\n{tool_catalog()}"}]
    )
    return Plan(**response.content[0].input)
```

Output is structured JSON via the tool-as-output pattern from v6. The planner sees the catalog of all available tools (v3 tools + v11 search + new agentic tools) and writes a plan that uses them.

## The Executor

The v6 streaming tool-use loop, but with one difference: instead of letting Claude pick tools freely, the system prompt is constrained to the current plan step. Each iteration of the executor focuses on one PlanStep, calls the assigned tool (or freely if `tool: None`), records the result, and moves to the next step.

```python
async def execute_plan(plan: Plan) -> dict[int, str]:
    results = {}
    for step in plan.steps:
        if any(dep not in results for dep in step.depends_on):
            raise PlanExecutionError("Dependency not satisfied")
        context = {dep: results[dep] for dep in step.depends_on}
        result = await execute_step(step, context)
        results[step.id] = result
    return results
```

## The Reflector

After execution finishes, a separate Claude call reviews the plan's `success_criteria` against the results.

```python
class Reflection(BaseModel):
    success: bool
    reasoning: str
    missing: list[str] = []          # things not yet known
    next_actions: list[PlanStep] = []  # if not success, what additional steps to add

async def reflect(plan: Plan, results: dict) -> Reflection:
    # Claude call with structured output
    ...
```

If `success: True`, finalize. If `False`, append `next_actions` to the plan and re-execute. Hard cap at 3 reflection cycles.

## New Tools the Agent Needs

Beyond v3+v11 tools:

| Tool | Purpose |
|------|---------|
| `pubmed_search` | Search PubMed for studies on a marker/intervention. Returns titles + abstracts. |
| `lookup_drug_interactions` | Check a proposed supplement/drug against my current stack (data lives in vault) |
| `read_genetic_variant` | Look up one of my genetic SNPs (MTHFR, COMT, etc.) — feeds into protocol design |
| `recall_past_protocols` | Semantic search through past protocols I've tried (notes from v11) |
| `propose_intervention` | Structured-output tool: returns intervention dict with name, dose, timing, evidence, interaction risks |

`read_genetic_variant` and `lookup_drug_interactions` need the data sources to exist first. Stub them in v12 with hardcoded JSON; promote to real lookups in v13.

## Sub-Agents

Some steps are complex enough to deserve their own scoped agent. Example: "research evidence for berberine in someone with my lipid profile" → spawn a sub-agent with `pubmed_search`, `lookup_drug_interactions`, and `recall_past_protocols` only. The sub-agent runs its own tool loop and returns a structured summary.

```python
async def spawn_subagent(task: str, allowed_tools: list[str]) -> str:
    return await run_constrained_loop(
        system=SUBAGENT_SYSTEM,
        task=task,
        tools=[t for t in ALL_TOOLS if t["name"] in allowed_tools]
    )
```

Why sub-agents matter: keeps the parent agent's context window clean, lets you parallelize independent subtasks, and gives each sub-task its own "specialist" persona.

## Memory

Two layers:

| Layer | Storage | Purpose |
|-------|---------|---------|
| Working memory | the agent's current `messages` list | Within one run, full conversation context |
| Long-term memory | v11 embeddings + a new `agent_runs` table | Across runs — "what protocols has the agent recommended in the past?" |

After every run, the agent writes a structured summary to `agent_runs` (goal, plan, key findings, recommendation, outcome). Future runs use v11 semantic search to recall prior runs that are relevant.

## Output: Structured Protocol Document

Final output isn't a wall of text. It's a Pydantic model:

```python
class Intervention(BaseModel):
    name: str
    type: Literal["supplement", "drug", "lifestyle", "test"]
    dose: str | None
    timing: str | None
    expected_effect: str
    targets_marker: list[str]
    evidence: list[str]                # PubMed PMIDs
    interaction_risks: list[str]
    cost_per_month_usd: float | None

class Protocol(BaseModel):
    goal: str
    summary: str
    interventions: list[Intervention]
    monitoring: list[str]              # what to retest and when
    confidence: Literal["low", "medium", "high"]
    sources: list[str]
    open_questions: list[str]
```

Frontend renders this as a structured card. MCP returns it as JSON. Both consume the same model.

## Cost + Safety Caps

Agents can run away. Hardcoded limits:

- `MAX_PLAN_STEPS = 20`
- `MAX_TOOL_CALLS_PER_RUN = 50`
- `MAX_REFLECTION_CYCLES = 3`
- `MAX_RUNTIME_SECONDS = 300`
- `MAX_COST_USD = 2.00` (track spend by counting tokens × model price)

If any limit hits, abort with a partial result + the reason.

## Edge Cases

| Case | Behavior |
|------|----------|
| Planner returns invalid JSON | Pydantic validation fails; retry once with the validation error in the prompt |
| Step depends on a tool that fails | Reflector adds a fallback step in the next cycle |
| Subagent doesn't return | Timeout per sub-agent (60s), parent agent treats as `{"error": "subagent timeout"}` |
| Protocol contradicts my known constraints | Validate output against my stack (no MAOIs, etc.) — flag in `interaction_risks` |
| Agent cycles indefinitely | Hard caps above |
| User cancels mid-run | SSE stream supports cancellation; agent checks cancellation flag between steps |

## Files to Add

- `agent/planner.py`
- `agent/executor.py`
- `agent/reflector.py`
- `agent/subagent.py`
- `agent/memory.py`
- `models.py` — add `PlanStep`, `Plan`, `Reflection`, `Intervention`, `Protocol`
- new MCP tool: `run_agent(goal: str)` — kicks off an agentic run, returns a job id, streams progress

## What's New vs v11

| Concept | v11 | v12 |
|---------|----|-----|
| Initiative | I ask, it answers | it plans, executes, and synthesizes |
| Tool calls per request | ~3-8 | up to 50 |
| Output | text or single JSON | structured Protocol document with evidence |
| Memory | DB rows + embeddings | + agent run history + reflection |
| Concurrency | sequential | sub-agents run in parallel where independent |
| Failure mode | error | reflect, replan, retry |

## Out of Scope for v12

- Multi-agent debate (two agents disagreeing and resolving) — interesting but not productive at this scale
- Long-running agents (days/weeks) — keep runs <5 minutes
- Self-modifying agents (writing their own tools) — far too sharp
- Fine-tuned planning model — Sonnet 4.6 is enough
- Voice interface (talk to the agent) — sits behind hands-free MCP if I want it later

## What "Done" Looks Like

I open the web app, type "review my last 2 quarters and propose Q3 interventions," watch a planner produce a 12-step plan, watch the executor stream tool calls (lookups, semantic searches, sub-agent dispatches), watch the reflector approve, and get back a structured Protocol document with 5-8 interventions, each with evidence + interaction risk + monitoring plan. End-to-end in under 4 minutes for under $1.

That's the entire AI engineering stack — Python, async, web, frontend, databases, deployment, MCP, RAG, agents — applied to my actual life. Done.
