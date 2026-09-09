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

Supabase and deployment setup is documented in [SUPABASE_SETUP_CHECKLIST.md](SUPABASE_SETUP_CHECKLIST.md).

## Deployment

- Deploy `frontend` as a Vercel Next.js project.
- Deploy `backend` as a Render Docker web service.
- Set backend `CORS_ORIGINS` to the Vercel URL.
- Keep generated reports and job state in managed storage when those features are added; Render's local filesystem is ephemeral.

The original `raceX` project remains unchanged and is the behavioral reference during migration.
