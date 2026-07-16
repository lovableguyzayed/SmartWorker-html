-- ============================================================================
-- SmartWorker — Supabase Row Level Security policies (per-account isolation)
-- ============================================================================
--
-- IMPORTANT CONTEXT
-- The Flask app connects to Postgres directly as the table owner, which BYPASSES
-- RLS. The app's own data isolation is therefore enforced in application code
-- (see tenancy.py). These policies exist as DEFENCE IN DEPTH for Supabase's
-- auto-generated REST/GraphQL API (PostgREST), which the app does not use but
-- which is reachable with the anon/authenticated keys. Without policies, the
-- app already enables RLS with no policies (deny-all) on every table at startup,
-- so the API is locked. Run this file to instead allow each authenticated
-- Supabase user to reach only their own workspace's rows through that API.
--
-- Apply it once in the Supabase Dashboard → SQL Editor (or psql). Idempotent.
-- ============================================================================

-- Account ids the current Supabase auth user belongs to. SECURITY DEFINER so
-- the policy can read public.users regardless of the caller's own row access.
create or replace function public.current_account_ids()
returns setof integer
language sql
stable
security definer
set search_path = public
as $$
  select account_id
  from public.users
  where supabase_uid = auth.uid()::text
    and account_id is not null;
$$;

revoke all on function public.current_account_ids() from public;
grant execute on function public.current_account_ids() to authenticated;

-- Per-tenant tables: an authenticated user may touch a row only when its
-- account_id is one of their account ids.
do $$
declare
  t text;
  tenant_tables text[] := array[
    'company_settings','sites','departments','projects','work_tasks',
    'project_assignments','worker_modifications','leave_adjustments',
    'worker_transactions','notifications','workers','attendance_records',
    'closure_days','payroll_records'
  ];
begin
  foreach t in array tenant_tables loop
    execute format('alter table public.%I enable row level security;', t);
    execute format('drop policy if exists tenant_isolation on public.%I;', t);
    execute format(
      'create policy tenant_isolation on public.%I for all to authenticated '
      'using (account_id in (select public.current_account_ids())) '
      'with check (account_id in (select public.current_account_ids()));', t);
  end loop;
end $$;

-- users: a user may read the rows of their own workspace (team roster) and
-- update only their own row.
alter table public.users enable row level security;
drop policy if exists users_same_account_read on public.users;
create policy users_same_account_read on public.users for select to authenticated
  using (account_id in (select public.current_account_ids()));
drop policy if exists users_self_update on public.users;
create policy users_self_update on public.users for update to authenticated
  using (supabase_uid = auth.uid()::text)
  with check (supabase_uid = auth.uid()::text);

-- accounts: a user may read the account(s) they belong to.
alter table public.accounts enable row level security;
drop policy if exists accounts_member_read on public.accounts;
create policy accounts_member_read on public.accounts for select to authenticated
  using (id in (select public.current_account_ids()));
