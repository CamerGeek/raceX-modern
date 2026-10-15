begin;

alter table public.races
    drop constraint if exists races_race_type_check;

alter table public.races
    add constraint races_race_type_check
    check (race_type in ('flat', 'trot', 'obstacles'));

commit;
