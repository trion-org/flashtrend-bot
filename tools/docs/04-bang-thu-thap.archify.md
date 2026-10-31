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
| `bilibili_keywords` | text[], **đề xuất** | không | Từ khoá tiếng Trung cho tìm kiếm Bilibili; rỗng = tắt Bilibili | `{3D玄幻,修仙动画,AI漫剧}` |
| `min_duration_sec` | int, **đề xuất** | không | Bỏ video ngắn hơn N giây trước khi chấm điểm, và yêu cầu cả hai nền tảng chỉ trả video dài; `0` = mọi độ dài | `14400` |
| `niche_only` | bool, **đề xuất** | không | `true` = bỏ video không thuộc ngách (không khớp `niche_terms`) trước khi chấm điểm | `true` |
| `niche_exclude_terms` | text[], **đề xuất** | không | Tiêu đề có một từ này thì không bao giờ thuộc ngách (khoá học, thuyết minh truyện cũng dài hàng giờ) | `{教程,解说,说书}` |
| `bilibili_series_types` | int[], **đề xuất** | không | Bảng xếp hạng series "đang hot" của Bilibili; `4` = 国创; rỗng = không lấy | `{4}` |
| `niche_terms` | text[], **đề xuất** | không | Từ trong tiêu đề/mô tả để coi video thuộc ngách (khớp không phân biệt hoa thường) | `{国漫,国创,漫剧,修仙}` |
| `niche_boost` | float, **đề xuất** | không | Hệ số ưu tiên của video ngách khi xếp ý tưởng và danh sách hot (1–10); không đổi `viral_score` | `3` |
| `youtube_search_every_hours` | int, **đề xuất** | không | Tìm từ khoá YouTube chỉ khi giờ Việt Nam chia hết N | `6` |
| `analysis_every_hours` | int, **đề xuất** | không | Vẽ và upload biểu đồ chỉ khi giờ Việt Nam chia hết N | `3` |
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
| `search_window_hours` | int, **đề xuất** | không | A2 chỉ lấy video đăng trong N giờ gần nhất (1–4320, tức 180 ngày); ngách ít upload hoặc tổng hợp dài cần nhiều tuần | `2160` |
| `updated_at` | timestamptz | không | Lần người sửa tham số (không phải mỗi job) | `2026-10-28T07:17:00+07:00` |

Ví dụ ngách hoạt hình Trung Quốc (đo trên kết quả YouTube thật, 2026-10-31): từ khoá ngắn và rộng như `国漫`, `修仙动画`, `AI漫剧` cho khoảng 25 video mỗi lần; cụm ghép `全集` / `合集` hoặc `国创 3D` trả về 0 vì YouTube coi là AND; cửa sổ 48 giờ để trống phần lớn từ khoá nên seed đặt `search_window_hours = 168`, `chart_enabled = false` và `decay_lambda = 0.01` (nửa đời ≈ 69 giờ, vì λ = 0.05 sẽ đưa điểm mọi video 6 ngày tuổi về gần 0). Bản đầy đủ nằm ở `sql/04_seed_app_config.sql`.

```sql title="Mẫu — seed app_config"
insert into app_config (keywords, regions, llm_enabled)
values (array['python bot', 'ai tools', 'personal finance', 'street food', 'youtube shorts'],
        array['VN', 'JP'], true);
```

## Bilibili — tìm kiếm không cần đăng nhập {#bilibili}

Bilibili không có API công khai cho việc này, nên adapter gọi đúng hai endpoint mà trang web gọi, **ẩn danh**: tìm kiếm (`search/type`, `order=click`, lọc theo `pubtime_begin_s` / `pubtime_end_s`) và thẻ kênh (`card`). Chỉ đọc metadata, không tải gì. Không dùng cookie: repo công khai, và cookie tài khoản cá nhân không thuộc về GitHub Actions; tải video chất lượng cao là việc của estfstudio.

| Đo ngày 2026-10-31 | Kết quả |
| --- | --- |
| Tìm kiếm có cửa sổ thời gian | Trả tối đa 20 video mỗi trang, đúng trong cửa sổ, kèm `play`, `like`, `review` (bình luận), `duration`, `pubdate`, `pic` |
| Từ khoá cho nhiều video | `修仙动画`, `国漫`, `AI漫剧`, `AI动画`, `3D国漫`, `3D玄幻` đều đủ 20 video / 7 ngày; `3D玄幻` có 15/20 video dài trên 1 giờ |
| Lịch sử video của kênh (`space/wbi/arc/search`) | `-352` (kiểm soát rủi ro) với khách ẩn danh, kể cả có cookie `buvid`: không dùng được |
| Thẻ kênh (`card`) | Trả `fans`, `archive_count`, tổng like; không có tổng view |
| Chặn chống bot | HTTP 412 ngẫu nhiên: cùng URL lúc 200 lúc 412; 2/10 từ khoá thử bị chặn sau cả ba lần thử lại {caution:Không ổn định} |

- **Baseline kênh = số người theo dõi.** Vì không có view trung bình của kênh, `channel_avg_views` của kênh Bilibili là `fans`, và `performance_ratio` thành *view trên người theo dõi*.
- **Mỗi nền tảng một cohort.** Tỉ lệ của YouTube (view / view trung bình kênh) và của Bilibili (view / người theo dõi) khác thang đo, nên μ, σ, θ tính riêng từng nền tảng; điểm YouTube không đổi khi thêm Bilibili. Hàng `runs` ghi cohort của nền tảng lớn nhất; log liệt kê cả hai.
- **Bilibili không bao giờ làm hỏng run.** Mỗi request thử lại sau 3, 8, 20 giây; từ khoá vẫn bị chặn thì bị bỏ qua và báo `warn`, các từ khoá khác và YouTube vẫn chạy. Giữa hai request có nghỉ 1 giây.
- Mã nền tảng trong `id` là `bi_`: video `bi_BV1…`, kênh `bi_<mid>`.

## Tìm video tổng hợp dài thay vì clip {#tong-hop-dai}

Ngách cần là **tuyển tập hoạt hình dài từ 4 giờ trở lên** (cả mùa phim hoặc nhiều bộ trong một video), không phải clip ngắn. Ba lớp lọc làm việc đó, theo thứ tự:

1. **Hỏi đúng nền tảng.** Khi `min_duration_sec` từ 1 giờ trở lên, Bilibili được tìm với `duration=4` (dài hơn 60 phút) và đọc 2 trang cho mỗi từ khoá; YouTube dùng `videoDuration=long` (trên 20 phút, bộ lọc dài nhất API có).
2. **Lọc độ dài.** Video ngắn hơn `min_duration_sec` hoặc không có thời lượng bị bỏ trước khi chấm điểm, nên không tốn một request thẻ kênh nào cho chúng.
3. **Lọc ngách.** Với `niche_only`, video phải khớp một từ trong `niche_terms` và tiêu đề không chứa từ nào trong `niche_exclude_terms`.

Đo ngày 2026-10-31 trên Bilibili: 8 truy vấn dạng tuyển tập (`国漫 合集`, `修仙动画 合集`, `3D国漫 全集 连播`, `国漫 通宵 连播`…) cho **61 video khác nhau dài từ 4 giờ trở lên**, có video dài 10 đến 80 giờ. Chúng thường đã đăng nhiều tháng, nên cửa sổ tìm là 90 ngày và `decay_lambda = 0.001` (video 7 ngày tuổi giữ 85% điểm, 90 ngày giữ 12%; λ = 0.01 sẽ làm điểm mọi video cũ hơn một tuần về gần 0). Tìm kiếm không tin tuyệt đối vào từ khoá: cuộc đo cũng trả về khoá học làm hoạt hình AI dài 293 giờ và thuyết minh tiểu thuyết 2446 chương, nên `niche_exclude_terms` là bắt buộc.

## Ưu tiên ngách, chạy mỗi giờ và biểu đồ phân tích {#uu-tien}

**Ưu tiên ngách.** Video khớp `niche_terms` trong tiêu đề hoặc mô tả được nhân `niche_boost` khi xếp thứ tự ý tưởng, danh sách hot và thẻ đầu. Điểm `viral_score` lưu trong database không đổi, nên so sánh với các lần chạy cũ vẫn đúng. Từ khoá tìm kiếm một mình không đủ để coi là ngách (nó chỉ cho biết đã gõ gì, không cho biết kết quả là gì). Từ `3D动画` đứng một mình bị bỏ khỏi `niche_terms` vì khớp cả video súng và kỹ thuật.

**Chạy mỗi giờ đổi ba ngân sách**, nên các việc nặng chạy thưa hơn (giờ tính theo giờ Việt Nam; chạy tay luôn làm đủ):

| Việc | Chu kỳ | Tính toán | Nếu cứ mỗi giờ |
| --- | --- | --- | --- |
| Tìm từ khoá YouTube | `youtube_search_every_hours` = 6 | 8 từ khoá × 100 đơn vị × 4 lần = 3.200 / 10.000 đơn vị mỗi ngày | 19.200: vượt hạn mức |
| Vẽ và upload biểu đồ | `analysis_every_hours` = 3 | 8 ảnh × 8 lần = 64 ảnh mỗi ngày | 192 ảnh mỗi ngày lên image host |
| Giữ snapshot và candidate | `snapshot_ttl_days` = 14 | ~150 video × 24 lần × 14 ngày ≈ 50 nghìn hàng | 90 ngày sẽ vượt gói Free 500 MB |

Giờ không tìm YouTube vẫn đọc Bilibili (không tốn quota), nên danh sách hot luôn mới. Snapshot theo giờ cho vận tốc và gia tốc view tốt hơn nhiều so với một lần mỗi ngày.

**Thời lượng và số phần.** Bilibili báo thời lượng tìm kiếm là *tổng các phần* (分P), nhưng trình phát mở phần 1. Đo ngày 31/10/2026 trên 10 video hot: tổng khớp tuyệt đối với tìm kiếm, nhưng 4 video nhiều phần, ví dụ video 9 giờ 38 phút có phần 1 chỉ 7 phút, video 46 giờ gồm 18 phần mà phần 1 dài 1 giờ 56. Vì vậy mỗi video hot được hỏi `x/player/pagelist` (nhẹ, không bị chặn như `view`) để ghi `parts` và `first_part_sec`; tổng các phần là `duration_sec`. Video có tổng thực tế dưới `min_duration_sec` bị bỏ và một ứng viên dự phòng (thêm 5) thế chỗ. Hỏi không được thì hàng đó vẫn hiện nhưng không có số phần, không đoán.

**Danh sách hot.** Mỗi lần chạy ghi vào `hot_videos` tối đa 10 video Bilibili hot nhất theo độ ưu tiên (`kind = video`) và 10 series 国创 đứng đầu bảng xếp hạng sống của Bilibili (`kind = series`, ví dụ 灵笼 第二季). Đo ngày 31/10/2026: bảng xếp hạng *video* theo từng danh mục (`ranking/v2` với `rid` khác 0) đã đứng im từ tháng 3/2025, mọi mục cũ hơn 576 ngày, nên không dùng; chỉ bảng series còn sống. Bảng phẳng, có tiêu đề, link, kênh, lượt xem, thời lượng, cờ ngách. estfstudio đọc bảng này cho `/analysis`; nó không phụ thuộc `ideas` vì các lần chạy theo giờ thường không có ý tưởng mới (video đã đề xuất trong 90 ngày thì bị loại).

**Tám biểu đồ** (ảnh PNG 1200×675 lên image host, `media.kind = 'analysis'`, có `caption` và `position`; mỗi ảnh ghi giờ chạy trong hình nên không bao giờ trùng `sha256` với lần khác):

| Vị trí | Biểu đồ | Đọc để biết |
| --- | --- | --- |
| 1 | Video đang hot | Thẻ xếp hạng 8 video ưu tiên cao nhất, huy hiệu nền tảng và ngách |
| 2 | Tăng trưởng lượt xem của video hot | Lượt xem tăng thêm kể từ lần đo đầu của 3 video hot tăng nhanh nhất, đọc từ `snapshots` (đo mỗi giờ); cuối mỗi đường là số lượt xem mỗi giờ |
| 3 | Lượt xem và mức vượt kênh | Mỗi chấm là một video: lượt xem và z-score trong nền tảng của nó; vạch đứt là ngưỡng θ thật, vòng vàng là video hot |
| 4 | Tỉ trọng nền tảng | Bilibili và YouTube chiếm bao nhiêu video và lượt xem |
| 5 | Thời lượng video | Số video theo nhóm thời lượng; từ 4 giờ trở lên là tuyển tập |
| 6 | Giờ đăng | Khung giờ đăng nhiều video (giờ Việt Nam) |
| 7 | Từ khoá hiệu quả nhất | Từ khoá cho lượt xem trung vị cao |
| 8 | Các lần chạy gần đây | Hai khung chung trục thời gian: số video thu được và số video hot của từng lần chạy |

Mỗi biểu đồ tự giải thích cho người không quen thống kê: dòng phụ đề trong ảnh nói một điểm, một cột hay một đường nghĩa là gì; `caption` (hiện dưới ảnh trong Telegram) có tên biểu đồ, cách đọc và điều lần chạy này cho thấy, ví dụ video tăng nhanh nhất và bao nhiêu lượt mỗi giờ. Số được viết kiểu Việt (1,2 triệu, 45 nghìn).

Biểu đồ phân bố z-score đã bỏ (31/10/2026): người đọc không rút ra được việc cần làm, và vạch "ngưỡng" của nó thật ra là z thấp nhất trong nhóm đã vượt, không phải θ. Không biểu đồ nào dùng hai trục dọc: hai đại lượng khác thang được vẽ thành hai khung. Đường tăng trưởng chỉ vẽ 3 video vì ba màu xanh dương, cam, xanh ngọc là bộ lớn nhất vẫn phân biệt được với mọi người đọc, kể cả người mù màu, trên nền panel.

Bảng màu theo kiểu dashboard Power BI: nền navy đậm, panel sáng hơn một chút, điểm nhấn teal, xanh dương, tím, vàng hổ phách; thanh biểu đồ chuyển màu teal sang tím, YouTube màu san hô và Bilibili màu cyan. Mã màu nằm ở đầu `infrastructure/chart.py`, đổi một chỗ là đổi cả tám ảnh. Biểu đồ không đủ dữ liệu (dưới 5 video, chưa có video dài, mới chạy 1–2 lần) bị bỏ chứ không vẽ rỗng. Ảnh lỗi chỉ mất ảnh đó, không bao giờ làm hỏng run. Runner không có font Hán thì workflow cài `fonts-noto-cjk`.

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
| `channel_avg_views` | float | không | μ kênh trong `performance_ratio`; thiếu cột này Z-Score vô nghĩa. Kênh Bilibili: số người theo dõi | `5000.0` |
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
