# RaceX Supabase Setup Checklist

Use this checklist when connecting the migration project to a real Supabase project.

## 1. Create the Supabase project

1. Create a project at <https://supabase.com/dashboard>.
2. Choose a project name, region, and database password.
3. Wait until the project status is healthy.
4. Open **Project Settings > API** and copy:
   - **Project URL**: `https://<project-ref>.supabase.co`
   - **service_role key**: the secret backend key

Do not commit the `service_role` key or place it in the Next.js frontend. It bypasses Supabase Row Level Security and belongs only in the FastAPI/Render environment.

## 2. Create the database schema

1. Open **SQL Editor** in the Supabase dashboard.
2. Create a new query.
3. Paste and run [`backend/supabase_schema.sql`](backend/supabase_schema.sql).
   If the schema was already installed, run the updated file again to add phone
   storage and update the signup trigger; the profile phone-column change is
   safe to re-run.
4. Open **Table Editor** and confirm these tables exist:
   - `meetings`
   - `races`
   - `race_runners`
   - `analysis_runs`
   - `quinte_odds_snapshots`
   - `user_profiles`
   - `jobs`
5. Confirm the `latest_analysis` view exists under **Database > Views**.

## 3. Optional sample data

To load sample records for a first API check:

1. In **SQL Editor**, create another query.
2. Paste and run [`backend/seed_supabase.sql`](backend/seed_supabase.sql).
3. In **Table Editor**, confirm that the seed created two meetings, one race, three race runners, and one analysis row.

The seed script is safe to run repeatedly for the current sample values, but it is demonstration data and should not be used as production race data.

## 4. Local backend environment

Copy `backend/.env.example` to `backend/.env`, then replace the two placeholders with values from **Project Settings > API**:

```dotenv
APP_NAME=RaceX API
API_PREFIX=/api/v1
CORS_ORIGINS=http://localhost:3000
SOURCE_TIMEOUT_SECONDS=20
MODEL_VERSION=initial-migration
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_KEY=<service_role-key>
```

Run the backend from `backend` with Python 3.12:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:PYTHONPATH = (Get-Location).Path
uvicorn app.main:app --reload
```

The local frontend environment is:

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<publishable-or-anon-key>
```

Save it as `frontend/.env.local`.

The public browser key is safe to expose when Row Level Security is enabled.
Never use the `service_role` key in the frontend. The backend continues to use
`SUPABASE_KEY` as its secret service-role key.

## 5. Configure roles and first administrator

The schema creates a `user_profiles` row with role `demo` and a seven-day
expiry and saves the phone number entered during signup. Existing Supabase Auth
users are backfilled as `simple` so this migration does not grant old accounts
a trial automatically.
Expired demo and subscriber access resolves to `simple`; anonymous visitors
remain able to use the public homepage. Protected API endpoints validate the
Supabase access token and check the profile role server-side.

To bootstrap the first administrator:

1. Create an account through the RaceX `/account` page.
2. Confirm the email if Supabase email confirmation is enabled.
3. Run this in Supabase SQL Editor, substituting that account's email:

```sql
update public.user_profiles
set role = 'admin', demo_expires_at = null, subscriber_expires_at = null
where lower(email) = lower('admin@example.com');
```

4. Sign out and back in so RaceX reloads the administrator role.

RaceX does not create a shared default administrator login or password. Promote
an account you control using the SQL above; never use shared credentials in
production.

From **Gestion des comptes**, administrators can activate or extend a
subscriber account after confirming a 5,000 FCFA manual transfer. Each action
adds one calendar month to a current subscription, or starts one month
immediately if the prior access has expired. No payment is collected or
automatically verified by RaceX. Demo-expired users see WhatsApp contacts for
Moov Burkina (`+226 60 35 44 00`) and Orange (`+226 74 91 15 38`).

## 6. Verify locally

Check the health endpoint:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Expected result:

```text
status service
------ -------
ok     RaceX API
```

Check the seeded race through the API. Replace `<race-id>` with the UUID from the `races` table:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/supabase-races/<race-id>
```

The response should contain `race` and `latest_analysis`.

## 7. Configure Render

The Render service is defined in [`render.yaml`](render.yaml). Create or update the `racex-api` web service with:

| Variable | Value |
| --- | --- |
| `CORS_ORIGINS` | `https://<your-vercel-project>.vercel.app` |
| `MODEL_VERSION` | `initial-migration` |
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` |
| `SUPABASE_KEY` | the Supabase `service_role` key |

Set `SUPABASE_URL` and `SUPABASE_KEY` as secret values in Render. Do not put either value in `render.yaml`.

The blueprint also defines a `racex-quinte-odds-poller` Cron Job. It uses the same Supabase secrets and runs `python -m app.tasks.poll_quinte_odds` every 30 minutes. Ensure your Render plan supports Cron Jobs and sync the updated blueprint. The task records the current Quinté+ runners' odds in `quinte_odds_snapshots` and stops collecting after the scheduled start time.

After deployment, verify:

```powershell
Invoke-RestMethod https://<your-render-service>.onrender.com/health
```

## 8. Configure Vercel

Create the Vercel project from the `frontend` directory and set this environment variable:

| Variable | Preview value | Production value |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | `https://<your-render-service>.onrender.com` | `https://<your-render-service>.onrender.com` |
| `NEXT_PUBLIC_SUPABASE_URL` | `https://<project-ref>.supabase.co` | `https://<project-ref>.supabase.co` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase publishable/anon key | Supabase publishable/anon key |

Redeploy after adding or changing this variable because Next.js reads `NEXT_PUBLIC_*` values during the build.

## 9. Final browser check

1. Open the deployed Vercel URL.
2. Submit a valid Zone-Turf race URL.
3. Confirm the request reaches Render without a CORS error.
4. Confirm the analysis result appears in the page.
5. Confirm the new `races` and `analysis_runs` rows appear in Supabase when the persistence route is used.

## Required values summary

You need these four project-specific values before deployment:

```text
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_KEY=<service_role-key>
CORS_ORIGINS=https://<your-vercel-project>.vercel.app
NEXT_PUBLIC_API_URL=https://<your-render-service>.onrender.com
```
