begin;

create table if not exists public.saved_combinations (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.user_profiles(id) on delete cascade,
    race_id uuid not null references public.races(id) on delete cascade,
    name text not null check (length(trim(name)) between 1 and 80),
    plan jsonb not null,
    created_at timestamptz not null default now()
);

create index if not exists idx_saved_combinations_user_race
    on public.saved_combinations (user_id, race_id, created_at desc);

alter table public.saved_combinations enable row level security;

drop policy if exists saved_combinations_owner_access on public.saved_combinations;
create policy saved_combinations_owner_access
    on public.saved_combinations
    for all
    to authenticated
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

grant select, insert, delete on public.saved_combinations to authenticated;
grant select, insert, delete on public.saved_combinations to service_role;

commit;
