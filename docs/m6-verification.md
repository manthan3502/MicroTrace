# M6 dashboard and Gate D

Exactly Trace List and Trace Detail, root/unknown routes redirect to the list.
Local React state/URL params, native fetch with abort protection, no new dependencies.
Manual refresh retains data/selection; real links preserve filtered Back navigation.
List filters, offset paging, UTC timestamps and explicit loading/empty/error states.
API-ordered waterfall with bounded geometry, readable ticks, depth indentation, minimum
3px width, service chips, solid SERVER/hollow CLIENT/thinner INTERNAL, ERROR text/stripe
and tint. Persistent desktop details show timing/attributes/errors/IDs and parent action.
Below 1100px, details stack. Missing parents and orphan subtrees remain visible.

Actual checks:
- Native npm test/lint/build initially unavailable because local node_modules was absent;
  used the existing Docker dependency environment. No dependency change.
- First Docker suite: 31 passed/1 failed; metadata-error helper changed the select label.
  Added explicit accessible name. ESLint found an imprecise numeric literal; exact BigInt
  validation replaced it. TypeScript/production build already passed.
- Final docker compose up --build -d --wait frontend: PASS.
- Docker npm test: 32 passed across 3 files, 0.982s. Covers all list/detail states,
  URL filters/paging, validation, refresh/selection/parent, error and orphan display,
  durations, offsets, scale/ticks/zero safety/min-width and route handling.
- Docker npm run lint: PASS; npm run build (TypeScript + Vite): PASS, 829ms Vite build.
- Manual in-app browser on real Compose PostgreSQL telemetry: healthy eight-span tree,
  slow eight-span trace (301ms INTERNAL in a 347ms trace), error five-span trace/four
  ERROR spans/no Notification. All visual kinds, error stripes/tint, selection, parent
  navigation, manual refresh and combined service/ERROR/min-duration filters verified.
- Real orphan telemetry through collector/DB/query: incomplete warning, ORPHAN marker,
  missing-parent detail and subtree indentation PASS. Only its two synthetic rows removed.
- At 1024px: one-column layout and static details below waterfall, no body overflow;
  viewport restored. Browser console warnings/errors: none.
- Real browser QA screenshots saved locally (ignored); fixture screenshots are not evidence.
- docker compose config --quiet; check_foundation.py: PASS; git diff --check PASS.
- Backend regression at preceding M5 boundary: 190 passed; no backend changes in M6.
- repository identity/privacy verification before milestone commit: PASS.

Gate D: PASS. Real services -> default bounded export -> collector -> PostgreSQL ->
query -> real UI for healthy, slow and error. No blockers. Clipboard copy and optional
arrow-key navigation omitted as allowed polish. Best-effort telemetry, no auth/retention.

Understand: geometry uses robust scale, while summary retains actual root duration;
shape/text communicates kind; status is distinct from completeness; the API reconstructs
the tree; URL filters preserve navigation; selection is local UI state.
