-- Phase 06 (G1): the schedule of the expiry cleanup.
--
-- **How the cleanup is scheduled.** Supabase runs ``pg_cron``, the
-- PostgreSQL job scheduler, in every project. This migration enables the
-- extension and registers one job:
--
-- * job name: ``purge-expired-recordings``
-- * schedule:  ``17 3 * * *`` — every day at 03:17 UTC
-- * command:   ``select public.purge_expired_recordings();``
--
-- 03:17 UTC is an off-peak minute in the region the project runs in, and
-- it is not on the hour, so the job does not pile up with every other
-- scheduled job in the fleet.
--
-- The job is idempotent: the migration unschedules a job with the same
-- name before it schedules the new one, so it can be applied twice
-- without creating two jobs.
--
-- The extension and the ``cron`` schema are Supabase-managed. This
-- migration is therefore the one file that cannot be applied to a plain
-- PostgreSQL server; everything else in ``supabase/migrations`` can.

create extension if not exists pg_cron with schema extensions;

select cron.unschedule(jobid)
  from cron.job
 where jobname = 'purge-expired-recordings';

select cron.schedule(
    'purge-expired-recordings',
    '17 3 * * *',
    $$select public.purge_expired_recordings();$$
);
