# SequelSpeak Frontend

React + TypeScript + Vite app that provides the connection management UI and the Clerk-authenticated entry point for SequelSpeak.

For the project-wide overview see the [root README](../README.md). For backend details see [backend/README.md](../backend/README.md).

## Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| UI library | React | 19.2.0 |
| Language | TypeScript | ~5.9.3 |
| Build tool / dev server | Vite | ^7.2.4 |
| Styling | Tailwind CSS via `@tailwindcss/vite` | ^4.1.18 |
| Authentication | `@clerk/clerk-react` | ^5.60.0 |
| Icons | `lucide-react` | ^0.562.0 |
| Class merging | `clsx` + `tailwind-merge` | latest |
| Testing | Vitest + Testing Library + jsdom | ^4.0.18 / ^16.3.2 / ^28.1.0 |

Full dependency list: [package.json](package.json).

## Getting Started

```bash
cd frontend
npm install
cp .env.example .env
# Fill in VITE_API_URL and VITE_CLERK_PUBLISHABLE_KEY
npm run dev
```

The dev server runs with `--host` (per [package.json](package.json)) so it is reachable from other devices on the LAN.

## Scripts

Only the scripts defined in [package.json](package.json):

| Script | Command | Purpose |
|--------|---------|---------|
| `npm run dev` | `vite --host` | Start the dev server |
| `npm run build` | `tsc -b && vite build` | Type-check and build for production |
| `npm run lint` | `eslint .` | Run ESLint over the project |
| `npm run preview` | `vite preview` | Preview the production bundle |

There is no dedicated `test` or `type-check` script; run them via `npx`:

```bash
npx vitest          # run unit/component tests
npx vitest --ui     # interactive UI
npx tsc --noEmit    # standalone type-check
```

## Environment Variables

From [.env.example](.env.example):

```env
VITE_API_URL=http://localhost:8000
VITE_CLERK_PUBLISHABLE_KEY=pk_test_your_clerk_publishable_key_here
```

`VITE_*` values are statically replaced by Vite at build time. In Docker they are passed as build args (see "Docker" below).

[src/main.tsx](src/main.tsx) throws on startup if `VITE_CLERK_PUBLISHABLE_KEY` is missing.

## Project Layout

```
frontend/
├── index.html
├── nginx.conf                          # Production SPA config (used by Docker image)
├── Dockerfile                          # Multi-stage build (deps -> build -> nginx)
├── eslint.config.js
├── vite.config.ts                      # Tailwind v4 + Vitest + path aliases
├── tsconfig.{json,app.json,node.json}
├── package.json
├── .env.example
└── src/
    ├── main.tsx                        # ClerkProvider + ErrorBoundary entry
    ├── App.tsx                         # Clerk-gated shell (SignedIn/SignedOut)
    ├── App.css / index.css             # Global styles
    ├── components/
    │   ├── ConnectionForm.tsx          # Main DB connection form
    │   ├── ConnectionStatusBanner.tsx  # Status feedback banner
    │   ├── ErrorBoundary.tsx
    │   ├── FormField.tsx
    │   ├── PasswordPromptModal.tsx     # Modal to ask for cached profile passwords
    │   ├── ProfileSelector.tsx         # Profile picker
    │   ├── hooks/                      # use-auto-scroll, etc.
    │   └── __tests__/                  # Component tests
    ├── hooks/
    │   ├── useProfileSelection.ts
    │   ├── index.ts
    │   └── __tests__/
    ├── services/
    │   ├── api/                        # client.ts, errors.ts (typed API client)
    │   ├── profileStorage.ts           # LocalStorage adapter for profile metadata
    │   └── __tests__/
    ├── data/
    │   ├── apiProfileAdapter.ts        # API <-> UI profile mapping
    │   └── index.ts
    ├── types/                          # api.ts, profile.ts
    ├── constants/                      # ui.ts, validation.ts
    ├── lib/                            # Shared helpers
    ├── test/setup.ts                   # `import '@testing-library/jest-dom'`
    └── assets/
```

### Path Aliases

Configured in [vite.config.ts](vite.config.ts) and the tsconfig:

| Alias | Resolves to |
|-------|-------------|
| `@` | `src/` |
| `@components` | `src/components/` |
| `@hooks` | `src/hooks/` |
| `@services` | `src/services/` |
| `@app-types` | `src/types/` |

### Build Chunking

[vite.config.ts](vite.config.ts) splits the production bundle into `react`, `clerk`, and `ui` chunks for better caching.

## Authentication

Clerk gates the entire app:

- [src/main.tsx](src/main.tsx) wraps `<App />` with `<ClerkProvider>` and an `<ErrorBoundary>`
- [src/App.tsx](src/App.tsx) renders the connection UI inside `<SignedIn>` and a sign-in/sign-up CTA inside `<SignedOut>`
- The API client attaches the Clerk session token to backend requests; protected backend endpoints validate it via `verify_clerk_token`

## Testing

Vitest is configured in [vite.config.ts](vite.config.ts) with the `jsdom` environment and `src/test/setup.ts` (which loads `@testing-library/jest-dom`).

Existing test files:

- [src/components/__tests__/PasswordPromptModal.test.tsx](src/components/__tests__/PasswordPromptModal.test.tsx)
- [src/components/__tests__/ConnectionStatusBanner.test.tsx](src/components/__tests__/ConnectionStatusBanner.test.tsx)
- [src/hooks/__tests__/useProfileSelection.test.ts](src/hooks/__tests__/useProfileSelection.test.ts)
- [src/services/__tests__/profileStorage.test.ts](src/services/__tests__/profileStorage.test.ts)

Add new tests under a sibling `__tests__/` directory next to the file under test, named `*.test.ts` or `*.test.tsx`.

```bash
npx vitest             # watch mode
npx vitest run         # single pass
npx vitest --ui        # interactive UI
```

## Docker

The image is a multi-stage build (see [Dockerfile](Dockerfile)):

1. `dependencies`: `npm ci` against `package.json` + `npm-shrinkwrap.json`
2. `builder`: copies the source, accepts `VITE_API_URL` and `VITE_CLERK_PUBLISHABLE_KEY` as build args, runs `npm run build`
3. Final stage: `nginx:alpine` serving `/usr/share/nginx/html` with [nginx.conf](nginx.conf) (gzip, security headers, SPA fallback, asset caching, optional `/api` reverse proxy)

In [docker-compose.yml](../docker-compose.yml), the `frontend` service receives the build args from the project-root `.env`:

```yaml
frontend:
  build:
    args:
      VITE_API_URL: ${VITE_API_URL:-http://localhost:8000}
      VITE_CLERK_PUBLISHABLE_KEY: ${VITE_CLERK_PUBLISHABLE_KEY}
  ports:
    - "80:80"
```

Because `VITE_*` values are baked at build time, you must rebuild the frontend image when changing them:

```bash
docker compose build --no-cache frontend
docker compose up -d frontend
```

## Linting

```bash
npm run lint
```

ESLint is configured in [eslint.config.js](eslint.config.js) (flat config) with `typescript-eslint`, `eslint-plugin-react-hooks`, and `eslint-plugin-react-refresh`.

## Browser Support

Modern evergreen browsers; Vite's default targets apply. The Clerk SDK and Tailwind v4 set the practical floor.
