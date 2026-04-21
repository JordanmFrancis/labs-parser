---
date: 2026-04-13
type: deliverable
tags: [dev, claude, design]
project: learning-python
---

# Lab Parser v8 Spec — React Frontend

Related: [[labs_parser_roadmap]] · [[labs_parser_v7_spec]]

By v7 I have an HTTP API. v8 puts a UI on it. Drag-and-drop a lab PDF, see flagged values, watch Claude's analysis stream in real time, browse my full history with charts. This is the version where the project becomes something I'd actually show people.

## What I Want to Learn

- HTML/CSS/JS basics (the right amount — not a year-long bootcamp)
- React with Vite — components, props, state, hooks (`useState`, `useEffect`)
- Tailwind CSS — utility-first styling, why it's faster than CSS-in-JS for prototypes
- `fetch` API — making HTTP calls from the browser
- Multipart upload from the browser (drag-and-drop file → POST)
- Server-Sent Events client (`EventSource`) — consuming the v7 streaming endpoint
- Recharts or similar for time-series charts
- TypeScript basics — type-safe API client

## Stack Choice

| Tool | Why |
|------|-----|
| Vite | Fast dev server, instant reloads, simpler than Next.js for a SPA |
| React 18 + TypeScript | Industry standard, huge ecosystem, types catch bugs early |
| Tailwind v4 | Utility classes, no CSS file gymnastics |
| Recharts | Simple React charts, good defaults |
| TanStack Query | Data fetching + caching, removes most `useEffect` data-fetch boilerplate |
| shadcn/ui | Copy-paste components, not a dependency. Use sparingly. |

No Next.js. No state management library (Zustand/Redux). The app isn't complex enough to justify them, and learning React first without those is the right call.

## Pages / Views

Five tab-based views, matching the prototype. No `react-router-dom` — the prototype uses simple state-based tab switching (`useState` for `route`), which is simpler and avoids URL management complexity for a SPA with no deep-linking needs.

```
Dashboard     Prompt-first hero + KPI grid + flagged list + sparkline grid + past agent runs
Upload        Drag-and-drop → parse → side-by-side source vs extracted → ambiguity resolution → save
Marker        Single marker detail: big value, time-series chart, range cards, compare, per-marker chat
Agent Run     Live timeline (plan/execute/reflect steps) → completed summary card with stats
Protocol      Intervention cards grouped by type (nutrition/training/supplement/monitoring) + formal report
```

The Dashboard and Marker views are v8. The Agent Run and Protocol views are UI shells in v8 but don't get real data until v12 (the agentic loop). Build the components and wire them to mock data so the full app is navigable.

## Key Components

```
src/
├── App.tsx                   # Tab-based navigation, route state
├── main.tsx
├── api/
│   ├── client.ts             # typed wrapper around fetch + base URL
│   └── types.ts              # generated from the OpenAPI spec via openapi-typescript
├── components/
│   ├── atoms/
│   │   ├── Chip.tsx          # versatile chip: default, accent, ok, ghost, on variants
│   │   ├── Card.tsx          # default, soft, accent, paper tones
│   │   └── Sparkline.tsx     # mini SVG line chart for marker grids
│   ├── dashboard/
│   │   ├── PromptBox.tsx     # prompt-first hero with starter cards + shortcut chips
│   │   ├── KpiGrid.tsx       # 4 key markers with sparklines + trend deltas
│   │   ├── FlaggedList.tsx   # full table sorted by severity, with optimal targets
│   │   ├── SparkGrid.tsx     # all markers in a compact grid
│   │   └── PastRuns.tsx      # last 3 agent runs
│   ├── upload/
│   │   ├── FileDropzone.tsx  # drag-and-drop + click-to-browse
│   │   ├── AmbiguityBanner.tsx  # "N rows need your eyes" with resolution UI
│   │   └── SourceVsExtracted.tsx  # side-by-side PDF pane + extracted rows table
│   ├── marker/
│   │   ├── MarkerChart.tsx   # SVG time-series with range bands + point labels
│   │   ├── RangeCards.tsx    # lab ref vs optimal vs current
│   │   ├── ComparePreview.tsx  # dual-line comparison chart
│   │   └── MarkerChat.tsx    # scoped per-marker chat with suggested questions
│   ├── agent/
│   │   ├── Timeline.tsx      # step-by-step with dot states (done/active/pending)
│   │   └── DoneSummary.tsx   # completed run stats + findings + expandable details
│   └── protocol/
│       ├── InterventionCard.tsx  # grouped by type, with dose/rationale/PMID/warnings
│       └── FormalReport.tsx     # expandable printable report
├── screens/
│   ├── Dashboard.tsx
│   ├── Upload.tsx
│   ├── Marker.tsx
│   ├── AgentRun.tsx
│   └── Protocol.tsx
└── lib/
    ├── format.ts             # date formatting, value formatting
    └── flags.ts              # flagStatus, severity, trendPct (match prototype logic)
```

## The Streaming Component (Most Interesting Part)

The v7 SSE endpoint streams analysis tokens. The frontend renders them as they arrive:

```tsx
function StreamingAnalysis({ drawId }: { drawId: number }) {
  const [text, setText] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    const es = new EventSource(`/api/analyze/${drawId}`);

    es.onmessage = (event) => {
      if (event.data === "[DONE]") {
        setDone(true);
        es.close();
        return;
      }
      const { token } = JSON.parse(event.data);
      setText((prev) => prev + token);
    };

    es.onerror = () => {
      es.close();
      setDone(true);
    };

    return () => es.close();
  }, [drawId]);

  return (
    <div className="prose">
      <p>{text}{!done && <span className="animate-pulse">▊</span>}</p>
    </div>
  );
}
```

The blinking cursor is the touch that makes it feel alive.

## Drag-and-Drop Upload

```tsx
function FileDropzone({ onUpload }: { onUpload: (file: File) => void }) {
  const [dragOver, setDragOver] = useState(false);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) onUpload(file);
  };

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      className={`border-2 border-dashed rounded-lg p-12 text-center ${
        dragOver ? "border-blue-500 bg-blue-50" : "border-gray-300"
      }`}
    >
      Drop a CSV or PDF here
    </div>
  );
}
```

## Marker Chart

Hand-rolled SVG chart (matching the prototype — not Recharts). One line for the marker, a filled band for the reference range (accent-soft fill), dashed horizontal lines at range boundaries, point labels showing values, date labels on x-axis. The prototype's `MarkerChart` component is ~30 lines of SVG math — clean and dependency-free.

## Design System

The prototype already defines the full design system. Match it exactly — don't redesign.

### Typography (three tiers)
- **Display**: Fraunces (serif, variable weight). Used for h1/h2/h3, large marker values, brand. Editorial italic variant for hero headlines.
- **Body**: Inter. Used for prose, labels, buttons, form inputs.
- **Mono**: JetBrains Mono. Used for numeric values, dates, units, tags, code-like elements.

### Color system (CSS custom properties)
- `--accent`: warm amber `#d97706` (default). Six additional swatches: coral, teal, indigo, forest, plum, ink.
- `--ink` / `--ink2` / `--ink3`: three tiers of text color (darkest to lightest).
- `--paper` / `--paper2`: background tiers. `--card`: white card surface.
- `--line`: border/divider color. `--ok`: green for in-range.
- Full dark mode theme (`[data-theme="night"]`) that inverts all values.

### Component patterns
- **Cards**: four tones — default (white), soft (paper2), accent (accent-soft bg), paper.
- **Chips**: seven variants — default, ghost, accent, ok, on, on+accent, btn. Used extensively for tags, actions, filters.
- **Buttons**: primary (ink bg, accent on hover) and ghost (transparent, border). Both with active state.
- **Tables**: full-width with hover rows, flagged row highlighting, mono numeric cells.
- **Sparklines**: hand-rolled SVG, not Recharts. Simple path + endpoint dot, accent color when flagged.

### Layout
- Max-width 1180px container, generous padding (48px top, 40px sides).
- Card shadows: subtle two-layer (`shadow-sm`, `shadow-md`).
- Warm off-white background (`#faf7f0`), not cool gray.
- Optional dot-grid or line-grid background patterns.

### Theming
The prototype has a tweaks panel with knobs for: theme (day/night), accent color, typography (serif/sans/mono), headline style (editorial/default/compact), background pattern, density (cozy/comfy/spacious), corner radius, chart detail, KPI density. These are nice-to-haves — implement them if time allows, but the default theme should match the prototype's defaults (editorial serif, amber accent, spacious density).

## TypeScript API Client

Generate types from the OpenAPI spec FastAPI exposes at `/openapi.json`:

```bash
npx openapi-typescript http://localhost:8000/openapi.json -o src/api/types.ts
```

Now my frontend types match my backend models exactly. Change the backend, regenerate, frontend errors compile-time.

## File Structure on Disk

```
labs-parser/
├── backend/         # v7 FastAPI app
└── frontend/        # v8 Vite app
    ├── src/
    ├── package.json
    └── vite.config.ts
```

Two separate `package.json`/`pyproject.toml` projects. Vite dev server proxies `/api/*` to the FastAPI on port 8000.

## Edge Cases

| Case | Behavior |
|------|----------|
| Upload while previous upload still processing | Disable upload button, show "extracting…" state |
| Backend down | TanStack Query shows error toast, retry button |
| SSE stream stalls | Client-side timeout (90s), close connection, show "stream timed out" |
| Marker with one data point | Chart renders single dot, no trend line. Sparkline shows flat line. |
| Mobile view | Tailwind responsive classes, mobile-first layout |
| Dark mode | CSS custom properties swap via `[data-theme="night"]` (matching prototype) |
| Parse returns rows needing review | Upload screen shows ambiguity banner with resolution chips |
| Unknown marker in parse results | Upload shows "New marker — map or create?" with chip options |
| Agent run screen with no runs yet | Show empty state with prompt to run first analysis |
| Protocol screen with no protocols | Show empty state directing to agent run |

## Files to Add

- `frontend/` directory, fresh Vite scaffold
- `vite.config.ts` with the `/api` proxy
- All the components/pages above
- Tailwind v4 config + globals.css

## What's New vs v7

| Concept | v7 | v8 |
|---------|----|----|
| Interface | API only | full web UI |
| Languages | Python | Python + TypeScript |
| Tooling | uv/pyproject | uv + npm/Vite |
| Output rendering | text in terminal | streaming UI with charts |
| User | me + curl | anyone with a browser |

## Prototype Files (Already Built)

The design prototype is complete and defines the exact component structure, data shapes, and interactions. Use these as the source of truth:

- `Labs Parser Prototype.html` — full CSS design system + nav + tweaks panel + app shell
- `data.jsx` — mock data arrays (MARKERS, HISTORY, UPLOAD_ROWS, AGENT_STEPS, PROTOCOL_INTERVENTIONS) + helper functions (latestValue, flagStatus, severity, trendPct)
- `screens.jsx` — all 5 screen components (Dashboard, Upload, Marker, AgentRun, Protocol) + atoms (Chip, Card, Sparkline) + charts (MarkerChart, ComparePreview)
- `design-canvas.jsx` — Figma-like pan/zoom wrapper (presentation layer, not part of the real app)

The v8 build is essentially: take the prototype, split it into a real Vite + TypeScript project, replace mock data with API calls to v7 endpoints, and add real interactivity where the prototype has simulated state.

## Out of Scope for v8

- Mobile app (the responsive web UI is enough)
- Login/signup (single-user)
- Server-side rendering / Next.js
- The tweaks panel (nice-to-have, add later if desired)
- Real Agent Run / Protocol data (v12 — use mock data from prototype for now)
- E2E tests (Playwright comes in v9 with the deploy pipeline)
- A11y audit (do it after v9 ships, before sharing publicly)
