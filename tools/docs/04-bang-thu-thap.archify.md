# Các bảng thu thập: mỗi field dùng để làm gì? {#bang-thu-thap}

Năm bảng giữ **dữ liệu thô và ngữ cảnh** của mỗi lần chạy: `app_config` (tham số thuật toán), `channels` (baseline kênh), `videos` (danh tính + số liệu mới nhất), `runs` (một job Actions) và `snapshots` (chuỗi thời gian views). Chúng được ghi trước khi tính bất kỳ điểm nào, nên chạy lại một run không làm mất lịch sử.

- ID theo dạng `{platform}_{nativeId}` (`yt_vid001`, `bi_BV1xx411c7M2`): upsert idempotent giữa các run.[](source:idea)
- Timestamp là `timestamptz`, mẫu ghi theo **giờ Việt Nam** (ISO-8601 kèm `+07:00`); database đặt múi giờ `Asia/Ho_Chi_Minh` nên SQL Editor cũng hiển thị giờ VN.
- Mẫu dùng xuyên suốt: run `run_20261028T071700` thu 5 video của 5 kênh; run thứ hai `run_20261028T181700` đo lại `yt_vid001` để có vận tốc.

@answer scope="Schema v1 (bản thiết kế) · mẫu dữ liệu dựng lại cho nhất quán · cột đánh dấu 'đề xuất' là bổ sung so với bản thiết kế gốc"
@meta locale=vi
@source idea title="Bản thiết kế FlashTrend (2026-10-28) — §4 Data Model, field dictionary"
@source yt-videos title="YouTube Data API — videos resource" url=https://developers.google.com/youtube/v3/docs/videos
@source yt-channels title="YouTube Data API — channels resource" url=https://developers.google.com/youtube/v3/docs/channels

## app_config — bảng tham số một hàng {#app-config}

Job đọc bảng này **một lần ở đầu run** để lấy ngưỡng θ, τ, λ và từ khoá. Không có khoá ngoại; `check (id = 1)` cấm hàng thứ hai. Đổi tham số = sửa hàng này, không sửa mã.

| Field | Kiểu | Null | Mục đích | Mẫu |
| --- | --- | --- | --- | --- |
| `id` | smallint PK, mặc định 1 | không | Khoá cứng = 1, bảo đảm singleton | `1` |
| `schema_version` | int | không | Phiên bản DDL bot kỳ vọng; lệch thì dừng ngay, không ghi rác | `1` |
| `regions` | text[] | không | `regionCode` cho chart A1 (ISO 3166-1 alpha-2) | `{VN,JP}` |
| `keywords` | text[] | không | Từ khoá cho `search.list` (A2); rỗng = chỉ dùng chart | `{python bot,ai tools,personal finance,street food,youtube shorts}` |
| `z_threshold` | float | không | θ: giữ candidate khi `z_score >= θ` | `1.5` |
| `cosine_threshold` | float | không | τ: hai tiêu đề chung cụm khi cosine ≥ τ | `0.70` |
| `history_cosine_threshold` | float | không | τ_hist: bỏ ý tưởng nếu giống lịch sử 90 ngày ≥ ngưỡng (C3) | `0.80` |
| `decay_lambda` | float | không | λ trong `exp(−λ · age_hours)`; 0.05 → nửa đời 13.9 giờ | `0.05` |
| `engagement_like_w` | float | không | Trọng số like trong engagement | `1.5` |
| `engagement_comment_w` | float | không | Trọng số comment (nặng hơn: tín hiệu đắt hơn) | `3.0` |
| `bayes_c` | int | không | C: độ mạnh prior, kéo video ít view về median ngách | `1000` |
| `min_cohort_n` | int | không | Dưới N video thì σ không tin được: nới θ | `20` |
| `snapshot_ttl_days` | int | không | `expire_at = captured_at + N ngày` cho snapshots/candidates | `90` |
| `llm_enabled` | boolean | không | `true` ở MVP; `false` chỉ khi debug L1/L2 không gọi Gemini | `true` |
| `relaxed_z_threshold` | float, **đề xuất** | không | θ dùng khi `cohort_n < min_cohort_n` | `0.5` |
| `chart_enabled` | boolean, **đề xuất** | không | `false` = bỏ chart `mostPopular` chung để cohort chỉ gồm video trong ngách | `false` |
| `search_window_hours` | int, **đề xuất** | không | A2 chỉ lấy video đăng trong N giờ gần nhất (1–720); ngách ít upload cần nhiều ngày | `168` |
| `updated_at` | timestamptz | không | Lần người sửa tham số (không phải mỗi job) | `2026-10-28T07:17:00+07:00` |

Ví dụ ngách hoạt hình Trung Quốc (đo trên kết quả YouTube thật, 2026-10-31): từ khoá ngắn và rộng như `国漫`, `修仙动画`, `AI漫剧` cho khoảng 25 video mỗi lần; cụm ghép `全集` / `合集` hoặc `国创 3D` trả về 0 vì YouTube coi là AND; cửa sổ 48 giờ để trống phần lớn từ khoá nên seed đặt `search_window_hours = 168`, `chart_enabled = false` và `decay_lambda = 0.01` (nửa đời ≈ 69 giờ, vì λ = 0.05 sẽ đưa điểm mọi video 6 ngày tuổi về gần 0). Bản đầy đủ nằm ở `sql/04_seed_app_config.sql`.

```sql title="Mẫu — seed app_config"
insert into app_config (keywords, regions, llm_enabled)
values (array['python bot', 'ai tools', 'personal finance', 'street food', 'youtube shorts'],
        array['VN', 'JP'], true);
```

## channels — baseline của kênh {#channels}

Không có baseline kênh thì views tuyệt đối vô nghĩa: 100k views là bình thường với kênh nhạc, là đột biến với kênh 8k sub. Hàng được cache 24 giờ để tránh N+1 lần gọi `channels.list`.[](source:yt-channels)

| Field | Kiểu | Null | Mục đích | Mẫu |
| --- | --- | --- | --- | --- |
| `id` | text PK | không | `{platform}_{native_id}`, upsert idempotent | `yt_UC_pythonlab` |
| `platform` | `platform_t` | không | Nền tảng; khớp tiền tố của `id` | `youtube` |
| `native_id` | text | không | ID gốc (YouTube `UC…`, Douyin user id); unique cùng `platform` | `UC_pythonlab` |
| `title` | text | không | Tên hiển thị; được copy sang `ideas.channel_title` | `Python Lab VN` |
| `subscriber_count` | bigint | có | Bối cảnh kênh nhỏ/lớn; chưa vào công thức v1; YouTube có thể ẩn | `8200` |
| `video_count` | int | có | Mẫu số khi ước `channel_avg_views = viewCount / videoCount` | `140` |
| `channel_avg_views` | float | không | μ kênh trong `performance_ratio`; thiếu cột này Z-Score vô nghĩa | `5000.0` |
| `fetched_at` | timestamptz | không | Lần gọi `channels.list` gần nhất | `2026-10-28T07:17:10+07:00` |
| `stale_after` | timestamptz | không | `fetched_at + 24h`; chỉ gọi API lại khi `now() > stale_after` | `2026-10-29T07:17:10+07:00` |

| Hàng mẫu | title | subscriber_count | video_count | channel_avg_views |
| --- | --- | --- | --- | --- |
| `yt_UC_pythonlab` | Python Lab VN | 8.200 | 140 | 5.000 |
| `yt_UC_codevn` | Code Dạo VN | 6.500 | 95 | 4.000 |
| `yt_UC_foodtrip` | Ăn Khắp Việt Nam | 52.000 | 310 | 10.000 |
| `yt_UC_fin20s` | Tài chính 20s | 4.100 | 88 | 3.000 |
| `yt_UC_bigmusic` | Big Music VN | 3.200.000 | 1.450 | 1.800.000 |

## videos — danh tính và số liệu mới nhất {#videos}

Một hàng cho mỗi video từng gặp, ổn định giữa các run. Số liệu `last_*` là bản sao snapshot mới nhất để đọc nhanh; lịch sử thật nằm ở `snapshots`.[](source:yt-videos)

| Field | Kiểu | Null | Mục đích | Mẫu |
| --- | --- | --- | --- | --- |
| `id` | text PK | không | `{platform}_{native_id}` | `yt_vid001` |
| `platform` | `platform_t` | không | Nguồn | `youtube` |
| `native_id` | text | không | videoId / BV / aweme id; unique cùng `platform` | `vid001` |
| `url` | text | không | Link chuẩn để estfstudio mở hoặc lồng tiếng | `https://www.youtube.com/watch?v=vid001` |
| `title` | text | không | Tiêu đề mới nhất; đầu vào embedding khi `source = title` | `Cách tạo Bot Python lấy dữ liệu TikTok tự động` |
| `description` | text, mặc định `''` | không | Đầu vào Gemini và lọc từ khoá; cắt 500 ký tự (bản gốc để 2.000) | `Thu thập metadata TikTok bằng Python, không tải file.` |
| `published_at` | timestamptz | không | Giờ đăng gốc → `age_hours` của candidate | `2026-10-28T02:00:00+07:00` |
| `channel_id` | text FK → `channels.id` | không | Chủ sở hữu; join lấy baseline khi cần | `yt_UC_pythonlab` |
| `duration_sec` | int | có | Phân biệt Shorts và video dài (F4) | `842` |
| `thumbnail_url` | text | có | URL `i.ytimg.com` công khai; không cần upload | `https://i.ytimg.com/vi/vid001/hqdefault.jpg` |
| `last_views` | bigint | không | Views lần đo gần nhất | `150000` |
| `last_likes` | bigint | không | Likes lần đo gần nhất | `9200` |
| `last_comments` | bigint | không | Comments lần đo gần nhất | `410` |
| `first_seen_at` | timestamptz | không | Lần đầu bot gặp; không ghi đè khi upsert | `2026-10-28T07:17:12+07:00` |
| `last_seen_at` | timestamptz | không | Lần thu gần nhất; dùng để dọn video mồ côi quá 90 ngày | `2026-10-28T07:17:12+07:00` |
| `last_run_id` | text (tham chiếu logic → `runs.id`) | có | Run cập nhật số liệu lần cuối; cố ý không FK để tránh vòng khi insert | `run_20261028T071700` |
| `transcript_excerpt` | text | có | Tối đa 12.000 ký tự phụ đề (A7, P1); null ở MVP | `null` |

| Hàng mẫu | title | published_at | views / likes / comments | kênh |
| --- | --- | --- | --- | --- |
| `yt_vid001` | Cách tạo Bot Python lấy dữ liệu TikTok tự động | 28/10 02:00 | 150.000 / 9.200 / 410 | `yt_UC_pythonlab` |
| `yt_vid002` | Hướng dẫn viết Bot Python cào video TikTok đơn giản | 27/10 22:30 | 120.000 / 6.800 / 350 | `yt_UC_codevn` |
| `yt_vid003` | Vlog một ngày ăn uống tại Đà Nẵng | 26/10 19:00 | 8.000 / 310 / 25 | `yt_UC_foodtrip` |
| `yt_vid004` | Bí quyết quản lý tài chính cho sinh viên năm 2026 | 27/10 15:00 | 95.000 / 6.100 / 380 | `yt_UC_fin20s` |
| `yt_vid005` | Video ca nhạc hài hước triệu views | 27/10 01:17 | 2.000.000 / 85.000 / 4.200 | `yt_UC_bigmusic` |

## runs — một lần chạy của GitHub Actions {#runs}

Mỗi job tạo đúng một hàng. Xoá một run thì `candidates` và `ideas` của nó bị xoá theo (`ON DELETE CASCADE`). estfstudio chỉ đọc run có `status = 'ok'`.

| Field | Kiểu | Null | Mục đích | Mẫu |
| --- | --- | --- | --- | --- |
| `id` | text PK | không | `run_` + giờ VN `YYYYMMDDTHHMMSS`; sắp xếp được, gần giờ cron 07:17 | `run_20261028T071700` |
| `schema_version` | int | không | Schema lúc ghi | `1` |
| `trigger` | `run_trigger_t` | không | `schedule` (cron) hay `workflow_dispatch` (chạy tay) | `schedule` |
| `git_sha` | text | không | Commit của bot; chạy local ghi `local`; truy vết lỗi | `3f9c2ab` |
| `region` | text | không | Region chính của lần chạy | `VN` |
| `started_at` | timestamptz | không | Khoá của truy vấn "run mới nhất" | `2026-10-28T07:17:02+07:00` |
| `finished_at` | timestamptz | có | Null khi đang `running` | `2026-10-28T07:18:41+07:00` |
| `status` | `run_status_t` | không | `running` → `ok` / `error` | `ok` |
| `error` | jsonb | có | Lỗi có cấu trúc: `code`, `message`, `details`, `trace_id` | `null` |
| `collected` | int | không | Số video A1 + A2 thu được | `5` |
| `scored` | int | không | Số hàng `candidates` | `5` |
| `outliers` | int | không | Số candidate `passed_z = true` | `3` |
| `ideas_count` | int | không | Số leader L2 (hàng `ideas`) | `2` |
| `cohort_n` | int | có | N dùng tính μ, σ | `5` |
| `cohort_mu_ratio` | float | có | μ của `performance_ratio` trong cohort | `18.7156` |
| `cohort_sigma_ratio` | float | có | σ mẫu của `performance_ratio` | `16.2272` |
| `cohort_median_engagement` | float | có | Prior m của engagement Bayes | `0.0938` |
| `z_threshold_used` | float, **đề xuất** | có | θ thực dùng (1.5, hoặc 0.5 khi cohort nhỏ) | `0.5` |
| `duration_ms` | int | có | Thời gian chạy; mục tiêu dưới 3 phút | `99000` |
| `chart_path` | text | có | Đường dẫn PNG artifact trên Actions (debug) | `output/2026-10-28_visual_summary.png` |
| `chart_media_id` | text FK → `media.id`, **đề xuất** | có | Biểu đồ đã upload lên image host | `img_4be1c07d9a2f5e31` |

| Hàng mẫu | trigger | status | collected / outliers / ideas | error |
| --- | --- | --- | --- | --- |
| `run_20261028T071700` | schedule | ok | 5 / 3 / 2 | — |
| `run_20261028T181700` | schedule | ok | 5 / 3 / 2 | — |
| `run_20261029T071700` | workflow_dispatch | error | 0 / 0 / 0 | `YT_QUOTA` |

```json title="runs.error — mẫu khi hết quota YouTube"
{
  "code": "YT_QUOTA",
  "message": "YouTube Data API quota exceeded",
  "details": {"reason": "quotaExceeded"},
  "trace_id": "run_20261029T071700"
}
```

Mã lỗi gợi ý: `YT_QUOTA`, `YT_AUTH`, `GEMINI_RATE_LIMIT`, `GEMINI_SCHEMA`, `DB_WRITE`, `SCHEMA_MISMATCH`, `TIMEOUT`.

## snapshots — chuỗi thời gian để tính vận tốc {#snapshots}

Khoá kép `(video_id, run_id)`: mỗi video tối đa một điểm mỗi run. Vận tốc **không** lưu ở đây mà tính khi chấm và ghi vào `candidates`.

| Field | Kiểu | Null | Mục đích | Mẫu |
| --- | --- | --- | --- | --- |
| `video_id` | text PK, FK → `videos.id` | không | Video được đo | `yt_vid001` |
| `run_id` | text PK, FK → `runs.id` | không | Lần đo | `run_20261028T071700` |
| `captured_at` | timestamptz | không | Giờ đo; index `(video_id, captured_at desc)` | `2026-10-28T07:17:12+07:00` |
| `views` | bigint | không | Views tại t; Δviews/Δt = vận tốc | `150000` |
| `likes` | bigint | không | Likes tại t | `9200` |
| `comments` | bigint | không | Comments tại t | `410` |
| `expire_at` | timestamptz | không | `captured_at + snapshot_ttl_days`; cron xoá khi quá hạn | `2027-01-26T07:17:12+07:00` |

| Hàng mẫu | run | captured_at | views | likes | comments |
| --- | --- | --- | --- | --- | --- |
| `yt_vid001` lần 1 | `run_20261028T071700` | 28/10 07:17:12 | 150.000 | 9.200 | 410 |
| `yt_vid001` lần 2 | `run_20261028T181700` | 28/10 18:17:10 | 410.000 | 24.900 | 1.130 |
| `yt_vid004` lần 1 | `run_20261028T071700` | 28/10 07:17:12 | 95.000 | 6.100 | 380 |

Vận tốc của `yt_vid001` ở run thứ hai: (410.000 − 150.000) / 10,9994 giờ (07:17:12 → 18:17:10) ≈ 23.638 views/giờ. Gia tốc cần điểm thứ ba nên còn null.
