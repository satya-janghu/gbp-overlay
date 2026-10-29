# Frontend Architecture

## Tech Stack

| Layer | Technology |
|-------|------------|
| Framework | React 19 (TypeScript) |
| Build | Vite 6 |
| Styling | Tailwind CSS 4 + shadcn/ui components |
| State | React Query (@tanstack/react-query) |
| Forms | react-hook-form + zod validation |
| Routing | react-router-dom (BrowserRouter) |
| Toasts | Sonner |

## Page Flow (3-Step UI)

```
/ (SetupPage → SetupForm)
  → /project/:id/review (ReviewPage → ReviewUI)
    → /project/:id/progress (ProgressPage)
      → Download ZIP
/projects (ProjectsPage — dashboard)
```

All pages wrapped in `<Layout />` (shared nav + container).

## Component Tree

```
App.tsx
├── <Toaster /> (sonner)
├── <Layout />
│   ├── SetupPage
│   │   └── SetupForm (react-hook-form + zod)
│   │       ├── FontPicker
│   │       └── FileDropzone
│   ├── ReviewPage
│   │   └── ReviewUI
│   │       ├── KeywordGroup[]
│   │       │   └── ReviewCard[] (keyword select, location input, include checkbox, imgError state with "No preview" placeholder)
│   │       └── CollapsibleSection[] (auto-skipped, duplicates, skipped; overflow-x-auto for wide content)
│   ├── ProgressPage (polling with React Query)
│   └── ProjectsPage (dashboard)
```

## Data Fetching

All API calls go through `lib/api.ts` using typed `apiFetch<T>()` wrapper:
- `createProject(FormData)` — POST /api/projects
- `fetchProject(id)` — GET /api/projects/:id (returns ProjectDetail)
- `fetchPipelineStatus(id)` — GET /api/projects/:id/status (polled every 3s)
- `fetchGenerationStatus(id)` — GET /api/projects/:id/generation-status (polled every 3s)
- `fetchProjects()` — GET /api/projects (dashboard)
- `confirmReview(id, payload)` — POST /api/projects/:id/confirm
- `updateImageKeyword/Location/Status` — PATCH /api/images/:id/*

**Request timeout:** `apiFetch` uses a 30s `AbortController` timeout; callers can pass their own `signal` for cancellation (forwarded to the timeout controller via an abort listener). Review mutations pass `AbortController` signals through to API calls for proper cancellation propagation.

**Error handling:** `ApiError` class with status code, thrown on non-OK responses. Status-specific toast messages: 400 → "Invalid ...", 404 → "... not found", 500+ → "Server error ... Try again.", 0 (cancelled) → suppressed.

## Review Page State

- `includedIds: Set<number>` — tracks selected images (lazy initialized, persists across refetch)
- `overrides: Map<number, {keyword?, location?}>` — optimistic local edits
- `ReviewCard` syncs `localLocation` from props via `useEffect`; handles image load errors with `imgError` state showing "No preview" placeholder
- Mobile-responsive layout: `flex-col sm:flex-row` for card layout adapting to small screens
- Keyword/location mutations debounced 300ms with per-image `AbortController` cancellation: stale in-flight requests are cancelled before issuing new ones
- Mutation failures show error-specific toast based on `ApiError.status` and trigger refetch

## Static Assets

- **Built output**: `app/static/dist/` (Vite build, served by FastAPI)
- **Fonts**: 17 TTF files in `app/static/fonts/` (~4.3 MB, 9 families)
- **Styling**: Tailwind CSS with shadcn/ui component library (no custom CSS file)
