-- Brightpan demo schema. Idempotent: safe to re-run.
-- RLS is enabled with no policies, so only the service role (n8n, scripts) can read or write.

create extension if not exists vector with schema extensions;

-- Help center: one row per article (BUILD_SPEC step 2)
create table if not exists public.kb_chunks (
  id          bigserial primary key,
  article_id  text not null unique,
  title       text not null,
  content     text not null,
  metadata    jsonb not null default '{}'::jsonb,   -- {article_id, title}; lets match_kb_chunks filter by metadata
  embedding   extensions.vector(1536) not null,     -- OpenAI text-embedding-3-small
  updated_at  timestamptz not null default now()
);

-- Called over PostgREST (/rest/v1/rpc/match_kb_chunks) by the search_help_center n8n workflow.
-- The (query_embedding, match_count, filter) signature is also the LangChain/n8n vector-store convention.
create or replace function public.match_kb_chunks(
  query_embedding extensions.vector(1536),
  match_count     int   default 4,
  filter          jsonb default '{}'::jsonb
)
returns table (id bigint, article_id text, title text, content text, metadata jsonb, similarity float)
language sql stable
set search_path = public, extensions
as $$
  select k.id, k.article_id, k.title, k.content, k.metadata,
         1 - (k.embedding <=> query_embedding) as similarity
  from public.kb_chunks k
  where k.metadata @> filter
  order by k.embedding <=> query_embedding
  limit match_count;
$$;

-- Every chat turn (BUILD_SPEC architecture)
create table if not exists public.conversations (
  id                bigserial primary key,
  session_id        text not null,
  "timestamp"       timestamptz not null default now(),
  user_message      text not null,
  tools_called      text[] not null default '{}',
  article_ids_used  text[] not null default '{}',
  answer            text,
  escalated         boolean not null default false,
  latency_ms        integer,
  error             text                              -- set by the workflow's error branch
);
-- Added for the eval: articles retrieved vs cited, and which model answered
alter table public.conversations add column if not exists article_ids_retrieved text[] not null default '{}';
alter table public.conversations add column if not exists model text;
create index if not exists conversations_session_idx on public.conversations (session_id);

-- Escalations to a human (escalate_to_human tool)
create table if not exists public.handoffs (
  id              bigserial primary key,
  created_at      timestamptz not null default now(),
  session_id      text,
  reason          text not null,
  summary         text not null,
  customer_email  text,
  order_number    text
);
-- true when the customer's email matched the order in Shopify at hand-off time
alter table public.handoffs add column if not exists verified boolean not null default false;

alter table public.kb_chunks     enable row level security;
alter table public.conversations enable row level security;
alter table public.handoffs      enable row level security;

-- Order-lookup attempt limiting (lookup_order tool). The order number + email pair is the only proof
-- of ownership, so failed guesses are capped per conversation, order number, email and globally.
create table if not exists public.lookup_attempts (
  id      bigserial primary key,
  key     text not null,                      -- 's:<session>', 'o:<order>', 'e:<email>' or 'g'
  at      timestamptz not null default now(),
  failed  boolean                             -- null while in flight, true = no match, false = matched
);
create index if not exists lookup_attempts_key_at_idx on public.lookup_attempts (key, at);
alter table public.lookup_attempts enable row level security;

-- Atomically reserve one attempt per key. Keys are locked in sorted order for the rest of the
-- transaction, so concurrent requests can't both pass the check. Failed and in-flight attempts count;
-- matched attempts don't. Soft keys (the global failure counter) never block; when one is over its
-- limit, hard keys switch to their stricter limits (under_attack = true). A hard key at its limit
-- returns locked = true and reserves nothing.
drop function if exists public.begin_lookup(text[], int[], int[]);
drop function if exists public.begin_lookup(text[], int[], int[], boolean[]);
create or replace function public.begin_lookup(
  keys text[], limits int[], windows_s int[], hard boolean[], strict_limits int[]
)
returns jsonb
language plpgsql
set search_path = public
as $$
declare
  i int;
  n int;
  k text;
  counts int[] := '{}';
  under_attack boolean := false;
  ids bigint[] := '{}';
  new_id bigint;
begin
  for k in select x from unnest(keys) x order by x loop
    perform pg_advisory_xact_lock(hashtextextended(k, 0));
  end loop;
  for i in 1 .. coalesce(array_length(keys, 1), 0) loop
    select count(*) into n from public.lookup_attempts
     where key = keys[i] and at > now() - make_interval(secs => windows_s[i]) and (failed is null or failed);
    counts := counts || n;
    if not hard[i] and n >= limits[i] then
      under_attack := true;
    end if;
  end loop;
  for i in 1 .. coalesce(array_length(keys, 1), 0) loop
    if hard[i] and counts[i] >= (case when under_attack then strict_limits[i] else limits[i] end) then
      return jsonb_build_object('locked', true, 'under_attack', under_attack, 'attempt_ids', '[]'::jsonb);
    end if;
  end loop;
  for i in 1 .. coalesce(array_length(keys, 1), 0) loop
    insert into public.lookup_attempts (key) values (keys[i]) returning id into new_id;
    ids := ids || new_id;
  end loop;
  delete from public.lookup_attempts where at < now() - interval '1 day';
  return jsonb_build_object('locked', false, 'under_attack', under_attack, 'attempt_ids', to_jsonb(ids));
end;
$$;

create or replace function public.finish_lookup(attempt_ids bigint[], matched boolean)
returns void
language sql
set search_path = public
as $$
  update public.lookup_attempts set failed = not matched where id = any(attempt_ids);
$$;

revoke execute on function public.begin_lookup(text[], int[], int[], boolean[], int[]) from public, anon, authenticated;
revoke execute on function public.finish_lookup(bigint[], boolean) from public, anon, authenticated;
grant execute on function public.begin_lookup(text[], int[], int[], boolean[], int[]) to service_role;
grant execute on function public.finish_lookup(bigint[], boolean) to service_role;
