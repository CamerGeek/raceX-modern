begin;

create or replace function public.apply_admin_subscription_plan(
    p_user_id uuid,
    p_plan text
)
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
    plan_duration interval;
begin
    plan_duration := case p_plan
        when 'weekly' then interval '1 week'
        when 'monthly' then interval '1 month'
        when 'annual' then interval '1 year'
        else null
    end;

    if plan_duration is null then
        raise exception 'Invalid RaceX subscription plan';
    end if;

    update public.user_profiles
    set role = 'subscriber',
        subscriber_expires_at = greatest(
            coalesce(subscriber_expires_at, now()),
            now()
        ) + plan_duration,
        updated_at = now()
    where id = p_user_id
      and role <> 'admin';

    if found then
        return 'activated';
    end if;

    if exists (select 1 from public.user_profiles where id = p_user_id) then
        return 'admin';
    end if;

    return 'not_found';
end;
$$;

revoke all on function public.apply_admin_subscription_plan(uuid, text) from public;
grant execute on function public.apply_admin_subscription_plan(uuid, text) to service_role;

commit;
