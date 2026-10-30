# FlashTrend làm gì và chạy ở đâu? {#tong-quan}

FlashTrend là **bộ lọc thống kê–ngữ nghĩa** chạy 1–2 lần/ngày trên GitHub Actions: lấy video YouTube, giữ video vượt trội so với chính kênh của nó, gộp ý tưởng trùng, nhờ Gemini viết góc làm lại, rồi ghi vào Supabase để **estfstudio** đọc.

- Không reup, không tải video ở MVP: chỉ đọc metadata qua API chính thức.[](source:idea)
- Supabase là nguồn sự thật duy nhất; JSON/PNG trên Actions chỉ để debug.[](source:idea)
- Repo này không có Telegram: bot của estfstudio đọc thẳng cùng project Supabase.
- Ảnh tự tạo (biểu đồ run, ảnh bìa) được upload qua một image host bên thứ ba; Supabase chỉ giữ link. Thumbnail YouTube dùng thẳng link `i.ytimg.com`, không upload.

@answer scope="Thiết kế MVP, 2026-10-28 · Phase 1 đã có mã (2026-10-31), chưa chạy với khoá YouTube/Gemini thật · số liệu quota là giới hạn công bố"
@meta locale=vi
@source idea title="Bản thiết kế FlashTrend (2026-10-28) — Scientific Idea Catalog"
@source setup title="Hướng dẫn cài đặt dịch vụ (2026-10-28) — Third-party setup"
@source yt-quota title="YouTube Data API — quota cost" url=https://developers.google.com/youtube/v3/determine_quota_cost
@source gh-billing title="GitHub Actions billing" url=https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions

## Bài toán và câu hỏi nghiên cứu {#bai-toan}

Người làm nội dung không thiếu video, mà thiếu **tín hiệu sớm**: video nào thật sự đột biến, ý tưởng nào không trùng, và góc làm lại nào đủ khác để không dính Content ID hay reused content.

Câu hỏi nghiên cứu: kết hợp API chính thức, trình trích metadata, toán (thống kê, đại số tuyến tính, giải tích, đồ thị) và Gemini thế nào để mỗi ngày ghi vào Supabase một tập ý tưởng **độc đáo và có xác suất viral cao**, cho estfstudio đọc và gửi Telegram?

| Giả thuyết | Phát biểu |
| --- | --- |
| H0 (giả thuyết không) | Lọc theo `views` tuyệt đối là đủ tốt |
| H1 (giả thuyết làm việc) | Z-Score hiệu suất tương đối + cosine dedup + vận tốc tăng trưởng cho tín hiệu tốt hơn views thô {good:Kiểm bằng Precision@5} |

| Hạng mục | Quyết định |
| --- | --- |
| Tên / repo / tiền tố | FlashTrend · `flashtrend-bot` · F (Flash = bắt xu hướng nhanh) |
| Mục tiêu | Phát hiện video đang / sắp viral, lọc ý tưởng độc đáo, (tuỳ chọn v2) biến thành nội dung mới và đăng YouTube theo lịch |
| Sản phẩm lõi (MVP) | Thu thập + chấm điểm + góc làm lại của Gemini → ghi Supabase |
| Bên đọc | estfstudio (repo riêng) đọc thẳng Supabase và gửi Telegram |
| Mở rộng (v2) | Lấy nguồn → biến đổi → upload/hẹn lịch qua YouTube Data API v3 |
| Chạy ở đâu | GitHub Actions, repo public + Secrets, 1–2 lần/ngày |
| Lưu ở đâu | Supabase (Postgres + pgvector) là nguồn sự thật; JSON/PNG chỉ là bản xuất |
| LLM | Gemini API bắt buộc (key Google AI Studio) |
| Ngôn ngữ | Python 3.12 trên Actions (mã chạy được từ 3.10; Google đã ngừng hỗ trợ 3.10) |
| Không làm ở MVP | Telegram trong repo này, reup nguyên bản, cào hàng loạt, LLM chạy local, GPU |
| Trạng thái | Đã khoá ý tưởng (2026-10-28); Phase 1 đã có mã và test (2026-10-31), chưa chạy thật với khoá dịch vụ |

## Những thành phần nào nói chuyện với nhau? {#thanh-phan span=12}

GitHub Actions là nơi duy nhất gọi API bên ngoài. estfstudio chỉ đọc và ghi trạng thái vào Supabase, không gọi YouTube hay Gemini của FlashTrend.

@architecture id=he-thong title="FlashTrend và các dịch vụ xung quanh"
| cron | GitHub Actions cron | cloud |
| yt | YouTube Data API | external |
| gem | Gemini API | external |
| img | Image host | external |
| db | Supabase Postgres | database |
| estf | estfstudio (Telegram) | backend |
| cron > yt | metadata |
| cron > gem | 3–5 ý tưởng |
| cron > img | PNG |
| cron > db | runs, ideas | emphasis |
| estf > db | đọc digest |

@steps id=he-thong-steps
| s-cron | GitHub Actions cron | Chạy lúc **07:17 giờ Việt Nam** hằng ngày (cron `17 0 * * *`: GitHub chỉ nhận cron theo UTC, 00:17 UTC = 07:17 giờ VN), có `workflow_dispatch` để chạy tay; timeout 10 phút. | he-thong | cron |
| s-yt | YouTube Data API | Chart `mostPopular` theo region + `search.list` theo từ khoá + baseline kênh. Chỉ cần API key. | he-thong | yt |
| s-gem | Gemini API | Chỉ đọc 3–5 ý tưởng đã lọc; trả JSON `summary`, `hook`, `angles[3]`, `risk`. | he-thong | gem |
| s-img | Image host | Upload biểu đồ của run, nhận URL công khai, ghi vào bảng `media`. | he-thong | img |
| s-db | Supabase Postgres | Postgres + pgvector, gói Free; RLS bật, không có policy cho `anon`. | he-thong | db |
| s-estf | estfstudio bot | Đọc run `ok` mới nhất, gửi Telegram, ghi `ideas.status` và `feedback`. | he-thong | estf |

## Một lần chạy đi qua những lớp nào? {#cac-lop}

Lớp rẻ chạy trước: Z-Score là O(n) và cắt phần lớn nhiễu trước khi phải mã hoá văn bản thành vector.

@workflow id=pipeline title="Năm lớp của một lần chạy"
| lane thu | Thu thập |
| lane loc | Lọc |
| lane ghi | Ghi |
| collect | Lấy video + kênh | external | thu |
| l1 | L1 Z-Score | backend | loc |
| l2 | L2 Cosine dedup | backend | loc |
| l3 | L3 Gemini | cloud | loc |
| store | Ghi Supabase | database | ghi |
| collect > l1 | |
| l1 > l2 | outlier |
| l2 > l3 | leader |
| l3 > store | llm | emphasis |

@steps id=pipeline-steps
| p-collect | Lấy video + kênh | A1 chart, A2 từ khoá, A3 `channel_avg_views` (cache 24 h trong bảng `channels`). | pipeline | collect |
| p-l1 | L1 Z-Score | `performance_ratio`, engagement Bayes, time-decay; giữ `z_score >= 1.5`. | pipeline | l1 |
| p-l2 | L2 Cosine dedup | Embedding MiniLM 384 chiều; cosine ≥ 0.70 thì chung cụm, giữ video điểm cao nhất. | pipeline | l2 |
| p-l3 | L3 Gemini | Viết tóm tắt, hook, 3 góc mới, rủi ro bản quyền vào `ideas.llm`. | pipeline | l3 |
| p-store | Ghi Supabase | `runs.status = ok` chỉ khi mọi idea có `llm` đủ schema; lỗi thì `error`. | pipeline | store |

Sau năm lớp của MVP còn hai lớp tuỳ chọn: **L4** (v2) lấy nguồn → biến đổi → hẹn lịch YouTube, và **L5** đồ thị độ trung tâm hashtag sau khi có đủ dữ liệu. Hai lớp đầu đi trước vì Z-Score O(n) cắt 80–90 % nhiễu trước bước mã hoá văn bản đắt hơn, hợp với CPU của Actions.

## MVP làm gì và cố ý không làm gì? {#pham-vi}

| Hạng mục | MVP | Để sau |
| --- | --- | --- |
| Nguồn video | YouTube API chính thức {good:P0} | TikTok/Facebook allowlist qua yt-dlp (P1) |
| Tải / đăng video | Không {good:An toàn} | Upload YouTube có lịch `publishAt` (P2) |
| Gemini | Bắt buộc | Chuyển video dài thành Shorts (P2) |
| Telegram | Không có trong repo | Thuộc estfstudio |
| Ảnh | Link trên image host bên thứ ba | Supabase Storage chỉ là phương án dự phòng |
| Hạ tầng | GitHub Actions public, $0 {good:$0} | — |

@callout level=note title="Vì sao repo public?"
Repo public được dùng phút Linux của Actions không giới hạn; private chỉ có 2.000 phút/tháng.[](source:gh-billing)
Secrets nằm trong GitHub Secrets nên public không làm lộ khoá, miễn là không hardcode.

## Giới hạn nào định hình thiết kế? {#gioi-han}

@facts
| Quota YouTube Data API | 10.000 unit/ngày; `search.list` tốn 100 unit, `videos.list` 1 unit |
| Supabase Free | 500 MB database, 5 GB egress/tháng, tạm dừng sau 1 tuần không hoạt động |
| Actions | `ubuntu-latest`, CPU, timeout 10 phút, mục tiêu dưới 3 phút |
| Gemini | Key Google AI Studio; lỗi Gemini → `runs.status = error`, vẫn giữ kết quả L1/L2 |

Chi phí quota YouTube theo bảng của Google.[](source:yt-quota) Ngân sách Supabase chi tiết nằm ở trang 03 · Dữ liệu.

## Mã nguồn sẽ chia thế nào? {#kien-truc}

```text title="Cấu trúc thư mục (clean slices, đã có mã)"
flashtrend-bot/
  domain/          # models, scoring (Z, engagement, decay, vận tốc), dedup (cosine), llm_contract, clock (giờ VN)
  application/     # digest (RunDigest: 7 bước ghi), check_media, ports
  infrastructure/  # youtube_api, supabase_store, gemini, embedder, image_host, chart, settings
  presentation/    # cli, log, output (điểm vào cho Actions: main.py)
  composition_root.py   # nơi duy nhất nối adapter vào use case
  sql/             # 01_core · 02_media · 03_functions · 04_seed_app_config · 05_search_tuning · 06_bilibili
  tests/           # unit + architecture + integration (PostgREST thật)
  output/          # bản xuất json + png tuỳ chọn (không phải nguồn sự thật)
  .github/workflows/  # flashtrend.yml · media-check.yml · ci.yml
  .env.example
```

- [ ] DTO khác entity; kiểm dữ liệu ở biên (URL allowlist, enum region, giới hạn số).
- [ ] Lỗi có cấu trúc: `code`, `message`, `details`, `trace_id`.
- [ ] Log không chứa token, cookie, email; luôn kèm `run_id`.

| Lớp | Lựa chọn | Lý do |
| --- | --- | --- |
| Ngôn ngữ | Python 3.12 | Google client đã ngừng hỗ trợ 3.10; yt-dlp |
| YouTube | `google-api-python-client` | Thư viện chính thức |
| Trích metadata | `yt-dlp` (chỉ metadata trước) | Đã dùng sẵn |
| Toán | `numpy`, `pandas` | Z-Score, điểm |
| Embedding | `sentence-transformers` MiniLM | CPU, ~90 MB, 5–10 giây |
| Biểu đồ | `matplotlib` | PNG debug / ảnh lên image host |
| LLM | Gemini API (Google AI Studio) | Bắt buộc; ghi `ideas.llm` |
| CSDL | Supabase (Postgres + pgvector) | Ghi: FlashTrend · đọc: estfstudio |
| Lịch | GitHub Actions | $0, không cần VPS |
| Thông báo | estfstudio (ngoài repo) | Bot Telegram đọc Supabase |

Không dùng mặc định: Zapier/Make, SaaS upload bên thứ ba, RapidAPI Douyin, Llama 8B trên runner.

## Bản đồ ý tưởng trên một trang {#ban-do}

| Nhóm | Ý tưởng | Khi nào |
| --- | --- | --- |
| Thu thập | A1 chart · A2 từ khoá ngách · A3 baseline kênh | MVP |
| Toán lớp 1 | B2 Z-Score + B1 / B3 / B6 | MVP |
| Toán lớp 2 | C2 cosine → ý tưởng duy nhất | MVP |
| Gemini | E2 tóm tắt / hook / góc mới (bắt buộc) | MVP |
| Tuỳ chọn | B4 vận tốc · D1 đồ thị | Sau MVP |
| Lưu | Supabase runs / ideas / snapshots + pgvector | MVP |
| Đọc | estfstudio (bot Telegram) | MVP |
| Về sau | A5/A6 lấy nguồn · G biến đổi · F đăng YouTube | v2 |

**Một câu định vị:** FlashTrend không phải bot reup; nó là bộ lọc thống kê–ngữ nghĩa chỉ ra *ý tưởng nào đáng làm hôm nay*.
