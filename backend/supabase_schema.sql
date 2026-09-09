-- Supabase schema for RaceX
-- Run this in the SQL editor of your Supabase project.

create extension if not exists pgcrypto;

create table if not exists public.meetings (
    id uuid primary key default gen_random_uuid(),
    source text not null default 'zone-turf',
    meeting_date date not null,
    name text,
    url text,
    metadata jsonb default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.races (
    id uuid primary key default gen_random_uuid(),
    meeting_id uuid references public.meetings(id) on delete cascade,
    source text not null default 'zone-turf',
    race_type text not null check (race_type in ('flat','trot')),
    source_url text not null,
    race_number text,
    race_key text,
    raw_snapshot jsonb default '{}'::jsonb,
    summary jsonb default '{}'::jsonb,
    status text not null default 'pending' check (status in ('pending','scraped','analyzed','failed')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- One row per starter returned by the Zone-Turf flat or trot scraper.
-- Names intentionally match the scraper's final uppercase DataFrame columns.
-- raw_data preserves source-specific columns not present in every discipline.
create table if not exists public.race_runners (
    id uuid primary key default gen_random_uuid(),
    race_id uuid not null references public.races(id) on delete cascade,
    "N°" text,
    "CHEVAL" text,
    "COTE" numeric(10, 2),
    "DIST." integer,
    "SEXE" text,
    "SEX" text,
    "AGE" integer,
    "POIDS" numeric(10, 2),
    "PAST_POIDS" numeric(10, 2),
    "MUSIQUE" text,
    "JOCKEY" text,
    "ENTRAINEUR" text,
    "JOCKEY_MUSIC" text,
    "TRAINER_MUSIC" text,
    "FORME_J" numeric(10, 2),
    "FORME_T" numeric(10, 2),
    "FORME" numeric(10, 2),
    "IF" numeric(10, 2),
    "S_COEFF" numeric(10, 2),
    "IC" numeric(10, 2),
    "COMPOSITE_SCORE" numeric(10, 2),
    "CLASS_ADVANTAGE" numeric(10, 2),
    "IS_PENALIZED" boolean,
    "HANDICAP_DISTANCE" integer,
    "HORSE_LINK" text,
    "RACE_URL" text,
    "RACE_DATE" text,
    "HIPPODROME" text,
    "REF_COURSE" text,
    "PRIZE_NAME" text,
    "DIST" integer,
    "RACE_CONDITIONS" text,
    "DESCRIPTIF" text,
    "Q+" boolean,
    "TABLE_INDEX" integer,
    "COURSE_ID" text,
    "ID_COURSE" text,
    "MEETING_ID" text,
    "STARTERS" integer,
    "NUM_STARTERS" integer,
    "ALLOCATION" numeric(12, 2),
    "LICE" text,
    "DISTANCE" integer,
    "HANDICAP" boolean,
    "RECLAMER" boolean,
    "LISTED" boolean,
    "GRP" text,
    "CLASSE" text,
    "HIPPOID" integer,
    "SURFACE" text,
    "OEILL." text,
    "DEF." text,
    "J-DECH." numeric(10, 2),
    "N_WEIGHT" numeric(10, 2),
    "GAIN" text,
    "PMU" text,
    "PMU_FR" text,
    "DSCP" integer,
    raw_data jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (race_id, "N°")
);

-- Upgrade the first version of race_runners, which used translated names.
do $$
begin
    if exists (select 1 from information_schema.columns where table_schema = 'public' and table_name = 'race_runners' and column_name = 'runner_number')
       and not exists (select 1 from information_schema.columns where table_schema = 'public' and table_name = 'race_runners' and column_name = 'N°') then
        alter table public.race_runners rename column runner_number to "N°";
        alter table public.race_runners rename column horse_name to "CHEVAL";
        alter table public.race_runners rename column odds to "COTE";
        alter table public.race_runners rename column distance_m to "DIST.";
        alter table public.race_runners rename column sex to "SEXE";
        alter table public.race_runners rename column age to "AGE";
        alter table public.race_runners rename column weight to "POIDS";
        alter table public.race_runners rename column previous_weight to "PAST_POIDS";
        alter table public.race_runners rename column horse_form to "MUSIQUE";
        alter table public.race_runners rename column jockey_name to "JOCKEY";
        alter table public.race_runners rename column trainer_name to "ENTRAINEUR";
        alter table public.race_runners rename column jockey_form to "FORME_J";
        alter table public.race_runners rename column trainer_form to "FORME_T";
        alter table public.race_runners rename column fitness_score to "IF";
        alter table public.race_runners rename column success_coefficient to "S_COEFF";
        alter table public.race_runners rename column composite_score to "COMPOSITE_SCORE";
        alter table public.race_runners rename column class_advantage to "CLASS_ADVANTAGE";
        alter table public.race_runners rename column is_penalized to "IS_PENALIZED";
        alter table public.race_runners rename column source_horse_url to "HORSE_LINK";
    end if;
end $$;

alter table public.race_runners add column if not exists "SEX" text;
alter table public.race_runners add column if not exists "JOCKEY_MUSIC" text;
alter table public.race_runners add column if not exists "TRAINER_MUSIC" text;
alter table public.race_runners add column if not exists "FORME" numeric(10, 2);
alter table public.race_runners add column if not exists "IC" numeric(10, 2);
alter table public.race_runners add column if not exists "HANDICAP_DISTANCE" integer;
alter table public.race_runners add column if not exists "RACE_URL" text;
alter table public.race_runners add column if not exists "RACE_DATE" text;
alter table public.race_runners add column if not exists "HIPPODROME" text;
alter table public.race_runners add column if not exists "REF_COURSE" text;
alter table public.race_runners add column if not exists "PRIZE_NAME" text;
alter table public.race_runners add column if not exists "DIST" integer;
alter table public.race_runners add column if not exists "RACE_CONDITIONS" text;
alter table public.race_runners add column if not exists "DESCRIPTIF" text;
alter table public.race_runners add column if not exists "Q+" boolean;
alter table public.race_runners add column if not exists "TABLE_INDEX" integer;
alter table public.race_runners add column if not exists "COURSE_ID" text;
alter table public.race_runners add column if not exists "ID_COURSE" text;
alter table public.race_runners add column if not exists "MEETING_ID" text;
alter table public.race_runners add column if not exists "STARTERS" integer;
alter table public.race_runners add column if not exists "NUM_STARTERS" integer;
alter table public.race_runners add column if not exists "ALLOCATION" numeric(12, 2);
alter table public.race_runners add column if not exists "LICE" text;
alter table public.race_runners add column if not exists "DISTANCE" integer;
alter table public.race_runners add column if not exists "HANDICAP" boolean;
alter table public.race_runners add column if not exists "RECLAMER" boolean;
alter table public.race_runners add column if not exists "LISTED" boolean;
alter table public.race_runners add column if not exists "GRP" text;
alter table public.race_runners add column if not exists "CLASSE" text;
alter table public.race_runners add column if not exists "HIPPOID" integer;
alter table public.race_runners add column if not exists "SURFACE" text;
alter table public.race_runners add column if not exists "OEILL." text;
alter table public.race_runners add column if not exists "DEF." text;
alter table public.race_runners add column if not exists "J-DECH." numeric(10, 2);
alter table public.race_runners add column if not exists "N_WEIGHT" numeric(10, 2);
alter table public.race_runners add column if not exists "GAIN" text;
alter table public.race_runners add column if not exists "PMU" text;
alter table public.race_runners add column if not exists "PMU_FR" text;
alter table public.race_runners add column if not exists "DSCP" integer;

-- Scraped runner rows are stored in discipline-specific tables because flat
-- and trotting pages do not expose an identical column contract.
create table if not exists public.flat_race_runners (
    id uuid primary key default gen_random_uuid(),
    race_id uuid not null references public.races(id) on delete cascade,
    runner_number text,
    "N°" text,
    "CHEVAL" text,
    "COTE" numeric(10, 2),
    "DIST." integer,
    "SEXE" text,
    "AGE" integer,
    "POIDS" numeric(10, 2),
    "PAST_POIDS" numeric(10, 2),
    "MUSIQUE" text,
    "JOCKEY" text,
    "ENTRAINEUR" text,
    "JOCKEY_MUSIC" text,
    "TRAINER_MUSIC" text,
    "FORME_J" numeric(10, 2),
    "FORME_T" numeric(10, 2),
    "FORME" numeric(10, 2),
    "IF" numeric(10, 2),
    "S_COEFF" numeric(10, 2),
    "IC" numeric(10, 2),
    "COMPOSITE_SCORE" numeric(10, 2),
    "CLASS_ADVANTAGE" numeric(10, 2),
    "IS_PENALIZED" boolean,
    "HORSE_LINK" text,
    "RACE_URL" text,
    "RACE_DATE" text,
    "HIPPODROME" text,
    "REF_COURSE" text,
    "PRIZE_NAME" text,
    "DIST" integer,
    "RACE_CONDITIONS" text,
    "DESCRIPTIF" text,
    "Q+" boolean,
    "TABLE_INDEX" integer,
    "COURSE_ID" text,
    "MEETING_ID" text,
    "STARTERS" integer,
    "NUM_STARTERS" integer,
    "ALLOCATION" numeric(12, 2),
    "LICE" text,
    "DISTANCE" integer,
    "HANDICAP" boolean,
    "RECLAMER" boolean,
    "LISTED" boolean,
    "GRP" text,
    "CLASSE" text,
    "HIPPOID" integer,
    "SURFACE" text,
    "OEILL." text,
    "DEF." text,
    "J-DECH." numeric(10, 2),
    "N_WEIGHT" numeric(10, 2),
    "GAIN" text,
    "PMU" text,
    "PMU_FR" text,
    "DSCP" integer,
    raw_data jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (race_id, "N°")
);

create table if not exists public.trot_race_runners (
    id uuid primary key default gen_random_uuid(),
    race_id uuid not null references public.races(id) on delete cascade,
    runner_number text,
    "N°" text,
    "CHEVAL" text,
    "COTE" numeric(10, 2),
    "DIST." integer,
    "SEXE" text,
    "AGE" integer,
    "DERNIÈRES PERF." text,
    "MUSIQUE" text,
    "REC." numeric(10, 2),
    "DEF." text,
    "JOCKEY" text,
    "ENTRAINEUR" text,
    "JOCKEY_MUSIC" text,
    "TRAINER_MUSIC" text,
    "FORME_J" numeric(10, 2),
    "FORME_T" numeric(10, 2),
    "FA" numeric(10, 2),
    "FM" numeric(10, 2),
    "IF" numeric(10, 2),
    "S_COEFF" numeric(10, 2),
    "S_COEFF_norm" numeric(10, 2),
    "disq_count" integer,
    "disq_harness_rate" numeric(10, 4),
    "disq_mounted_rate" numeric(10, 4),
    "recent_disq_count" integer,
    "recent_disq_rate" numeric(10, 4),
    "DQ_Risk" numeric(10, 2),
    "DQ_Risk_Amplified" numeric(10, 2),
    "shoeing_aggressiveness" numeric(10, 4),
    "HORSE_LINK" text,
    "RACE_URL" text,
    "RACE_DATE" text,
    "HIPPODROME" text,
    "REF_COURSE" text,
    "PRIZE_NAME" text,
    "DIST" integer,
    "RACE_CONDITIONS" text,
    "DESCRIPTIF" text,
    "Q+" boolean,
    "TABLE_INDEX" integer,
    "COURSE_ID" text,
    "MEETING_ID" text,
    raw_data jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (race_id, "N°")
);

create index if not exists idx_flat_race_runners_race_id on public.flat_race_runners(race_id);
create index if not exists idx_trot_race_runners_race_id on public.trot_race_runners(race_id);
alter table public.flat_race_runners add column if not exists runner_number text;
alter table public.trot_race_runners add column if not exists runner_number text;
alter table public.trot_race_runners add column if not exists "DERNIÈRES PERF." text;
alter table public.trot_race_runners add column if not exists "REC." numeric(10, 2);
alter table public.trot_race_runners add column if not exists "DEF." text;
alter table public.trot_race_runners add column if not exists "FA" numeric(10, 2);
alter table public.trot_race_runners add column if not exists "FM" numeric(10, 2);
alter table public.trot_race_runners add column if not exists "S_COEFF_norm" numeric(10, 2);
alter table public.trot_race_runners add column if not exists "disq_count" integer;
alter table public.trot_race_runners add column if not exists "disq_harness_rate" numeric(10, 4);
alter table public.trot_race_runners add column if not exists "disq_mounted_rate" numeric(10, 4);
alter table public.trot_race_runners add column if not exists "recent_disq_count" integer;
alter table public.trot_race_runners add column if not exists "recent_disq_rate" numeric(10, 4);
alter table public.trot_race_runners add column if not exists "DQ_Risk" numeric(10, 2);
alter table public.trot_race_runners add column if not exists "DQ_Risk_Amplified" numeric(10, 2);
alter table public.trot_race_runners add column if not exists "shoeing_aggressiveness" numeric(10, 4);
update public.flat_race_runners set runner_number = "N°" where runner_number is null;
update public.trot_race_runners set runner_number = "N°" where runner_number is null;
create unique index if not exists uq_flat_race_runners_race_number on public.flat_race_runners(race_id, runner_number);
create unique index if not exists uq_trot_race_runners_race_number on public.trot_race_runners(race_id, runner_number);

create table if not exists public.analysis_runs (
    id uuid primary key default gen_random_uuid(),
    race_id uuid not null references public.races(id) on delete cascade,
    model_version text not null,
    summary jsonb default '{}'::jsonb,
    prognosis jsonb default '[]'::jsonb,
    handicap jsonb default '{}'::jsonb,
    raw_rows jsonb default '[]'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists public.jobs (
    id uuid primary key default gen_random_uuid(),
    type text not null,
    status text not null default 'queued' check (status in ('queued','running','done','failed')),
    progress integer not null default 0,
    error_message text,
    metadata jsonb default '{}'::jsonb,
    result_url text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    full_name text,
    created_at timestamptz not null default now()
);

create index if not exists idx_meetings_date on public.meetings(meeting_date);
create index if not exists idx_meetings_source on public.meetings(source);
create index if not exists idx_races_meeting_id on public.races(meeting_id);
create index if not exists idx_races_source_url on public.races(source_url);
create index if not exists idx_races_race_key on public.races(race_key);
create index if not exists idx_race_runners_race_id on public.race_runners(race_id);
create index if not exists idx_race_runners_horse_name on public.race_runners("CHEVAL");
create index if not exists idx_analysis_runs_race_id on public.analysis_runs(race_id);
create index if not exists idx_jobs_status on public.jobs(status);

create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_meetings_updated_at on public.meetings;
create trigger trg_meetings_updated_at
before update on public.meetings
for each row execute function public.set_updated_at();

drop trigger if exists trg_races_updated_at on public.races;
create trigger trg_races_updated_at
before update on public.races
for each row execute function public.set_updated_at();

drop trigger if exists trg_race_runners_updated_at on public.race_runners;
create trigger trg_race_runners_updated_at
before update on public.race_runners
for each row execute function public.set_updated_at();

drop trigger if exists trg_flat_race_runners_updated_at on public.flat_race_runners;
create trigger trg_flat_race_runners_updated_at
before update on public.flat_race_runners
for each row execute function public.set_updated_at();

drop trigger if exists trg_trot_race_runners_updated_at on public.trot_race_runners;
create trigger trg_trot_race_runners_updated_at
before update on public.trot_race_runners
for each row execute function public.set_updated_at();

drop trigger if exists trg_jobs_updated_at on public.jobs;
create trigger trg_jobs_updated_at
before update on public.jobs
for each row execute function public.set_updated_at();

-- Optional helper: read the latest analysis for a race
create or replace view public.latest_analysis as
select distinct on (race_id)
    race_id,
    model_version,
    summary,
    prognosis,
    handicap,
    raw_rows,
    created_at
from public.analysis_runs
order by race_id, created_at desc;
