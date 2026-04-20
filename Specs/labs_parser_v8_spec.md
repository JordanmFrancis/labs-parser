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

```
/                  Dashboard — latest draw + flagged values + "Analyze" button
/upload            Drag-and-drop a CSV or PDF
/history           List of all draws, sortable by date
/draws/:id         Single draw detail, all values, edit/delete
/markers/:name     One marker over time, line chart, optimal range overlay
/analysis/:drawId  Streaming analysis view with the SSE token output
```

Six views. Small enough that `react-router-dom` covers navigation without complications.

## Key Components

```
src/
├── App.tsx
├── main.tsx
├── api/
│   ├── client.ts         # typed wrapper around fetch + base URL
│   └── types.ts          # generated from the OpenAPI spec via openapi-typescript
├── components/
│   ├── FileDropzone.tsx
│   ├── FlaggedLabsList.tsx
│   ├── MarkerChart.tsx
│   ├── StreamingAnalysis.tsx
│   └── ui/               # shadcn primitives
├── pages/
│   ├── Dashboard.tsx
│   ├── Upload.tsx
│   ├── History.tsx
│   ├── DrawDetail.tsx
│   ├── MarkerDetail.tsx
│   └── Analysis.tsx
└── lib/
    └── format.ts         # date formatting, value formatting
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

Recharts line chart, one line for the marker, two horizontal reference lines for the standard range, a third dashed line for the functional optimal range (fetched from the cached `lookup_optimal_range` endpoint). Hovering shows the value and date.

## Design System

Keep it brutalist-clean. Off-white background, mono headings, one accent color (use the COMT-friendly muted blue, not stimulating red). No shadows, no gradients. Big numbers when something matters, small text everywhere else.

Tailwind config:
- Font: Inter for body, JetBrains Mono for numeric values
- Spacing: generous, default Tailwind scale
- Color: neutral grays + a single `accent` (tailwind's `slate-700`)

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
| Upload while previous upload still processing | Disable upload button, show progress |
| Backend down | TanStack Query shows error toast, retry button |
| SSE stream stalls | Client-side timeout (90s), close connection, show "stream timed out" |
| Marker with one data point | Chart renders single dot, no trend line |
| Mobile view | Tailwind responsive classes, mobile-first layout |
| Dark mode | Tailwind dark variant, OS preference detection |

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

## Out of Scope for v8

- Mobile app (the responsive web UI is enough)
- Login/signup (single-user)
- Server-side rendering / Next.js
- Animations beyond hover states and the streaming cursor
- E2E tests (Playwright comes in v9 with the deploy pipeline)
- A11y audit (do it after v9 ships, before sharing publicly)
