-- Server-side helpers the bot calls through PostgREST RPC (docs/03: heavy work stays in the database,
-- no vector is pulled to the client). Run after 02_media.sql.
-- Only service_role may execute them: RLS does not protect functions, so revoke the defaults.

-- C3: highest cosine similarity between a query vector and embeddings updated in the last p_days days,
-- ignoring the videos of the current run. NULL when there is no history yet.
-- A sequential scan is intentional: with HNSW, post-filtering the excluded ids could hide the true neighbour.
create or replace function flashtrend_max_cosine(query text, p_days int, exclude_ids text[])
returns double precision
language sql
stable
set search_path = public, extensions
as $$
  select max(1 - (e.embedding <=> query::vector(384)))
  from embeddings e
  where e.updated_at >= now() - make_interval(days => p_days)
    and not (e.video_id = any(exclude_ids));
$$;

-- w7: TTL cleanup. estf_* tables are estfstudio's and are never touched here.
create or replace function flashtrend_cleanup(p_ttl_days int, p_embeddings_ttl_days int)
returns jsonb
language plpgsql
set search_path = public
as $$
declare
  n_snapshots int;
  n_candidates int;
  n_embeddings int;
  n_videos int;
  n_hot int := 0;
  n_charts int := 0;
begin
  delete from snapshots where expire_at < now();
  get diagnostics n_snapshots = row_count;

  delete from candidates where expire_at < now();
  get diagnostics n_candidates = row_count;

  delete from embeddings
   where updated_at < now() - make_interval(days => p_embeddings_ttl_days);
  get diagnostics n_embeddings = row_count;

  -- hot lists and analysis charts are only useful while fresh: they expire with the snapshots.
  -- Guarded: a database that has not run 07_analysis.sql yet has neither the table nor the enum value.
  begin
    delete from hot_videos where created_at < now() - make_interval(days => p_ttl_days);
    get diagnostics n_hot = row_count;
  exception when undefined_table then
    n_hot := 0;
  end;
  delete from media
   where kind::text = 'analysis'
     and created_at < now() - make_interval(days => p_ttl_days);
  get diagnostics n_charts = row_count;

  -- orphan videos: not seen for p_ttl_days and referenced by nothing (ideas are kept ~1 year)
  delete from videos v
   where v.last_seen_at < now() - make_interval(days => p_ttl_days)
     and not exists (select 1 from ideas i where i.video_id = v.id)
     and not exists (select 1 from snapshots s where s.video_id = v.id)
     and not exists (select 1 from candidates c where c.video_id = v.id)
     and not exists (select 1 from embeddings e where e.video_id = v.id)
     and not exists (select 1 from media m where m.video_id = v.id);
  get diagnostics n_videos = row_count;

  return jsonb_build_object(
    'snapshots', n_snapshots,
    'candidates', n_candidates,
    'embeddings', n_embeddings,
    'videos', n_videos,
    'hot_videos', n_hot,
    'analysis_charts', n_charts
  );
end;
$$;

-- Budget guard: the bot logs this and warns at 350 MB, stops writing candidates at 450 MB.
create or replace function flashtrend_db_size()
returns bigint
language sql
stable
as $$ select pg_database_size(current_database()); $$;

revoke execute on function flashtrend_max_cosine(text, int, text[]) from public, anon, authenticated;
revoke execute on function flashtrend_cleanup(int, int) from public, anon, authenticated;
revoke execute on function flashtrend_db_size() from public, anon, authenticated;
grant execute on function flashtrend_max_cosine(text, int, text[]) to service_role;
grant execute on function flashtrend_cleanup(int, int) to service_role;
grant execute on function flashtrend_db_size() to service_role;
