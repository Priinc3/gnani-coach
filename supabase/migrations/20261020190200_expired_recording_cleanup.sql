-- Phase 06 (G1): the expiry cleanup.
--
-- A retained recording lives for 30 days. The expiry is written as
-- ``expires_at`` on the row when the recording is saved, and this
-- function is what removes it when the time comes.
--
-- The function is deliberately a **function**, not an inline command, so
-- that:
--
-- * the scheduling migration (``..._schedule.sql``) only has to schedule
--   one statement, and
-- * the cleanup can be run by hand, and tested, without a scheduler.
--
-- The function is ``security definer`` because the storage objects live
-- in the ``storage`` schema, whose row-level security the ``postgres``
-- role bypasses and the ``authenticated`` role does not. The execute
-- privilege is taken away from ``public`` and given to the service role
-- only, so an ordinary signed-in user cannot run the cleanup.

create or replace function public.purge_expired_recordings()
    returns void
    language plpgsql
    security definer
    set search_path = public, storage
as $$
begin
    update public.recordings
       set state = 'deleted',
           deleted_at = expires_at
     where expires_at <= now()
       and state = 'retained';

    delete from storage.objects
     where bucket_id = 'recordings'
       and (storage.foldername(name))[1] in (
           select user_id::text
             from public.recordings
            where expires_at <= now()
       );
end;
$$;

revoke execute on function public.purge_expired_recordings() from public;
revoke execute on function public.purge_expired_recordings() from anon;
revoke execute on function public.purge_expired_recordings() from authenticated;
grant execute on function public.purge_expired_recordings() to service_role;
