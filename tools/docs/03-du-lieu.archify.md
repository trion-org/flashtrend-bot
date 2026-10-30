# Dữ liệu nằm ở đâu trong Supabase và có vượt gói Free không? {#du-lieu}

Mọi thứ nằm trong **một project Supabase dùng chung với estfstudio**: FlashTrend là writer duy nhất của `runs`, `candidates`, `ideas`; estfstudio chỉ ghi `feedback` và `ideas.status`. Với TTL 90 ngày, ước tính dùng khoảng **230 MB / 500 MB** database và dưới 0,3 GB / 5 GB egress mỗi tháng.

- Z-Score phụ thuộc cohort nên chỉ sống ở `candidates` (mỗi run một hàng), không ở `videos`.[](source:idea)
- Embedding tách bảng riêng và chiếm phần lớn dung lượng: TTL của nó quyết định quota.
- Ảnh không nằm trong Supabase: bảng `media` chỉ giữ URL trên image host và `sha256`.
- Free tạm dừng project sau 1 tuần không hoạt động; cron 1–2 lần/ngày giữ nó sống.[](source:pricing)

@answer scope="Schema v1 từ bản thiết kế + bảng media mới · dung lượng là ước tính cho ~300 video mới/ngày, 2 run/ngày"
@meta locale=vi
@source idea title="Bản thiết kế FlashTrend (2026-10-28) — §4 Data Model"
@source pricing title="Supabase pricing — Free plan" url=https://supabase.com/pricing
@source pgsize title="PostgreSQL — database object size functions" url=https://www.postgresql.org/docs/current/functions-admin.html#FUNCTIONS-ADMIN-DBOBJECT

## Các bảng liên quan với nhau thế nào? {#erd span=12}

@erd id=schema-v1 title="Schema FlashTrend v1 (lõi digest)"
| entity videos | videos |
| entity runs | runs |
| entity ideas | ideas |
| videos.id | text | pk |
| runs.id | text | pk |
| ideas.run_id | text | pk,fk | runs.id |
| ideas.video_id | text | pk,fk | videos.id |
| ideas > runs | many:one | digest |
| ideas > videos | many:one | leader |

`candidates` (điểm L1 của mọi video trong cohort, cùng khoá `(run_id, video_id)` như `ideas`), `channels` (baseline kênh, cache 24 giờ), `embeddings` (vector 384 chiều, 1:1 với `videos`), `snapshots` (một điểm views mỗi video mỗi run, khoá `(video_id, run_id)`) và `feedback` (một nhãn mỗi idea, khoá trùng `ideas`) không vẽ để sơ đồ dễ đọc; `media` có panel riêng bên dưới. `app_config` (1 hàng, `id = 1`) giữ ngưỡng θ, τ, λ và từ khoá; không có khoá ngoại. `publish_jobs` (v2) chưa tạo ở MVP. DDL đầy đủ ở mục bên dưới.

## Mọi quan hệ và hành vi khi xoá {#quan-he}

Field từng bảng, mục đích và dữ liệu mẫu nằm ở trang 04 (bảng thu thập), 05 (bảng điểm) và 06 (bảng mở rộng, enum).

| Cha → con | Bản số | ON DELETE | Ý nghĩa |
| --- | --- | --- | --- |
| `channels` → `videos` | 1 : N | RESTRICT | Video thuộc đúng một kênh; cache baseline A3 |
| `channels` → `candidates` | 1 : N | RESTRICT | Sao chép `channel_avg_views` vào điểm L1 |
| `channels` → `ideas` | 1 : N | RESTRICT | Sao chép `channel_title` để estfstudio không join |
| `videos` → `snapshots` | 1 : N | RESTRICT | Chuỗi thời gian views/likes/comments (B4) |
| `runs` → `snapshots` | 1 : N | RESTRICT | Mỗi run ghi một điểm cho mỗi video |
| `runs` → `candidates` | 1 : N | CASCADE {caution:Xoá theo} | Xoá run thì xoá toàn bộ Z của cohort đó |
| `videos` → `candidates` | 1 : N | RESTRICT | Cùng video có một hàng mỗi run |
| `runs` → `ideas` | 1 : N | CASCADE {caution:Xoá theo} | Xoá run thì xoá digest của nó |
| `videos` → `ideas` | 1 : N | RESTRICT | Chỉ leader của cụm được insert |
| `videos` → `embeddings` | 1 : 1 | RESTRICT | Vector mới nhất; C3 so với 90 ngày |
| `ideas` → `feedback` | 1 : 0..1 | RESTRICT | Nhãn Precision@5, khoá trùng `(run_id, video_id)` |
| `ideas` → `publish_jobs` | 1 : N | RESTRICT | v2: nhiều lần thử upload / hẹn lịch |
| `videos` → `media` | 1 : N | RESTRICT | Thumbnail, ảnh bìa của video |
| `runs` → `media` | 1 : N | SET NULL | Biểu đồ của run; xoá run vẫn giữ link ảnh |
| `ideas` → `estf_posts` | 1 : N | SET NULL | Bài estfstudio đăng từ một idea |
| `media` → `estf_posts` | 1 : N | RESTRICT | Ảnh bìa của từng phần |

`app_config` không có khoá ngoại; `videos.last_run_id` chỉ là tham chiếu logic tới `runs.id` (không FK, tránh vòng khi insert).

## Vì sao Postgres, và đặt ID thế nào? {#nguyen-tac}

| Quyết định | Nội dung |
| --- | --- |
| Dùng của Supabase | Postgres, pgvector, SQL Editor |
| Không dùng | Auth, Realtime, Storage, Edge Functions (trùng vai trò GitHub Actions) |
| Host thay thế cùng schema | Neon hoặc Postgres bất kỳ có pgvector |
| Vì sao không JSON trong git | L1 là thống kê cohort (`AVG`, `STDDEV`), L2 là cosine vector, B4 là chuỗi thời gian; JSON trong git gây conflict, lộ dữ liệu trên repo public và không truy vấn được |
| ID video / kênh | `{platform}_{native_id}`: `yt_9bZkp7q19f0`, `bi_BV1xx411c7M2`, `yt_UC_pythonlab` |
| ID run | `run_` + giờ VN `YYYYMMDDTHHMMSS`, ví dụ `run_20261028T071700` (sắp xếp được) |
| ID cụm | `{run_id}_c{n}`, ví dụ `run_20261028T071700_c0` |
| Z-Score | Chỉ ở `candidates` (phụ thuộc cohort của run) |
| Embedding | Bảng riêng `embeddings`, 1:1 với `videos` |
| Thời gian | Chỉ dùng **giờ Việt Nam** (UTC+7, không có giờ mùa hè): kiểu `timestamptz`, bot ghi ISO-8601 kèm `+07:00`, database đặt `timezone = 'Asia/Ho_Chi_Minh'` |

## DDL đầy đủ của schema v1 {#ddl}

Dán toàn bộ vào SQL Editor của Supabase rồi Run; sau đó chạy DDL `media` ở mục kế tiếp. Không tạo policy nào cho `anon` / `authenticated`: hai backend dùng `service_role` (bỏ qua RLS) từ phía server.

```sql title="Schema v1 — 7 enum, 10 bảng, index, RLS"
-- Chỉ dùng giờ Việt Nam: SQL Editor và now() hiển thị +07
alter database postgres set timezone to 'Asia/Ho_Chi_Minh';

create extension if not exists vector;

create type platform_t as enum (
  'youtube', 'tiktok', 'facebook', 'bilibili', 'douyin'
);
create type run_trigger_t as enum ('schedule', 'workflow_dispatch');
create type run_status_t as enum ('running', 'ok', 'error');
create type idea_status_t as enum ('new', 'seen', 'used', 'rejected');
create type feedback_label_t as enum (
  'useful', 'not_useful', 'duplicate', 'used'
);
create type publish_status_t as enum (
  'queued', 'uploaded', 'scheduled', 'failed'
);
create type privacy_t as enum ('private', 'unlisted', 'public');

create table app_config (
  id smallint primary key default 1 check (id = 1),
  schema_version int not null default 1,
  regions text[] not null default array['VN'],
  keywords text[] not null,
  z_threshold double precision not null default 1.5,
  cosine_threshold double precision not null default 0.70,
  history_cosine_threshold double precision not null default 0.80,
  decay_lambda double precision not null default 0.05,
  engagement_like_w double precision not null default 1.5,
  engagement_comment_w double precision not null default 3.0,
  bayes_c int not null default 1000,
  min_cohort_n int not null default 20,
  snapshot_ttl_days int not null default 90,
  llm_enabled boolean not null default true,
  updated_at timestamptz not null default now()
);

create table channels (
  id text primary key,
  platform platform_t not null,
  native_id text not null,
  title text not null,
  subscriber_count bigint,
  video_count int,
  channel_avg_views double precision not null,
  fetched_at timestamptz not null,
  stale_after timestamptz not null,
  unique (platform, native_id)
);

create table videos (
  id text primary key,
  platform platform_t not null,
  native_id text not null,
  url text not null,
  title text not null,
  description text not null default '',
  published_at timestamptz not null,
  channel_id text not null references channels (id),
  duration_sec int,
  thumbnail_url text,
  last_views bigint not null default 0,
  last_likes bigint not null default 0,
  last_comments bigint not null default 0,
  first_seen_at timestamptz not null,
  last_seen_at timestamptz not null,
  last_run_id text,
  transcript_excerpt text,
  unique (platform, native_id)
);

create table runs (
  id text primary key,
  schema_version int not null default 1,
  trigger run_trigger_t not null,
  git_sha text not null,
  region text not null,
  started_at timestamptz not null,
  finished_at timestamptz,
  status run_status_t not null default 'running',
  error jsonb,
  collected int not null default 0,
  scored int not null default 0,
  outliers int not null default 0,
  ideas_count int not null default 0,
  cohort_n int,
  cohort_mu_ratio double precision,
  cohort_sigma_ratio double precision,
  cohort_median_engagement double precision,
  duration_ms int,
  chart_path text
);

create table snapshots (
  video_id text not null references videos (id),
  run_id text not null references runs (id),
  captured_at timestamptz not null,
  views bigint not null,
  likes bigint not null,
  comments bigint not null,
  expire_at timestamptz not null,
  primary key (video_id, run_id)
);

create table candidates (
  run_id text not null references runs (id) on delete cascade,
  video_id text not null references videos (id),
  platform platform_t not null,
  title text not null,
  url text not null,
  channel_id text not null references channels (id),
  views bigint not null,
  likes bigint not null,
  comments bigint not null,
  age_hours double precision not null,
  channel_avg_views double precision not null,
  performance_ratio double precision not null,
  z_score double precision not null,
  engagement double precision not null,
  time_decay double precision not null,
  velocity double precision,
  acceleration double precision,
  early_flag boolean not null default false,
  viral_score double precision not null,
  passed_z boolean not null,
  query_tag text,
  expire_at timestamptz not null,
  primary key (run_id, video_id)
);

create table ideas (
  run_id text not null references runs (id) on delete cascade,
  video_id text not null references videos (id),
  platform platform_t not null,
  title text not null,
  url text not null,
  published_at timestamptz not null,
  views bigint not null,
  likes bigint not null,
  comments bigint not null,
  channel_title text not null,
  channel_id text not null references channels (id),
  channel_avg_views double precision not null,
  performance_ratio double precision not null,
  z_score double precision not null,
  engagement double precision not null,
  time_decay double precision not null,
  viral_score double precision not null,
  duplicates_count int not null default 0,
  novelty_score double precision,
  cluster_id text not null,
  llm jsonb,
  status idea_status_t not null default 'new',
  created_at timestamptz not null default now(),
  primary key (run_id, video_id)
);

create table embeddings (
  video_id text primary key references videos (id),
  model text not null default 'all-MiniLM-L6-v2',
  dim int not null default 384 check (dim = 384),
  text_hash text not null,
  source text not null check (source in ('title', 'title+transcript')),
  embedding vector(384) not null,
  updated_at timestamptz not null default now()
);

create table feedback (
  run_id text not null,
  video_id text not null,
  label feedback_label_t not null,
  labeled_at timestamptz not null default now(),
  note text,
  primary key (run_id, video_id),
  foreign key (run_id, video_id) references ideas (run_id, video_id)
);

create table publish_jobs (
  id text primary key,
  run_id text not null,
  video_id text not null,
  status publish_status_t not null default 'queued',
  youtube_video_id text,
  publish_at timestamptz,
  privacy_status privacy_t not null default 'private',
  made_for_kids boolean not null,
  error jsonb,
  foreign key (run_id, video_id) references ideas (run_id, video_id)
);

create index snapshots_video_time on snapshots (video_id, captured_at desc);
create index candidates_run_score on candidates (run_id, passed_z, viral_score desc);
create index ideas_run_rank on ideas (run_id, viral_score desc);
create index embeddings_updated on embeddings (updated_at desc);
create index embeddings_hnsw on embeddings
  using hnsw (embedding vector_cosine_ops);

alter table app_config enable row level security;
alter table channels enable row level security;
alter table videos enable row level security;
alter table runs enable row level security;
alter table snapshots enable row level security;
alter table candidates enable row level security;
alter table ideas enable row level security;
alter table embeddings enable row level security;
alter table feedback enable row level security;
alter table publish_jobs enable row level security;
```

```sql title="Cột đề xuất thêm (trang 04): ngưỡng nới khi cohort nhỏ"
alter table app_config add column relaxed_z_threshold double precision not null default 0.5;
alter table runs add column z_threshold_used double precision;
```

Nếu `hnsw` / `vector_cosine_ops` báo lỗi (project cũ): tạm bỏ lệnh `create index embeddings_hnsw` — MVP vẫn tính cosine trong bộ nhớ, index chỉ tăng tốc C3. Nếu `extension "vector" is not available`: Database → Extensions → bật `vector`.

## Bảng media mới lưu gì? {#media}

Mỗi ảnh được upload một lần: `sha256` trùng thì dùng lại URL cũ thay vì upload lại.

```sql title="media — link ảnh trên image host (chạy sau DDL lõi)"
create type media_kind_t as enum ('thumbnail', 'chart', 'cover');

create table media (
  id text primary key,                    -- 'img_' || left(sha256, 16)
  owner text not null check (owner in ('flashtrend', 'estfstudio')),
  kind media_kind_t not null,
  url text not null,                      -- URL công khai do image host trả về
  host text not null default 'nobinobi',
  sha256 text not null unique,
  bytes int not null check (bytes <= 2000000),
  width int,
  height int,
  video_id text references videos (id),
  run_id text references runs (id) on delete set null,
  alive boolean not null default true,    -- false khi HEAD url trả 404
  checked_at timestamptz,
  created_at timestamptz not null default now()
);
create index media_video on media (video_id);
alter table media enable row level security;
alter table runs add column chart_media_id text references media (id);
```

## Ai được đọc, ai được ghi? {#hop-dong}

| Bảng | flashtrend-bot | estfstudio |
| --- | --- | --- |
| `channels`, `videos`, `snapshots`, `candidates`, `embeddings` | Ghi | Không đụng |
| `runs` | Ghi | Đọc (`status = 'ok'`) |
| `ideas` | Ghi, kể cả `llm` | Đọc; chỉ cập nhật cột `status` |
| `feedback` | Đọc (đánh giá Precision@5) | Ghi |
| `media` | Ghi `owner = 'flashtrend'` | Đọc; ghi `owner = 'estfstudio'`, `kind = 'cover'` |
| `estf_posts`, `estf_jobs` | Không đụng | Ghi và đọc (bảng của estfstudio) |
| `publish_jobs` (v2) | Ghi, chưa tạo ở MVP | Không đụng |

```sql title="Digest estfstudio đọc: run ok mới nhất, top 10, kèm ảnh"
select i.run_id, i.video_id, i.title, i.url, i.channel_title,
       i.viral_score, i.llm, v.thumbnail_url as image_url
from ideas i
join videos v on v.id = i.video_id
where i.run_id = (select id from runs where status = 'ok' order by started_at desc limit 1)
order by i.viral_score desc
limit 10;
```

Liệt kê cột cụ thể, không `select *`: giữ egress nhỏ và không bao giờ kéo vector 384 chiều về client.

Quy tắc estfstudio phải theo (kế hoạch ở `docs/v1.1.0/01-ke-hoach-supabase.html` của estfstudio):

| Quy tắc | Nội dung |
| --- | --- |
| Chỉ đọc run `ok` | Run `error` bị bỏ qua dù đã có `candidates` |
| `ideas.status` | Lồng tiếng một ý tưởng → `used`; bỏ qua → `seen` hoặc `rejected`; mặc định `new` |
| `feedback` | Nhãn `useful` / `not_useful` từ nút 👍 / 👎; một nhãn mỗi idea |
| `media` | Chỉ ghi `owner = 'estfstudio'`; `sha256` trùng thì dùng lại hàng cũ |
| Ảnh `alive = false` | Coi như không có ảnh; không xoá hàng của FlashTrend |
| Thứ tự DDL | DDL lõi, rồi `media`, rồi migration `estf_*` của estfstudio |

```sql title="Truy vấn cốt lõi khác"
-- μ, σ của cohort cho Z-Score (L1)
select avg(views / (channel_avg_views + 1e-5))         as mu_ratio,
       stddev_samp(views / (channel_avg_views + 1e-5)) as sigma_ratio
from candidates where run_id = 'run_20261028T071700';

-- B4: ba điểm gần nhất của một video
select views, captured_at from snapshots
where video_id = 'yt_vid001' order by captured_at desc limit 3;

-- Dọn TTL (cuối mỗi run hoặc pg_cron)
delete from snapshots  where expire_at < now();
delete from candidates where expire_at < now();
delete from embeddings where updated_at < now() - interval '90 days';
delete from estf_jobs  where expire_at < now();
```

## Thứ tự ghi trong một run {#thu-tu-ghi}

@steps id=write-order
| w1 | Mở run | `insert runs` với `status = running`, `id = run_<giờ VN>`. |
| w2 | Kênh và video | Kênh hết hạn (`stale_after`) mới gọi API; upsert `videos`, insert `snapshots`. |
| w3 | Chấm L1 | Insert `candidates` với Z, `viral_score`, `passed_z`. |
| w4 | Embedding | Upsert `embeddings`, bỏ qua khi `text_hash` trùng. |
| w5 | Leader và ảnh | Insert `ideas`; upload ảnh, insert `media` (trùng `sha256` thì dùng lại). |
| w6 | Gemini | Cập nhật `ideas.llm`; đủ schema thì `runs.status = ok`, ngược lại `error`. |
| w7 | Dọn TTL | Xoá `snapshots`, `candidates`, `embeddings`, `videos` mồ côi quá 90 ngày. |

## Ngân sách 500 MB chia thế nào? {#quota}

```mermaid title="Ước tính dung lượng sau 90 ngày (MB) — ~300 video mới/ngày, 2 run/ngày"
xychart-beta horizontal
  x-axis ["embeddings", "candidates", "videos", "nền Postgres", "estfstudio", "ideas (1 năm)", "snapshots", "media + channels"]
  y-axis "MB" 0 --> 100
  bar "MB" [95, 38, 27, 30, 20, 11, 8, 3]
```

| Bảng | Giả định | Ước tính |
| --- | --- | --- |
| `embeddings` | 27.000 vector × ~3,5 KB (1.544 B vector + hàng + HNSW) | 95 MB |
| `candidates` | 600 hàng/ngày × 90 ngày × ~0,7 KB | 38 MB |
| `videos` | 27.000 × ~1 KB, `description` cắt 500 ký tự | 27 MB |
| `snapshots` | 54.000 × ~0,15 KB | 8 MB |
| `ideas` | 10/ngày × 365 × ~3 KB (`llm` jsonb), giữ lâu dài | 11 MB |
| `media` + `channels` | Chỉ URL và số, không có ảnh | 3 MB |
| Phần estfstudio | Chừa 20 MB; kế hoạch v1.1.0 ước tính dùng ≈ 12 MB/năm (bài đã đăng, job nhẹ, ảnh bìa) | 20 MB |
| Nền Postgres | Catalog hệ thống, extension | 30 MB |
| **Tổng** | Cộng các dòng trên | **232 MB ≈ 46 %** |

Tổng: 95 + 38 + 27 + 8 + 11 + 3 + 20 + 30 = 232 MB. Đây là ước tính; đo thật bằng `pg_database_size` sau mỗi run.[](source:pgsize)

@metric id=db-budget label="Database ước tính / giới hạn Free" value=232 limit=500 unit=MB note="cảnh báo ở 350 MB, dừng ghi candidates ở 450 MB"

- [ ] Mỗi run ghi `pg_database_size(current_database())` vào log; vượt 350 MB thì giảm TTL embeddings xuống 60 ngày.
- [ ] Cắt `videos.description` còn 500 ký tự (bản gốc để 2.000).
- [ ] Không bật Supabase Storage cho ảnh: 1 GB storage và 5 GB egress dùng chung sẽ hết nhanh.[](source:pricing)
- [ ] Không có policy cho `anon`; chỉ `service_role` trong GitHub Secrets và `.secrets/` của estfstudio.
