-- Run once in the Supabase SQL Editor. The 384 dimensions match all-MiniLM-L6-v2.
create extension if not exists vector with schema extensions;

create table if not exists public.documents (
  id text primary key,
  name text not null,
  file_type text not null,
  size_bytes bigint not null default 0,
  created_at timestamptz not null default now()
);

create table if not exists public.document_chunks (
  id bigserial primary key,
  document_id text not null references public.documents(id) on delete cascade,
  content text not null,
  page integer,
  embedding extensions.vector(384) not null
);

create index if not exists document_chunks_embedding_idx
  on public.document_chunks using hnsw (embedding extensions.vector_cosine_ops);
create index if not exists document_chunks_document_id_idx
  on public.document_chunks(document_id);
