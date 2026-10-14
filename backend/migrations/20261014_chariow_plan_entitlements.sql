begin;

drop function if exists public.apply_chariow_sale(text, text, uuid);

create or replace function public.apply_chariow_sale(
    p_delivery_id text,
    p_sale_id text,
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

    insert into public.chariow_processed_sales (sale_id, delivery_id, user_id)
    values (p_sale_id, p_delivery_id, p_user_id)
    on conflict do nothing;

    if not found then
        return 'duplicate';
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

    if not found then
        raise exception 'RaceX subscription profile does not exist or is an admin';
    end if;

    return 'activated';
end;
$$;

revoke all on function public.apply_chariow_sale(text, text, uuid, text) from public;
grant execute on function public.apply_chariow_sale(text, text, uuid, text) to service_role;

commit;
