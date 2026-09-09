-- Seed script for sample meetings and race rows.
-- Run this in Supabase SQL editor after creating the schema.

insert into public.meetings (source, meeting_date, name, url, metadata)
values
    ('zone-turf', '2026-09-06', 'Cagnes-sur-Mer', 'https://zone-turf.fr/programmes', '{"track": "Cagnes-sur-Mer"}'),
    ('zone-turf', '2026-09-07', 'La Teste', 'https://zone-turf.fr/programmes', '{"track": "La Teste"}')
on conflict do nothing;

with meeting_row as (
    select id
    from public.meetings
    where meeting_date = '2026-09-06'
    order by created_at desc
    limit 1
)
insert into public.races (meeting_id, source, race_type, source_url, race_number, race_key, raw_snapshot, summary, status)
select
    meeting_row.id,
    'zone-turf',
    'trot',
    'https://zone-turf.fr/programmes/test-race-1',
    '1',
    'R1C1',
    jsonb_build_object(
        'horses', jsonb_build_array(
            jsonb_build_object('CHEVAL', 'Horse Alpha', 'COTE', 4.5, 'DIST.', '2700m'),
            jsonb_build_object('CHEVAL', 'Horse Beta', 'COTE', 5.4, 'DIST.', '2725m'),
            jsonb_build_object('CHEVAL', 'Horse Gamma', 'COTE', 6.8, 'DIST.', '2700m')
        )
    ),
    jsonb_build_object('runner_count', 3, 'status', 'scraped'),
    'scraped'
from meeting_row
on conflict do nothing;

with race_row as (
    select id
    from public.races
    where source_url = 'https://zone-turf.fr/programmes/test-race-1'
    limit 1
)
insert into public.trot_race_runners (
    race_id, "N°", "CHEVAL", "COTE", "DIST.", raw_data
)
select race_row.id, sample.num, sample.cheval, sample.cote,
       sample.dist_m, sample.raw_data
from race_row
cross join (values
    ('1', 'Horse Alpha', 4.5, 2700, jsonb_build_object('CHEVAL', 'Horse Alpha', 'COTE', 4.5, 'DIST.', '2700m')),
    ('2', 'Horse Beta', 5.4, 2725, jsonb_build_object('CHEVAL', 'Horse Beta', 'COTE', 5.4, 'DIST.', '2725m')),
    ('3', 'Horse Gamma', 6.8, 2700, jsonb_build_object('CHEVAL', 'Horse Gamma', 'COTE', 6.8, 'DIST.', '2700m'))
) as sample(num, cheval, cote, dist_m, raw_data)
on conflict (race_id, "N°") do nothing;

with race_row as (
    select id
    from public.races
    where source_url = 'https://zone-turf.fr/programmes/test-race-1'
    limit 1
)
insert into public.analysis_runs (race_id, model_version, summary, prognosis, handicap, raw_rows)
select
    race_row.id,
    'initial-migration',
    jsonb_build_object('runner_count', 3, 'winner', 'Horse Alpha'),
    jsonb_build_array(
        jsonb_build_object('CHEVAL', 'Horse Alpha', 'SCORE', 90.1),
        jsonb_build_object('CHEVAL', 'Horse Beta', 'SCORE', 84.2),
        jsonb_build_object('CHEVAL', 'Horse Gamma', 'SCORE', 78.6)
    ),
    jsonb_build_object('distance', 25, 'penalized_count', 1),
    jsonb_build_array(
        jsonb_build_object('CHEVAL', 'Horse Alpha', 'COTE', 4.5),
        jsonb_build_object('CHEVAL', 'Horse Beta', 'COTE', 5.4),
        jsonb_build_object('CHEVAL', 'Horse Gamma', 'COTE', 6.8)
    )
from race_row
on conflict do nothing;
