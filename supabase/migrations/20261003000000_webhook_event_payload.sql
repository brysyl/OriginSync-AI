alter table public.webhook_events
  add column if not exists payload jsonb;

update public.webhook_events
set payload = '{}'::jsonb
where payload is null;

alter table public.webhook_events
  alter column payload set not null;
