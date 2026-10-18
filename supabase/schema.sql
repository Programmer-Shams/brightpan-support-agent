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
