# FlashTrend chấm điểm một video thế nào? {#thuat-toan}

Một video được giữ khi nó **vượt trội so với chính kênh của nó** (Z-Score của `views / channel_avg_views` ≥ 1.5 trong cohort lần chạy, nới xuống 0.5 khi cohort dưới 20 video), rồi được xếp hạng bằng `viral_score = log1p(views) · engagement · performance_ratio · time_decay`.

- Views tuyệt đối thiên vị kênh lớn; tỉ lệ so với baseline kênh mới cho thấy đột biến.[](source:idea)
- Mô hình nhân: thiếu một yếu tố (không tương tác, quá cũ, đúng mức thường của kênh) thì điểm sụp.
- `log1p(views)` giữ một video triệu view không nuốt hết bảng xếp hạng.
- Sau lớp số, cosine trên embedding gộp các video cùng ý tưởng, chỉ giữ một leader.

@answer scope="Công thức v1 của bản thiết kế · tham số mặc định của app_config · số mẫu tính lại từ chính công thức"
@meta locale=vi
@source idea title="Bản thiết kế FlashTrend (2026-10-28) — mục B, C, E"
@source minilm title="all-MiniLM-L6-v2 (384 chiều)" url=https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2
@source pgvector title="pgvector — toán tử khoảng cách" url=https://github.com/pgvector/pgvector

## Bốn đại lượng nào tạo nên điểm? {#dai-luong}

| Đại lượng | Công thức | Tham số (`app_config`) |
| --- | --- | --- |
| `performance_ratio` | `views / (channel_avg_views + ε)` | ε = 1e-5 |
| `z_score` | `(ratio − μ_cohort) / σ_cohort` | `z_threshold` = 1.5 |
| `engagement` | `(likes·1.5 + comments·3 + C·m) / (views + C)` | `bayes_c` C = 1000, m = median engagement của run |
| `time_decay` | `exp(−λ · age_hours)` | `decay_lambda` λ = 0.05, nửa đời ≈ 13.9 giờ |
| `viral_score` | `log1p(views) · engagement · ratio · decay` | khoá xếp hạng |

Nửa đời là `ln 2 / λ = 0.693 / 0.05 = 13.9` giờ. Engagement làm mượt Bayes: video ít view bị kéo về prior `m` thay vì nhảy lên 1.0 vì một vài like.

@callout level=warning title="Cohort nhỏ làm σ không ổn định"
Nếu một run có ít hơn `min_cohort_n` = 20 video, σ của Z-Score không đáng tin.
Khi đó ghi `cohort_n` thật vào `runs` và nới ngưỡng hoặc bỏ lọc Z, đừng âm thầm giữ 1.5.

## Ví dụ: năm video trong cùng một run {#vi-du}

Cohort `run_20261028T071700` có 5 video: μ = 18,7156 và σ = 16,2272 trên `performance_ratio`; median engagement thô m = 0,0938. Vì 5 < `min_cohort_n` = 20, θ được nới xuống 0.5.

| Video | Views / avg kênh | ratio | Z | engagement | decay | viral_score |
| --- | --- | --- | --- | --- | --- | --- |
| `yt_vid001` (kênh 8k sub) | 150.000 / 5.000 | 30,00 | 0,70 {good:Giữ} | 0,1002 | 0,768 (5,3 h) | 27,49 |
| `yt_vid002` (trùng ý vid001) | 120.000 / 4.000 | 30,00 | 0,70 {good:Giữ} | 0,0938 | 0,645 (8,8 h) | 21,20 |
| `yt_vid003` (vlog ẩm thực) | 8.000 / 10.000 | 0,80 | −1,10 {bad:Loại} | 0,0704 | 0,163 (36,3 h) | 0,08 |
| `yt_vid004` (tài chính SV) | 95.000 / 3.000 | 31,67 | 0,80 {good:Giữ} | 0,1082 | 0,443 (16,3 h) | 17,39 |
| `yt_vid005` (kênh nhạc lớn) | 2.000.000 / 1.800.000 | 1,11 | −1,08 {bad:Loại} | 0,0701 | 0,223 (30,0 h) | 0,25 |

Kiểm tra `yt_vid001`: Z = (30 − 18,7156) / 16,2272 = 0,695; engagement = (9.200·1,5 + 410·3 + 1.000·0,0938) / 151.000 = 0,1002; viral = 11,918 · 0,1002 · 30 · 0,768 = 27,49. `yt_vid005` có 2 triệu views nhưng chỉ bằng 1,11 lần mức thường của kênh, nên bị loại.

@callout level=note title="Số mẫu đã được tính lại"
Bản thiết kế gốc ghi μ = 8,2444, σ = 12,1101, engagement 0,0703, viral_score 19,412 — không khớp chính 5 video mẫu của nó.
Mọi trang dùng số tính lại từ công thức ở trên; khi viết test, lấy số trên trang này làm chuẩn.

## Bắt sóng sớm: vận tốc, gia tốc, làm mượt {#van-toc}

B4 cần ít nhất 2 snapshot (vận tốc) hoặc 3 snapshot (gia tốc) của cùng video; B5 cần 5–7 điểm mới có ích.

| Snapshot `yt_vid001` | captured_at | views | vận tốc v (views/giờ) | gia tốc a | EMA α = 0,3 |
| --- | --- | --- | --- | --- | --- |
| Lần 1 | 28/10 07:17 | 150.000 | — | — | 150.000 |
| Lần 2 | 28/10 18:17 | 410.000 | 23.638 | — | 228.000 |
| Lần 3 (minh hoạ) | 29/10 07:17 | 600.000 | 14.615 | −694 {caution:Chậm lại} | 339.600 |

v₂ = 260.000 / 10,9994 h ≈ 23.638 (07:17:12 → 18:17:10); v₃ = 190.000 / 13,0 h ≈ 14.615 (18:17 → 07:17 hôm sau); a₃ = (14.615 − 23.638) / 13,0 ≈ −694 views/giờ². `early_flag` chỉ bật khi v cao **và** a > 0, nên ở lần 3 vẫn `false`: video đã qua đỉnh tăng tốc. EMA: S₂ = 0,3·410.000 + 0,7·150.000 = 228.000; S₃ = 0,3·600.000 + 0,7·228.000 = 339.600.

"v cao" nghĩa là vận tốc từ median vận tốc của cohort trở lên (video chưa có snapshot trước không có vận tốc, nên không được cờ).

Tuỳ chọn ở B6: nhân thêm `max(1, 1 + k·acceleration)` để thưởng video đang tăng tốc.

## Hai video "cùng ý" được gộp thế nào? {#cosine span=12}

@workflow id=dedup title="Gộp ý tưởng trùng bằng cosine"
| outl | Outlier từ L1 | backend |
| emb | Mã hoá MiniLM | backend |
| clus | Gom cụm cos ≥ 0.70 | backend |
| hist | So lịch sử 90 ngày | security |
| lead | Giữ leader | database |
| drop | Bỏ ý cũ | external |
| outl > emb | |
| emb > clus | |
| clus > hist | |
| hist > drop | trùng |
| hist > lead | mới | emphasis |

@steps id=dedup-steps
| d-emb | Mã hoá MiniLM | `all-MiniLM-L6-v2`, 384 chiều, model ~90 MB chạy CPU; `sha256(title)` trùng lần trước thì dùng lại vector cũ. |
| d-clus | Gom cụm cos ≥ 0.70 | Greedy: video điểm cao nhất làm leader, các video cos ≥ 0.70 với nó vào `duplicates_count`. |
| d-hist | So lịch sử 90 ngày | Truy vấn pgvector `1 − (embedding <=> $1)` trên 90 ngày; ≥ 0.80 thì bỏ (C3, P1). |
| d-lead | Giữ leader | Chỉ leader vào bảng `ideas`, kèm `cluster_id` và `novelty_score = 1 − max_cos`. |

Toán tử `<=>` của pgvector trả **khoảng cách** cosine, tức `1 − similarity`.[](source:pgvector) Model 384 chiều theo trang model.[](source:minilm)

## Đồ thị chủ đề (P2–P3) {#do-thi}

D1 dựng đồ thị vô hướng có trọng số: nút là từ khoá/hashtag, cạnh nối hai từ cùng xuất hiện trong một video đã qua L1. Từ có độ trung tâm cao là "cầu nối" của xu hướng tuần đó.

| Từ (minh hoạ) | Video chứa | Bậc (số từ nối tới) | Vai trò |
| --- | --- | --- | --- |
| `python` | vid001, vid002 | 3 (bot, tiktok, crawl) | Cầu nối {good:Trung tâm} |
| `tiktok` | vid001, vid002 | 3 (python, bot, crawl) | Cầu nối |
| `bot` | vid001, vid002 | 3 | Cầu nối |
| `tài chính` | vid004 | 1 (sinh viên) | Cụm riêng |

Đầu ra dự kiến: `bridge_topics[]` (top-k theo PageRank) và JSON thống kê đồ thị. D2 chiếu đồ thị hai phía kênh × chủ đề để thấy nhiều kênh cùng đẩy một motif (P3).

## Gemini được phép làm gì? {#gemini}

Python làm mọi việc đếm, gọi API và tính toán; Gemini chỉ đọc 3–5 leader đã lọc và trả JSON theo hợp đồng.

| Khoá `ideas.llm` | Nội dung |
| --- | --- |
| `summary` | Tóm tắt, tối đa 3 câu |
| `why_viral` | Cơ chế lan truyền, không phải "vì hay" |
| `hook` | 3–5 giây mở đầu |
| `angles` | Đúng 3 góc làm lại, không paraphrase tiêu đề |
| `format` | `long` · `short` · `compilation` · `review` |
| `risk` | `copyright` · `reused` · `kids` · `sensitive` |

- [ ] JSON sai schema thì thử lại một lần, vẫn sai thì `runs.status = error`.
- [ ] Gemini lỗi vẫn ghi L1/L2 với `llm = null`; estfstudio chỉ đọc run `ok`.
- [ ] Mỗi tuần soát tay 20 cặp cùng/khác ý để chỉnh ngưỡng 0.70.
- [ ] E3 (P2): từ cùng `llm`, sinh dàn ý Shorts 45–60 giây gồm hook, 3 nhịp, lời kêu gọi — nén lại và mở hook mới, không cắt 60 giây đầu.
