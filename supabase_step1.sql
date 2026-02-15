-- Server Vibe MVP: Supabase Step 1 Setup
-- Run in Supabase SQL Editor

-- 0) Optional extension for gen_random_uuid() (usually already enabled)
create extension if not exists pgcrypto;

-- 1) commands table
create table if not exists public.commands (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  command_text text not null,
  status text not null default 'pending'
    check (status in ('pending','processing','completed','error')),
  response_log text,
  image_url text,
  created_at timestamptz not null default now()
);

-- 2) Helpful indexes
create index if not exists idx_commands_user_created_at
  on public.commands (user_id, created_at desc);

create index if not exists idx_commands_status_created_at
  on public.commands (status, created_at desc);

-- 3) Enable Row Level Security
alter table public.commands enable row level security;

-- 4) RLS policies
-- Users can insert their own commands
create policy if not exists "Users can insert own commands"
  on public.commands
  for insert
  to authenticated
  with check (auth.uid() = user_id);

-- Users can read their own commands
create policy if not exists "Users can read own commands"
  on public.commands
  for select
  to authenticated
  using (auth.uid() = user_id);

-- Users can update their own commands (optional, useful for client-side edits)
create policy if not exists "Users can update own commands"
  on public.commands
  for update
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- Service role bypasses RLS automatically.
-- If your Python agent uses anon/authenticated key instead of service role,
-- create a dedicated DB role + tighter policy instead of broad public update rules.

-- 5) Realtime: include table in supabase_realtime publication
do $$
begin
  if not exists (
    select 1
    from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'commands'
  ) then
    alter publication supabase_realtime add table public.commands;
  end if;
end $$;

-- 6) Storage bucket for screenshots
insert into storage.buckets (id, name, public)
values ('screenshots', 'screenshots', true)
on conflict (id) do nothing;

-- 7) Storage policies
-- Read access for screenshot URLs
create policy if not exists "Public can read screenshots"
  on storage.objects
  for select
  to public
  using (bucket_id = 'screenshots');

-- Authenticated users can upload to screenshots/{user_id}/...
create policy if not exists "Users can upload own screenshots"
  on storage.objects
  for insert
  to authenticated
  with check (
    bucket_id = 'screenshots'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

-- Authenticated users can update/delete their own screenshots
create policy if not exists "Users can update own screenshots"
  on storage.objects
  for update
  to authenticated
  using (
    bucket_id = 'screenshots'
    and (storage.foldername(name))[1] = auth.uid()::text
  )
  with check (
    bucket_id = 'screenshots'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

create policy if not exists "Users can delete own screenshots"
  on storage.objects
  for delete
  to authenticated
  using (
    bucket_id = 'screenshots'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

-- 8) Optional trigger to keep updated_at (if you add the column later)
-- alter table public.commands add column if not exists updated_at timestamptz not null default now();
-- create or replace function public.set_updated_at()
-- returns trigger as $$
-- begin
--   new.updated_at = now();
--   return new;
-- end;
-- $$ language plpgsql;
-- drop trigger if exists trg_commands_updated_at on public.commands;
-- create trigger trg_commands_updated_at
-- before update on public.commands
-- for each row execute function public.set_updated_at();
