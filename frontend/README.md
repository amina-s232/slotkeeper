React 19 + TypeScript + Vite. Talks to the Django API through a dev proxy (`/api`).

    npm ci
    npm run dev          # http://localhost:5173  (API expected on 127.0.0.1:8000)
    npm test             # unit and component tests
    npm run typecheck
    npm run build
    npm run e2e          # needs the API running with `seed_demo`, and `npx playwright install chromium`

Set `BACKEND_URL` to proxy to a different API address.

Demo accounts after `python manage.py seed_demo`: asha@demo.test (client), dr.rao@demo.test
(provider), all with password demo-pass-123.
