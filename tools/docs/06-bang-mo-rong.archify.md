# Các bảng mở rộng: publish_jobs, media và bảng của estfstudio {#bang-mo-rong}

Ngoài lõi MVP còn bốn bảng: `publish_jobs` (v2, hàng đợi đăng YouTube), `media` (link ảnh trên image host, dùng chung hai repo), và hai bảng **do estfstudio sở hữu** trong cùng project: `estf_posts` (sổ bài đã đăng) và `estf_jobs` (nhật ký job nhẹ). Bảng enum ở cuối trang liệt kê mọi giá trị hợp lệ.

- `publish_jobs` không tạo ở MVP; nó chỉ cần khi Phase 3 (đăng video có quyền) bắt đầu.[](source:idea)
- `media` không giữ ảnh, chỉ giữ URL và `sha256`, nên gần như không tốn dung lượng.
- FlashTrend không bao giờ ghi vào `estf_*`; estfstudio không bao giờ ghi vào bảng chấm điểm.

@answer scope="publish_jobs theo bản thiết kế · media, estf_posts, estf_jobs là thiết kế mới (2026-10-28) · mẫu minh hoạ"
@meta locale=vi
@source idea title="Bản thiết kế FlashTrend (2026-10-28) — publish_jobs, enums"
@source estf-plan title="estfstudio — kế hoạch v1.1.0 dùng chung Supabase" url=https://github.com/trion-org/estfstudio/blob/develop/docs/v1.1.0/01-ke-hoach-supabase.html
@source yt-insert title="YouTube Data API — videos.insert" url=https://developers.google.com/youtube/v3/docs/videos/insert

## publish_jobs — hàng đợi đăng YouTube (v2) {#publish-jobs}

Một idea có thể có nhiều job (thử lại). Không lưu token OAuth trong hàng nào.[](source:yt-insert)

| Field | Kiểu | Null | Mục đích | Mẫu |
| --- | --- | --- | --- | --- |
| `id` | text PK | không | `job_{ngày}_{video_id}` hoặc uuid | `job_20261029_vid001` |
| `run_id` | text, FK kép → `ideas` | không | Idea nguồn | `run_20261028T071700` |
| `video_id` | text, FK kép → `ideas` | không | Leader được làm thành nội dung mới | `yt_vid001` |
| `status` | `publish_status_t` | không | `queued` → `uploaded` / `scheduled` / `failed` | `scheduled` |
| `youtube_video_id` | text | có | ID video trên **kênh của bạn** sau `videos.insert` | `Ab3dEf9GhIj` |
| `publish_at` | timestamptz | có | `status.publishAt` (ghi `+07:00`): upload sớm, YouTube tự công khai | `2026-10-30T15:00:00+07:00` |
| `privacy_status` | `privacy_t` | không | App chưa xác minh thì giữ `private` | `private` |
| `made_for_kids` | boolean | không | `selfDeclaredMadeForKids` bắt buộc (COPPA); thiếu thì API trả 400 | `false` |
| `error` | jsonb | có | Lỗi upload (quota ~1.600 unit, OAuth…) | `null` |

| Hàng mẫu | status | youtube_video_id | publish_at | error |
| --- | --- | --- | --- | --- |
| `job_20261029_vid001` | scheduled | `Ab3dEf9GhIj` | 30/10 15:00 | — |
| `job_20261029_vid004` | failed | — | — | `{"code":"YT_QUOTA"}` |

## media — link ảnh trên image host {#media}

Mỗi tệp ảnh có đúng một hàng: `sha256` unique nên upload lại cùng ảnh sẽ dùng lại URL cũ.

| Field | Kiểu | Null | Mục đích | Mẫu |
| --- | --- | --- | --- | --- |
| `id` | text PK | không | `img_` + 16 ký tự đầu của sha256 | `img_4be1c07d9a2f5e31` |
| `owner` | text, `flashtrend` hoặc `estfstudio` | không | Repo nào tạo ảnh; mỗi bên chỉ ghi hàng của mình | `flashtrend` |
| `kind` | `media_kind_t` | không | `thumbnail`, `chart` (biểu đồ run), `cover` (ảnh bìa từng phần) | `chart` |
| `url` | text | không | URL công khai image host trả về | URL do host trả |
| `host` | text, mặc định `nobinobi` | không | Image host nào, để thay host mà không mất dấu | `nobinobi` |
| `sha256` | text unique | không | Chống upload trùng | `4be1c07d9a2f5e31…` |
| `bytes` | int, `check (bytes <= 2000000)` | không | Giới hạn 2 MB mỗi ảnh | `48213` |
| `width` / `height` | int | có | Kích thước ảnh | `1200` / `630` |
| `video_id` | text FK → `videos.id` | có | Ảnh thuộc video nào (thumbnail, cover) | `null` |
| `run_id` | text FK → `runs.id`, `on delete set null` | có | Ảnh thuộc run nào (chart) | `run_20261028T071700` |
| `alive` | boolean, mặc định true | không | `false` khi `HEAD url` trả 404 | `true` |
| `checked_at` | timestamptz | có | Lần kiểm link gần nhất (cron hằng tuần) | `2026-11-04T07:20:00+07:00` |
| `created_at` | timestamptz | không | Lúc ghi | `2026-10-28T07:18:38+07:00` |

Cron `HEAD url` hằng tuần của FlashTrend kiểm mọi hàng, kể cả `owner = 'estfstudio'`; 404 chỉ đặt `alive = false`, không xoá hàng. Phía estfstudio coi ảnh `alive = false` như chưa có ảnh bìa.

| Hàng mẫu | owner | kind | gắn với | bytes |
| --- | --- | --- | --- | --- |
| `img_4be1c07d9a2f5e31` | flashtrend | chart | `run_20261028T071700` | 48.213 |
| `img_9a1f0e22c4d7b860` | estfstudio | cover | bài `estf_posts` id 1 | 182.554 |

## estf_posts — sổ bài estfstudio đã đăng {#estf-posts}

Một hàng cho mỗi tệp đã đăng lên Facebook hoặc Drive. Nếu bài sinh ra từ một idea FlashTrend thì nối về `ideas`.[](source:estf-plan)

| Field | Kiểu | Null | Mục đích | Mẫu |
| --- | --- | --- | --- | --- |
| `id` | bigint identity PK | không | Khoá nội bộ | `1` |
| `platform` | `estf_platform_t` | không | `facebook`, `drive`, `youtube` | `facebook` |
| `external_id` | text | không | ID video Facebook / ID tệp Drive; unique cùng `platform` | `1234567890123456` |
| `permalink` | text | có | `permalink_url` của Facebook / `webViewLink` của Drive | `https://www.facebook.com/…/videos/1234567890123456` |
| `title` | text, tối đa 200 ký tự | không | Tiêu đề bài | Bot Python lấy dữ liệu TikTok — Phần 1/3 |
| `source_url` | text | có | Link video gốc đã lồng tiếng | `https://www.youtube.com/watch?v=vid001` |
| `idea_run_id` / `idea_video_id` | text, FK kép → `ideas`, `on delete set null` | có | Idea đã sinh ra bài này | `run_20261028T071700` / `yt_vid001` |
| `part_no` / `part_total` | smallint | có | Phần N/M khi đăng chia phần | `1` / `3` |
| `duration_sec` | int | có | Thời lượng tệp đã đăng | `598` |
| `cover_media_id` | text FK → `media.id` | có | Ảnh bìa của phần này | `img_9a1f0e22c4d7b860` |
| `status` | `estf_post_status_t` | không | `scheduled`, `published`, `failed`, `deleted` | `scheduled` |
| `scheduled_at` | timestamptz | có | Giờ đăng theo lịch của Facebook | `2026-10-28T20:00:00+07:00` |
| `published_at` | timestamptz | có | Giờ thực sự công khai | `null` |
| `created_at` | timestamptz | không | Lúc ghi sổ | `2026-10-28T18:42:10+07:00` |

| Hàng mẫu | platform | external_id | phần | status |
| --- | --- | --- | --- | --- |
| `1` | facebook | `1234567890123456` | 1/3 | scheduled |
| `2` | facebook | `1234567890123457` | 2/3 | scheduled |
| `3` | drive | `1AbCdEfGhIjKlMnOp` | — | published |

## estf_jobs — nhật ký job nhẹ của estfstudio {#estf-jobs}

Chỉ trạng thái và mã lỗi, không có log; tự xoá sau 90 ngày. Log đầy đủ vẫn nằm trên máy chạy bot.

| Field | Kiểu | Null | Mục đích | Mẫu |
| --- | --- | --- | --- | --- |
| `id` | text PK | không | `job_` + giờ VN `YYYYMMDDTHHMMSS` | `job_20261028T183001` |
| `kind` | text | không | Lệnh bot: `all`, `gen`, `fetch`, `translate`, `fb` | `all` |
| `source_url` | text | có | Link đầu vào | `https://www.youtube.com/watch?v=vid001` |
| `status` | text: `running` / `ok` / `error` | không | Trạng thái | `ok` |
| `error_code` | text | có | Tên lớp lỗi, không kèm thông điệp có dữ liệu cá nhân | `null` |
| `gpu` | text: `kaggle` / `local` / `none` | có | Job có dùng GPU mượn không | `kaggle` |
| `started_at` | timestamptz | không | Bắt đầu | `2026-10-28T18:30:01+07:00` |
| `finished_at` | timestamptz | có | Kết thúc | `2026-10-28T18:41:55+07:00` |
| `expire_at` | timestamptz | không | `started_at + 90 ngày` | `2027-01-26T18:30:01+07:00` |

## Mọi kiểu enum {#enum}

| Enum | Giá trị | Dùng ở |
| --- | --- | --- |
| `platform_t` | `youtube`, `tiktok`, `facebook`, `bilibili`, `douyin` (tiền tố `yt_`, `tt_`, `fb_`, `bi_`, `dy_`) | `channels`, `videos`, `candidates`, `ideas` |
| `run_trigger_t` | `schedule`, `workflow_dispatch` | `runs.trigger` |
| `run_status_t` | `running`, `ok`, `error` | `runs.status` |
| `idea_status_t` | `new`, `seen`, `used`, `rejected` | `ideas.status` |
| `feedback_label_t` | `useful`, `not_useful`, `duplicate`, `used` | `feedback.label` |
| `publish_status_t` | `queued`, `uploaded`, `scheduled`, `failed` | `publish_jobs.status` |
| `privacy_t` | `private`, `unlisted`, `public` | `publish_jobs.privacy_status` |
| `media_kind_t` | `thumbnail`, `chart`, `cover`, `analysis` (migration 07) | `media.kind` |
| `estf_platform_t` | `facebook`, `drive`, `youtube` | `estf_posts.platform` |
| `estf_post_status_t` | `scheduled`, `published`, `failed`, `deleted` | `estf_posts.status` |

## hot_videos và biểu đồ phân tích {#phan-tich}

Mỗi lần chạy ghi hai danh sách vào `hot_videos` (phẳng, không cần join): `kind = 'video'` là 10 video Bilibili hot nhất theo độ ưu tiên, `kind = 'series'` là 10 series 国创 đứng đầu bảng xếp hạng sống của Bilibili (ví dụ 灵笼 第二季; `views` là tổng lượt xem cả series, `channel_title` là điểm và số tập, không có thời lượng hay ngày đăng; thứ hạng tính lại từ 1 trong mỗi `kind`) và, theo chu kỳ `analysis_every_hours`, tám ảnh biểu đồ vào `media` với `kind = 'analysis'`, kèm `caption` (tiêu đề tiếng Việt) và `position` (thứ tự hiển thị). estfstudio đọc cả hai cho lệnh `/analysis`. Migration này chạy trên mọi database, mới hay cũ.

```sql title="Migration 07 — biểu đồ phân tích, hot_videos, tham số chu kỳ"
alter type media_kind_t add value if not exists 'analysis';
alter table media add column if not exists caption text;
alter table media add column if not exists position smallint;

create table if not exists hot_videos (
  run_id text not null references runs (id) on delete cascade,
  kind text not null default 'video' check (kind in ('video', 'series')),
  rank smallint not null check (rank between 1 and 50),   -- 1 = hottest within its kind
  video_id text not null,                                  -- 'bi_BV…' or 'bi_ss<season>'; no foreign key: videos get cleaned up
  platform text not null,
  title text not null,
  url text not null,
  channel_title text,                                      -- series: rating and episodes, e.g. '9.8分 · 全12话'
  views bigint not null default 0,                         -- series: total plays of the whole series
  duration_sec int,
  published_at timestamptz,
  niche boolean not null default false,                    -- matched app_config.niche_terms or a niche ranking
  viral_score double precision not null default 0,
  created_at timestamptz not null default now(),
  primary key (run_id, kind, rank)
);
create index if not exists hot_videos_created on hot_videos (created_at desc);
alter table hot_videos enable row level security;
alter table hot_videos add column if not exists parts smallint check (parts >= 1);   -- null = not checked; duration_sec is the total of the parts
alter table hot_videos add column if not exists first_part_sec int check (first_part_sec >= 0);   -- the player opens part 1

alter table app_config add column if not exists bilibili_series_types int[] not null default '{}';
alter table app_config add column if not exists niche_terms text[] not null default '{}';
alter table app_config add column if not exists niche_boost double precision not null default 1
  check (niche_boost between 1 and 10);
alter table app_config add column if not exists youtube_search_every_hours int not null default 1
  check (youtube_search_every_hours between 1 and 24);
alter table app_config add column if not exists analysis_every_hours int not null default 1
  check (analysis_every_hours between 1 and 24);
alter table app_config add column if not exists niche_exclude_terms text[] not null default '{}';
alter table app_config add column if not exists niche_only boolean not null default false;
alter table app_config add column if not exists min_duration_sec int not null default 0
  check (min_duration_sec >= 0);
alter table app_config drop constraint if exists app_config_search_window_hours_check;
alter table app_config add constraint app_config_search_window_hours_check
  check (search_window_hours between 1 and 4320);
```

| Cột mới | Ý nghĩa |
| --- | --- |
| `app_config.bilibili_series_types` | Bảng xếp hạng series Bilibili (4 = 国创); rỗng = không lấy bảng xếp hạng |
| `app_config.niche_terms` | Từ trong tiêu đề hoặc mô tả để coi video thuộc ngách |
| `app_config.niche_boost` | Hệ số ưu tiên ngách khi xếp ý tưởng và danh sách hot (không đổi `viral_score`) |
| `app_config.youtube_search_every_hours` | Tìm từ khoá YouTube chỉ khi giờ chia hết N: giữ quota 10.000 đơn vị/ngày |
| `hot_videos.parts` · `hot_videos.first_part_sec` | Số phần (分P) của video hot và độ dài phần 1; rỗng = chưa kiểm. `duration_sec` là tổng các phần |
| `app_config.min_duration_sec` | Bỏ video ngắn hơn N giây và chỉ yêu cầu video dài từ nền tảng; 0 = không lọc |
| `app_config.niche_only` | Bỏ video không thuộc ngách trước khi chấm điểm |
| `app_config.niche_exclude_terms` | Tiêu đề có từ này thì không thuộc ngách (khoá học, thuyết minh) |
| `app_config.analysis_every_hours` | Vẽ và upload biểu đồ chỉ khi giờ chia hết N: giữ tải của image host |
