# RaceX Modern

Migration workspace for RaceX: FastAPI backend on Render and Next.js frontend on Vercel.

## Local development

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH = (Get-Location).Path
uvicorn app.main:app --reload
```

Frontend:

```powershell
cd frontend
npm run dev
```

Set `NEXT_PUBLIC_API_URL=http://localhost:8000` in `frontend/.env.local`.

For account creation and login, also set `NEXT_PUBLIC_SUPABASE_URL` and
`NEXT_PUBLIC_SUPABASE_ANON_KEY` in `frontend/.env.local`. The public key is
intended for browser use; never put the Supabase `service_role` key in the
frontend. Run the account/profile section in `backend/supabase_schema.sql`
before enabling authentication. New accounts receive a seven-day demo. The
administrator promotion endpoint remains available for manually confirmed
payments when needed.

Chariow checkout starts from the account page and associates each sale with its
RaceX user through checkout metadata. To enable it, configure `CHARIOW_API_KEY`,
`CHARIOW_PULSE_SECRET`, `CHARIOW_PRODUCT_ID`, and `CHARIOW_RETURN_URL` in the
backend environment. `CHARIOW_PULSE_SECRET` is the signing secret for the
specific Chariow Pulse, not the API key. In Chariow, create a Pulse for
**Successful Sale**, restricted to the RaceX product, and set its URL to
`https://<backend-host>/api/v1/webhooks/chariow`. Copy the Pulse signing secret
to `CHARIOW_PULSE_SECRET`, then run the Chariow section of
`backend/supabase_schema.sql` in Supabase. Successful verified sales add one
calendar month of access; failed or unverified events do not.

Supabase and deployment setup is documented in [SUPABASE_SETUP_CHECKLIST.md](SUPABASE_SETUP_CHECKLIST.md).

## Deployment

- Deploy `frontend` as a Vercel Next.js project.
- Deploy `backend` as a Render Docker web service.
- Vercel and Render provide HTTPS at the deployment edge; keep their HTTPS redirects enabled. The frontend also sends HSTS and baseline browser security headers.
- The frontend's canonical URL, sitemap, and robots file currently use `https://frontend-camer-geek.vercel.app`. Update `frontend/src/app/site-config.ts` if the production domain changes.
- Configure a CAPTCHA provider in Supabase Auth before enabling public account registration at scale. RaceX does not currently load third-party analytics or advertising trackers, so it does not show a non-essential cookie-consent banner.
- The backend is pinned to Python 3.12 because the pinned ML and Supabase dependencies do not provide compatible wheels for Python 3.14.
- Set backend `CORS_ORIGINS` to the Vercel URL.
- Store Chariow API and Pulse signing secrets as backend secrets; never expose them in frontend configuration. Set `CHARIOW_RETURN_URL` to the deployed frontend account URL.
- Keep generated reports and job state in managed storage when those features are added; Render's local filesystem is ephemeral.

The frontend is installable as a PWA. Its service worker caches the app shell and static Next.js assets, and shows an offline page when a navigation cannot reach the network. Race data and API responses are not cached, so analysis requires a connection.

The original `raceX` project remains unchanged and is the behavioral reference during migration.
