# FlashTrend (flashtrend-bot)

A statistical-semantic filter that runs once or twice a day on GitHub Actions: it reads YouTube metadata
through the official API, keeps the videos that beat **their own channel's** usual performance, merges
duplicate ideas, asks Gemini for a remake angle, and writes the digest to **Supabase**. The sister project
**estfstudio** reads that digest from the same Supabase project.

Not a re-upload bot: no video is downloaded; only metadata is read.

Design docs (Vietnamese, Archify HTML): <https://trion-org.github.io/flashtrend-bot/> · sources in
`tools/docs/`, built with `tools/docs/build.sh`.

## Time zone

**Vietnam time only** (UTC+7, no daylight saving). Every timestamp the bot creates, logs, serialises or
stores is `+07:00`; run ids are `run_YYYYMMDDTHHMMSS` in Vietnam time; the database is set to
`Asia/Ho_Chi_Minh`. The one exception GitHub forces on us: cron expressions are UTC, so `17 0 * * *` is
written in the workflow and means **07:17 Vietnam time**.

## Pipeline

```
YouTube (chart + keywords + channel baselines)
  → L1 Z-Score of views / channel_avg_views, Bayes engagement, time decay  → viral_score
  → L2 MiniLM embeddings, greedy cosine clusters (τ = 0.70), 90-day history (0.80)
  → L3 Gemini → ideas.llm (summary, why_viral, hook, 3 angles, format, risk)
  → Supabase: runs · channels · videos · snapshots · candidates · embeddings · ideas · media
```

`runs.status = 'ok'` only when every idea has a schema-valid `llm`. If anything fails after L2 the
candidates and ideas are kept with `llm = null` and the run is `error` (estfstudio reads only `ok` runs).

## Setup

1. Supabase (Free, Singapore): run `sql/01_core.sql`, `02_media.sql`, `03_functions.sql`,
   `04_seed_app_config.sql` in the SQL Editor, in that order.
2. Four secrets (GitHub → Settings → Secrets, or a local `.env`): `SUPABASE_URL`,
   `SUPABASE_SERVICE_ROLE_KEY`, `YOUTUBE_API_KEY`, `GEMINI_API_KEY` — see `.env.example`.
3. First run: Actions → **FlashTrend digest** → Run workflow with `dry_run` ticked.

```bash
uv sync --extra dev --extra chart        # tests need no torch
uv sync --extra embed                    # + sentence-transformers (install CPU-only torch first)
uv run python main.py run --dry-run --output-dir output
uv run python main.py run                # writes to Supabase
uv run python main.py check-media        # weekly in CI: HEAD every media URL
uv run pytest -q                         # unit + architecture tests
tests/integration/run.sh                 # SupabaseStore vs real Postgres+pgvector+PostgREST (Docker)
```

Exit codes: `0` ok (or a dry run), `1` the run ended in `error`, `2` configuration error.

## Layout (Clean Architecture, enforced by `tests/architecture`)

```
domain/          models, scoring, dedup, llm_contract, clock — stdlib only, no I/O
application/     digest (RunDigest), check_media, ports (Protocols)
infrastructure/  youtube_api · supabase_store · gemini · embedder · image_host · chart · settings
presentation/    cli · log · output
composition_root.py   the only place adapters are wired into use cases
sql/             schema, functions (cosine search, TTL cleanup), seed
```

## Rules worth knowing

- Secrets live only in GitHub Secrets / `.env`; the service-role key is used on Actions only, and the log
  observer masks every secret value.
- Ideas keep `status = 'new'` until estfstudio changes it; the bot never resets it (plain `insert`).
- Image upload failures never fail a run (docs page 07); the endpoint is unofficial and unconfirmed.
- v2 (source fetching, transformation, YouTube upload) is design only, see docs page 09.
