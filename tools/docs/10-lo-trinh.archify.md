# FlashTrend được xây theo thứ tự nào và đo thành công ra sao? {#lo-trinh}

Bốn phase, mỗi phase chỉ bắt đầu khi phase trước đo được: **Phase 1 ghi digest vào Supabase** là MVP; tải và đăng video (Phase 3) chỉ làm với nội dung có quyền. Thước đo chính là **Precision@5 ≥ 0.4**: trong 5 ý tưởng mỗi ngày, ít nhất 2 cái bạn thấy dùng được.

- Tối ưu ý tưởng dùng được, không tối ưu số lượng video.[](source:idea)
- Nhãn đánh giá đến từ estfstudio qua bảng `feedback`, nên vòng phản hồi đã có từ Phase 1.
- Mỗi ngưỡng (θ = 1.5, τ = 0.70, λ = 0.05) là giả định ban đầu, được chỉnh ở Phase 4.

@answer scope="Lộ trình trong bản thiết kế · chưa có ngày cam kết · Phase 0 (khoá spec) đã xong"
@meta locale=vi
@source idea title="Bản thiết kế FlashTrend (2026-10-28) — §7 Roadmap, §8 Evaluation, §9 Constraints"
@source estf-plan title="estfstudio — kế hoạch v1.1.0 dùng chung Supabase (mốc m1–m6)" url=https://github.com/trion-org/estfstudio/blob/develop/docs/v1.1.0/01-ke-hoach-supabase.html

## Mỗi phase giao gì? {#phase span=12}

@workflow id=phases title="Bốn phase sau khi khoá spec"
| p1 | Phase 1 Discover | backend |
| g1 | Cổng Precision@5 | security |
| p2 | Phase 2 Tín hiệu | backend |
| p3 | Phase 3 Đăng | cloud |
| p4 | Phase 4 Đồ thị | backend |
| p1 > g1 | |
| g1 > p2 | ≥ 0.4 | emphasis |
| p2 > p3 | có quyền |
| p2 > p4 | |

@steps id=phase-steps
| ph1 | Phase 1 Discover | Khoảng 1 tuần làm việc, sau Phase 0 (khoá spec: MVP = thu thập + chấm điểm + báo cáo, upload để Phase 3). YouTube chart + từ khoá + baseline kênh; B1–B3, B6; MiniLM + cosine; schema Supabase; Gemini → `ideas.llm`; Actions + cache + timeout, artifact JSON/PNG; ảnh qua image host; hợp đồng đọc cho estfstudio (run `ok` + ideas xếp hạng). |
| ph-g | Cổng Precision@5 | Đo trên nhãn `feedback` của 2 tuần digest trước khi mở rộng. Nhãn đến từ nút 👍 / 👎 của estfstudio (mốc m4 trong kế hoạch của nó), nên Phase 1 chỉ đo được sau m4.[](source:estf-plan) |
| ph2 | Phase 2 Tín hiệu | Snapshot → vận tốc và gia tốc view; transcript vào embedding; lọc trùng 90 ngày; TikTok/Facebook allowlist. |
| ph3 | Phase 3 Đăng | **Không làm trong repo này** (quyết định 2026-10-31: flashtrend-bot chỉ tìm từ khoá xu hướng; tải và đăng thuộc estfstudio). Thiết kế giữ lại ở trang 09: OAuth + test user; resumable upload với `publishAt`; biến đổi kiểu commentary/review, không dựa vào crop/flip. |
| ph4 | Phase 4 Đồ thị | PageRank hashtag; chỉnh θ, τ, λ trên ý tưởng đã làm và kết quả hit/miss. |

## Đo thế nào? {#do-luong}

| Chỉ số | Cách đo | Mục tiêu v1 |
| --- | --- | --- |
| Precision@5 | Bạn đánh `useful` / `not_useful` trong 7 ngày | ≥ 0.4 |
| Chất lượng gộp | Soát tay 20 cặp cùng ý / khác ý mỗi tuần | τ cho F1 cao nhất |
| Bắt sóng sớm | Video Z cao có tăng view trong 48 giờ sau không | Theo dõi bằng `snapshots` |
| Thời gian chạy | Wall time của Actions | Dưới 3 phút, tối đa 10 |
| Chi phí | API + Actions + Gemini + Supabase | $0 |
| Tác hại | Gậy bản quyền / reused content | 0 |

## Ràng buộc nào không được phá? {#rang-buoc}

| Ràng buộc | Lý do |
| --- | --- |
| Không reup nguyên bản Douyin/Bilibili | Reused content và bản quyền; chỉ commentary có luận điểm mới |
| Chỉ lấy metadata từ nguồn allowlist | Điều khoản TikTok/Facebook cấm quét toàn cục |
| Mọi upload khai `selfDeclaredMadeForKids` | COPPA; thiếu trường này API trả 400 |
| Không đăng dồn nhiều video giống nhau | Thuật toán chống spam của YouTube |
| Secret chỉ ở GitHub Secrets / `.env` | Repo public |
| Không thiết kế "tự public" trước OAuth Verification | App chưa xác minh bị khoá Private |
| Quota YouTube: ~6 upload/ngày | Hẹn lịch bằng `publishAt`, không spam `videos.insert` |
| Extractor Douyin/Bilibili gãy là bình thường | Ghim phiên bản yt-dlp, chỉ `-U` có kiểm soát |
| Bilibili chỉ tìm kiếm, ẩn danh, không cookie | Repo công khai; Bilibili chặn 412 ngẫu nhiên nên lỗi chỉ cảnh báo, không làm hỏng run |
| Không ghi token/cookie vào hàng Supabase | Chỉ `service_role` trên Actions; RLS chặn `anon` |

- [ ] Trả lời các câu hỏi mở bên dưới trước Phase 1.
- [ ] Gắn nhãn digest đều đặn để có Precision@5 sau 2 tuần.

## Giả định đang dùng {#gia-dinh}

| Giả định | Ghi chú |
| --- | --- |
| Tên FlashTrend, repo `flashtrend-bot` | Đã chốt |
| Máy local đã có `yt-dlp` | Theo nghiên cứu ban đầu |
| Ngày đầu chưa tải / upload | v2 mới làm |
| Region chính `VN`, có thể thêm `JP` | `app_config.regions` |
| Gemini bắt buộc, `llm_enabled = true` | Key Google AI Studio |
| Trọng số engagement và λ sẽ chỉnh sau | Chỉ đúng *hướng* (tương đối + ngữ nghĩa + thời gian), không tự nhận đúng tuyệt đối |
| Supabase Free; cron mỗi giờ giữ project không pause | `service_role` chỉ trong GitHub Secrets; snapshot giữ 14 ngày vì chạy dày gấp 24 lần |
| Telegram không nằm trong repo này | estfstudio đọc cùng project, theo kế hoạch v1.1.0 của nó[](source:estf-plan) |

## Câu hỏi còn mở {#cau-hoi}

| Câu hỏi | Mặc định nếu chưa trả lời |
| --- | --- |
| Ngách nội dung cụ thể (1–3 từ khoá gốc)? | Đã chọn (2026-10-31): hoạt hình 3D / AI Trung Quốc, 8 từ khoá tiếng Trung và tiếng Anh trong `sql/04_seed_app_config.sql`, tắt chart chung |
| Ngôn ngữ đầu ra (vi / ja / en)? | vi |
| estfstudio đã trỏ cùng project Supabase chưa? | Chưa có mã; dùng chung một project, estfstudio làm theo sáu mốc m1–m6 |
| Đã có kênh YouTube + test user OAuth chưa, hay chỉ báo cáo? | Chỉ báo cáo, không upload |
| Có nguồn được phép dùng ở v2 (kênh mình, CC, hợp đồng)? | Chưa; v2 chưa bắt đầu |
| Đã có project Supabase chưa, region nào (Singapore)? | Tạo mới ở region gần |
| Model Gemini? | `gemini-2.5-flash`, xác nhận trên AI Studio khi code |
