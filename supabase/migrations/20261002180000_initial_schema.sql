create extension if not exists vector with schema extensions;
create extension if not exists pgcrypto with schema extensions;

create type public.trade_case_status as enum (
  'received',
  'processing',
  'verified',
  'review_required',
  'rejected',
  'settlement_pending',
  'settled',
  'settlement_failed'
);

create type public.settlement_status as enum (
  'not_eligible',
  'pending',
  'processing',
  'completed',
  'failed'
);

create type public.roo_rule_type as enum (
  'wholly_obtained',
  'value_added',
  'change_in_tariff_classification',
  'specific_process',
  'alternative'
);

create table public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null check (length(trim(name)) between 1 and 200),
  country_code char(2) check (country_code is null or country_code ~ '^[A-Z]{2}$'),
  created_at timestamptz not null default now()
);

create table public.organization_memberships (
  organization_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null check (role in ('owner', 'admin', 'analyst', 'viewer')),
  created_at timestamptz not null default now(),
  primary key (organization_id, user_id)
);

create index organization_memberships_user_idx
  on public.organization_memberships(user_id, organization_id);

create function public.is_organization_member(target_organization_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.organization_memberships membership
    where membership.organization_id = target_organization_id
      and membership.user_id = (select auth.uid())
  );
$$;

create table public.tariff_rules (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid references public.organizations(id) on delete cascade,
  agreement text not null,
  hs_code_prefix text not null check (hs_code_prefix ~ '^[0-9]{2,6}$'),
  origin_country char(2) not null check (origin_country ~ '^[A-Z]{2}$'),
  destination_country char(2) not null check (destination_country ~ '^[A-Z]{2}$'),
  rule_type public.roo_rule_type not null,
  minimum_value_added_pct numeric(5, 2)
    check (minimum_value_added_pct between 0 and 100),
  required_tariff_heading_prefix text
    check (required_tariff_heading_prefix is null or required_tariff_heading_prefix ~ '^[0-9]{2,6}$'),
  excluded_inputs jsonb not null default '[]'::jsonb
    check (jsonb_typeof(excluded_inputs) = 'array'),
  source_uri text not null check (source_uri ~ '^https://'),
  source_version text not null,
  source_sha256 char(64) not null check (source_sha256 ~ '^[0-9a-f]{64}$'),
  verified_by uuid not null references auth.users(id),
  verified_at timestamptz not null,
  effective_from date not null,
  effective_to date,
  embedding extensions.vector(768),
  embedding_model text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (effective_to is null or effective_to >= effective_from)
);

create index tariff_rules_lookup_idx
  on public.tariff_rules(origin_country, destination_country, hs_code_prefix, effective_from);
create index tariff_rules_embedding_idx
  on public.tariff_rules using hnsw (embedding extensions.vector_cosine_ops)
  where embedding is not null;

create table public.trade_cases (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  created_by uuid references auth.users(id) on delete set null,
  external_reference text,
  idempotency_key text not null,
  request_hash char(64) not null check (request_hash ~ '^[0-9a-f]{64}$'),
  status public.trade_case_status not null default 'received',
  goods_description text not null check (length(trim(goods_description)) between 1 and 10000),
  hs_code text check (hs_code is null or hs_code ~ '^[0-9]{6,10}$'),
  hs_code_confidence numeric(5, 4) check (hs_code_confidence between 0 and 1),
  hs_code_rationale text,
  origin_country char(2) not null check (origin_country ~ '^[A-Z]{2}$'),
  destination_country char(2) not null check (destination_country ~ '^[A-Z]{2}$'),
  cif_amount numeric(18, 2) not null check (cif_amount >= 0),
  currency char(3) not null check (currency ~ '^[A-Z]{3}$'),
  wholly_obtained boolean,
  value_added_pct numeric(5, 2) check (value_added_pct between 0 and 100),
  origin_eligible boolean,
  origin_rule_id uuid references public.tariff_rules(id) on delete set null,
  origin_decision jsonb not null default '{}'::jsonb,
  rigs_score numeric(5, 4) check (rigs_score between 0 and 1),
  rigs_components jsonb not null default '{}'::jsonb,
  settlement_status public.settlement_status not null default 'not_eligible',
  beneficiary_email text,
  settlement_amount numeric(18, 2) check (settlement_amount is null or settlement_amount >= 0),
  settlement_currency char(3) check (settlement_currency is null or settlement_currency ~ '^[A-Z]{3}$'),
  paypal_sender_batch_id text unique,
  paypal_payout_batch_id text unique,
  error_code text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  settled_at timestamptz,
  unique (organization_id, external_reference),
  unique (organization_id, idempotency_key)
);

create index trade_cases_org_created_idx
  on public.trade_cases(organization_id, created_at desc);
create index trade_cases_org_status_idx
  on public.trade_cases(organization_id, status, created_at desc);

create table public.trusted_beneficiaries (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  email text not null check (email = lower(email)),
  verified_by uuid not null references auth.users(id),
  verified_at timestamptz not null,
  revoked_at timestamptz,
  created_at timestamptz not null default now(),
  unique (organization_id, email)
);

create index trusted_beneficiaries_active_idx
  on public.trusted_beneficiaries(organization_id, lower(email))
  where revoked_at is null;

create table public.trade_documents (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  trade_case_id uuid not null references public.trade_cases(id) on delete cascade,
  storage_bucket text not null default 'trade-documents',
  storage_path text not null,
  media_type text not null,
  sha256 char(64) not null check (sha256 ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now(),
  unique (storage_bucket, storage_path)
);

create index trade_documents_case_idx on public.trade_documents(organization_id, trade_case_id);

create table public.classification_cache (
  id uuid primary key default gen_random_uuid(),
  query_hash char(64) not null unique check (query_hash ~ '^[0-9a-f]{64}$'),
  embedding extensions.vector(768) not null,
  hs_code text not null check (hs_code ~ '^[0-9]{6,10}$'),
  confidence numeric(5, 4) not null check (confidence between 0 and 1),
  rationale text not null,
  source_version text not null,
  embedding_model text not null,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null
);

create index classification_cache_embedding_idx
  on public.classification_cache using hnsw (embedding extensions.vector_cosine_ops);
create index classification_cache_expiry_idx on public.classification_cache(expires_at);

create function public.match_classification_cache(
  query_embedding extensions.vector(768),
  match_threshold real default 0.92,
  match_count integer default 5,
  requested_source_version text default null,
  requested_embedding_model text default null
)
returns table (hs_code text, confidence numeric, rationale text, similarity real)
language sql
stable
security invoker
set search_path = ''
as $$
  select cache.hs_code,
         cache.confidence,
         cache.rationale,
         (1 - (cache.embedding <=> query_embedding))::real as similarity
  from public.classification_cache cache
  where cache.expires_at > now()
    and (requested_source_version is null or cache.source_version = requested_source_version)
    and (requested_embedding_model is null or cache.embedding_model = requested_embedding_model)
    and 1 - (cache.embedding <=> query_embedding) >= match_threshold
  order by cache.embedding <=> query_embedding
  limit greatest(1, least(match_count, 20));
$$;

create function public.match_tariff_rules(
  query_embedding extensions.vector(768),
  target_organization_id uuid,
  target_origin_country char(2),
  target_destination_country char(2),
  match_count integer default 5,
  match_threshold real default 0.75,
  requested_embedding_model text default null
)
returns table (
  id uuid,
  agreement text,
  hs_code_prefix text,
  rule_type public.roo_rule_type,
  similarity real
)
language sql
stable
security invoker
set search_path = ''
as $$
  select rule.id,
         rule.agreement,
         rule.hs_code_prefix,
         rule.rule_type,
         (1 - (rule.embedding <=> query_embedding))::real as similarity
  from public.tariff_rules rule
  where rule.embedding is not null
    and (rule.organization_id is null or rule.organization_id = target_organization_id)
    and rule.origin_country = target_origin_country
    and rule.destination_country = target_destination_country
    and rule.effective_from <= current_date
    and (rule.effective_to is null or rule.effective_to >= current_date)
    and (requested_embedding_model is null or rule.embedding_model = requested_embedding_model)
    and 1 - (rule.embedding <=> query_embedding) >= match_threshold
  order by rule.embedding <=> query_embedding
  limit greatest(1, least(match_count, 20));
$$;

create table public.agent_events (
  id bigint generated always as identity primary key,
  organization_id uuid not null references public.organizations(id) on delete cascade,
  trade_case_id uuid not null references public.trade_cases(id) on delete cascade,
  stage text not null check (stage in ('observe', 'decide', 'execute', 'record')),
  event_type text not null,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index agent_events_case_idx on public.agent_events(organization_id, trade_case_id, created_at);

create table public.webhook_events (
  id uuid primary key default gen_random_uuid(),
  provider text not null check (provider in ('paypal', 'n8n')),
  event_id text not null,
  signature_verified boolean not null,
  payload_sha256 char(64) not null check (payload_sha256 ~ '^[0-9a-f]{64}$'),
  processed_at timestamptz,
  created_at timestamptz not null default now(),
  unique (provider, event_id)
);

insert into storage.buckets (id, name, public)
values ('trade-documents', 'trade-documents', false)
on conflict (id) do update set public = false;

create function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger tariff_rules_set_updated_at
  before update on public.tariff_rules
  for each row execute function public.set_updated_at();
create trigger trade_cases_set_updated_at
  before update on public.trade_cases
  for each row execute function public.set_updated_at();

alter table public.organizations enable row level security;
alter table public.organization_memberships enable row level security;
alter table public.tariff_rules enable row level security;
alter table public.trade_cases enable row level security;
alter table public.trusted_beneficiaries enable row level security;
alter table public.trade_documents enable row level security;
alter table public.classification_cache enable row level security;
alter table public.agent_events enable row level security;
alter table public.webhook_events enable row level security;

create policy "Members can read their organizations"
  on public.organizations for select
  using (public.is_organization_member(id));
create policy "Members can read organization memberships"
  on public.organization_memberships for select
  using (public.is_organization_member(organization_id));
create policy "Members can read applicable tariff rules"
  on public.tariff_rules for select
  using (organization_id is null or public.is_organization_member(organization_id));
create policy "Members can read their trade cases"
  on public.trade_cases for select
  using (public.is_organization_member(organization_id));
create policy "Members can read trusted beneficiaries"
  on public.trusted_beneficiaries for select
  using (public.is_organization_member(organization_id));
create policy "Members can read trade documents"
  on public.trade_documents for select
  using (public.is_organization_member(organization_id));
create policy "Members can read agent events"
  on public.agent_events for select
  using (public.is_organization_member(organization_id));

revoke all on public.webhook_events from anon, authenticated;
revoke all on public.classification_cache from anon, authenticated;
grant select on public.classification_cache to service_role;
grant insert, update, delete on public.classification_cache to service_role;
grant select, insert, update, delete on public.webhook_events to service_role;
grant select, insert on public.agent_events to service_role;
grant select, insert, update on public.trade_cases to service_role;
grant select, insert on public.trade_documents to service_role;
grant select on public.tariff_rules to service_role;
grant execute on function public.match_classification_cache(
  extensions.vector, real, integer, text, text
) to service_role;
grant execute on function public.match_tariff_rules(
  extensions.vector, uuid, char, char, integer, real, text
) to service_role;
grant select on public.organizations, public.organization_memberships,
  public.trade_cases, public.trusted_beneficiaries, public.trade_documents,
  public.agent_events, public.tariff_rules to authenticated;
grant select on public.organizations, public.organization_memberships,
  public.trusted_beneficiaries to service_role;
