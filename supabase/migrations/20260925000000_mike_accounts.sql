-- Mike accounts: a profile per person, a private avatar, and self-service
-- account deletion.
--
-- Run once in your Supabase project (SQL editor, or `supabase db push`).
-- Everything here is scoped to the signed-in person by row-level security:
-- nobody — not even another signed-in user — can read or change anyone
-- else's profile or photo. Mike's conversations, files and memory are never
-- stored here; they stay on the user's computer.

-- ── Profiles ────────────────────────────────────────────────────────────

create table if not exists public.profiles (
  id           uuid primary key references auth.users (id) on delete cascade,
  display_name text check (char_length(display_name) <= 80),
  avatar_path  text check (char_length(avatar_path) <= 200),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

comment on table public.profiles is
  'One row per Mike account: the name Mike calls you and your photo. Nothing else.';

alter table public.profiles enable row level security;

drop policy if exists "Own profile: read" on public.profiles;
create policy "Own profile: read" on public.profiles
  for select to authenticated
  using ((select auth.uid()) = id);

drop policy if exists "Own profile: create" on public.profiles;
create policy "Own profile: create" on public.profiles
  for insert to authenticated
  with check ((select auth.uid()) = id);

drop policy if exists "Own profile: update" on public.profiles;
create policy "Own profile: update" on public.profiles
  for update to authenticated
  using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

grant select, insert, update on public.profiles to authenticated;
revoke all on public.profiles from anon;

create or replace function public.touch_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists profiles_touch_updated_at on public.profiles;
create trigger profiles_touch_updated_at
  before update on public.profiles
  for each row execute function public.touch_updated_at();

-- A profile exists from the moment someone signs up, named from what they
-- typed (email sign-up) or what their Google account says.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, display_name)
  values (
    new.id,
    nullif(left(trim(coalesce(
      new.raw_user_meta_data ->> 'display_name',
      new.raw_user_meta_data ->> 'full_name',
      new.raw_user_meta_data ->> 'name',
      ''
    )), 80), '')
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ── Avatars ─────────────────────────────────────────────────────────────
-- A private bucket: a photo is readable only by the person it belongs to.
-- Each person writes only inside their own folder, avatars/<user id>/.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('avatars', 'avatars', false, 2097152, array['image/png', 'image/jpeg', 'image/webp'])
on conflict (id) do update
  set public = excluded.public,
      file_size_limit = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "Own avatar: read" on storage.objects;
create policy "Own avatar: read" on storage.objects
  for select to authenticated
  using (bucket_id = 'avatars' and (storage.foldername(name))[1] = (select auth.uid())::text);

drop policy if exists "Own avatar: upload" on storage.objects;
create policy "Own avatar: upload" on storage.objects
  for insert to authenticated
  with check (bucket_id = 'avatars' and (storage.foldername(name))[1] = (select auth.uid())::text);

drop policy if exists "Own avatar: replace" on storage.objects;
create policy "Own avatar: replace" on storage.objects
  for update to authenticated
  using (bucket_id = 'avatars' and (storage.foldername(name))[1] = (select auth.uid())::text)
  with check (bucket_id = 'avatars' and (storage.foldername(name))[1] = (select auth.uid())::text);

drop policy if exists "Own avatar: remove" on storage.objects;
create policy "Own avatar: remove" on storage.objects
  for delete to authenticated
  using (bucket_id = 'avatars' and (storage.foldername(name))[1] = (select auth.uid())::text);

-- ── Deleting an account ─────────────────────────────────────────────────
-- Signed-in people can delete their own account — and only their own. The
-- app removes the photo through the Storage API first (Supabase doesn't
-- allow deleting storage files from SQL); deleting the auth user then
-- cascades to the profile, sessions and sign-in identities.

create or replace function public.delete_account()
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  uid uuid := auth.uid();
begin
  if uid is null then
    raise exception 'Not signed in' using errcode = '42501';
  end if;
  delete from auth.users where id = uid;
end;
$$;

revoke execute on function public.delete_account() from public, anon;
grant execute on function public.delete_account() to authenticated;
