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
before enabling authentication. New accounts receive a seven-day demo. An
administrator can activate or extend a subscriber for one calendar month after
confirming the manual 5,000 FCFA transfer.

Supabase and deployment setup is documented in [SUPABASE_SETUP_CHECKLIST.md](SUPABASE_SETUP_CHECKLIST.md).

## Deployment

- Deploy `frontend` as a Vercel Next.js project.
- Deploy `backend` as a Render Docker web service.
- The backend is pinned to Python 3.12 because the pinned ML and Supabase dependencies do not provide compatible wheels for Python 3.14.
- Set backend `CORS_ORIGINS` to the Vercel URL.
- Keep generated reports and job state in managed storage when those features are added; Render's local filesystem is ephemeral.

The frontend is installable as a PWA. Its service worker caches the app shell and static Next.js assets, and shows an offline page when a navigation cannot reach the network. Race data and API responses are not cached, so analysis requires a connection.

The original `raceX` project remains unchanged and is the behavioral reference during migration.
