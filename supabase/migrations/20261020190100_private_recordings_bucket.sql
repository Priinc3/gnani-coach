-- Phase 06 (G1): the private recordings bucket.
--
-- The bucket is **private**: ``public = false``. A stored URL would be a
-- shareable capability, so the bucket publishes nothing: no public URL
-- is created, stored or returned by any route.
--
-- The object key is ``<user id>/<recording id>``. The owner-scoped
-- policies below use the first path segment, which is the signed-in
-- user's own id, so a user can only reach the objects in their own
-- folder. There is **no policy for the ``anon`` role**, and no policy
-- uses ``using (true)``.
--
-- The Python service reaches the bucket with the service-role key, which
-- bypasses row-level security, so the service enforces ownership in its
-- own queries. These policies protect the direct-from-the-browser path.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
    'recordings',
    'recordings',
    false,
    10485760,
    array['audio/wav']
)
on conflict (id) do update
    set public = excluded.public,
        file_size_limit = excluded.file_size_limit,
        allowed_mime_types = excluded.allowed_mime_types;

create policy "recordings_owner_insert"
    on storage.objects
    for insert
    to authenticated
    with check (
        bucket_id = 'recordings'
        and (storage.foldername(name))[1] = auth.uid()::text
    );

create policy "recordings_owner_select"
    on storage.objects
    for select
    to authenticated
    using (
        bucket_id = 'recordings'
        and (storage.foldername(name))[1] = auth.uid()::text
    );

create policy "recordings_owner_update"
    on storage.objects
    for update
    to authenticated
    using (
        bucket_id = 'recordings'
        and (storage.foldername(name))[1] = auth.uid()::text
    )
    with check (
        bucket_id = 'recordings'
        and (storage.foldername(name))[1] = auth.uid()::text
    );

create policy "recordings_owner_delete"
    on storage.objects
    for delete
    to authenticated
    using (
        bucket_id = 'recordings'
        and (storage.foldername(name))[1] = auth.uid()::text
    );
