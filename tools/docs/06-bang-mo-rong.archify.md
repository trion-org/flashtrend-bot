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
| `run_id` | text, FK kép → `ideas` | không | Idea nguồn | `run_20261028T001700Z` |
| `video_id` | text, FK kép → `ideas` | không | Leader được làm thành nội dung mới | `yt_vid001` |
| `status` | `publish_status_t` | không | `queued` → `uploaded` / `scheduled` / `failed` | `scheduled` |
| `youtube_video_id` | text | có | ID video trên **kênh của bạn** sau `videos.insert` | `Ab3dEf9GhIj` |
| `publish_at` | timestamptz | có | `status.publishAt` (UTC): upload sớm, YouTube tự công khai | `2026-10-30T08:00:00Z` |
| `privacy_status` | `privacy_t` | không | App chưa xác minh thì giữ `private` | `private` |
| `made_for_kids` | boolean | không | `selfDeclaredMadeForKids` bắt buộc (COPPA); thiếu thì API trả 400 | `false` |
| `error` | jsonb | có | Lỗi upload (quota ~1.600 unit, OAuth…) | `null` |

| Hàng mẫu | status | youtube_video_id | publish_at | error |
| --- | --- | --- | --- | --- |
| `job_20261029_vid001` | scheduled | `Ab3dEf9GhIj` | 30/10 08:00 UTC | — |
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
| `run_id` | text FK → `runs.id`, `on delete set null` | có | Ảnh thuộc run nào (chart) | `run_20261028T001700Z` |
| `alive` | boolean, mặc định true | không | `false` khi `HEAD url` trả 404 | `true` |
| `checked_at` | timestamptz | có | Lần kiểm link gần nhất (cron hằng tuần) | `2026-11-04T00:20:00Z` |
| `created_at` | timestamptz | không | Lúc ghi | `2026-10-28T00:18:38Z` |

Cron `HEAD url` hằng tuần của FlashTrend kiểm mọi hàng, kể cả `owner = 'estfstudio'`; 404 chỉ đặt `alive = false`, không xoá hàng. Phía estfstudio coi ảnh `alive = false` như chưa có ảnh bìa.

| Hàng mẫu | owner | kind | gắn với | bytes |
| --- | --- | --- | --- | --- |
| `img_4be1c07d9a2f5e31` | flashtrend | chart | `run_20261028T001700Z` | 48.213 |
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
| `idea_run_id` / `idea_video_id` | text, FK kép → `ideas`, `on delete set null` | có | Idea đã sinh ra bài này | `run_20261028T001700Z` / `yt_vid001` |
| `part_no` / `part_total` | smallint | có | Phần N/M khi đăng chia phần | `1` / `3` |
| `duration_sec` | int | có | Thời lượng tệp đã đăng | `598` |
| `cover_media_id` | text FK → `media.id` | có | Ảnh bìa của phần này | `img_9a1f0e22c4d7b860` |
| `status` | `estf_post_status_t` | không | `scheduled`, `published`, `failed`, `deleted` | `scheduled` |
| `scheduled_at` | timestamptz | có | Giờ đăng theo lịch của Facebook | `2026-10-28T13:00:00Z` |
| `published_at` | timestamptz | có | Giờ thực sự công khai | `null` |
| `created_at` | timestamptz | không | Lúc ghi sổ | `2026-10-28T11:42:10Z` |

| Hàng mẫu | platform | external_id | phần | status |
| --- | --- | --- | --- | --- |
| `1` | facebook | `1234567890123456` | 1/3 | scheduled |
| `2` | facebook | `1234567890123457` | 2/3 | scheduled |
| `3` | drive | `1AbCdEfGhIjKlMnOp` | — | published |

## estf_jobs — nhật ký job nhẹ của estfstudio {#estf-jobs}

Chỉ trạng thái và mã lỗi, không có log; tự xoá sau 90 ngày. Log đầy đủ vẫn nằm trên máy chạy bot.

| Field | Kiểu | Null | Mục đích | Mẫu |
| --- | --- | --- | --- | --- |
| `id` | text PK | không | `job_` + UTC stamp | `job_20261028T113001Z` |
| `kind` | text | không | Lệnh bot: `all`, `gen`, `fetch`, `translate`, `fb` | `all` |
| `source_url` | text | có | Link đầu vào | `https://www.youtube.com/watch?v=vid001` |
| `status` | text: `running` / `ok` / `error` | không | Trạng thái | `ok` |
| `error_code` | text | có | Tên lớp lỗi, không kèm thông điệp có dữ liệu cá nhân | `null` |
| `gpu` | text: `kaggle` / `local` / `none` | có | Job có dùng GPU mượn không | `kaggle` |
| `started_at` | timestamptz | không | Bắt đầu | `2026-10-28T11:30:01Z` |
| `finished_at` | timestamptz | có | Kết thúc | `2026-10-28T11:41:55Z` |
| `expire_at` | timestamptz | không | `started_at + 90 ngày` | `2027-01-26T11:30:01Z` |

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
| `media_kind_t` | `thumbnail`, `chart`, `cover` | `media.kind` |
| `estf_platform_t` | `facebook`, `drive`, `youtube` | `estf_posts.platform` |
| `estf_post_status_t` | `scheduled`, `published`, `failed`, `deleted` | `estf_posts.status` |
