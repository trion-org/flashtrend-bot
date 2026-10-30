# Các bảng điểm: candidates, ideas, embeddings, feedback chứa gì? {#bang-diem}

Bốn bảng giữ **kết quả tính toán**: `candidates` là điểm L1 của **mọi** video trong cohort một run, `ideas` chỉ giữ **leader** sau khi gộp cosine (đây là bảng estfstudio đọc), `embeddings` giữ vector 384 chiều mới nhất của mỗi video, `feedback` giữ nhãn người dùng gắn cho từng idea.

- Z-Score phụ thuộc cohort nên chỉ sống ở `candidates`: cùng một video, run khác thì Z khác.[](source:idea)
- `ideas` sao chép số liệu từ `candidates` lúc chốt và thêm tên kênh, để estfstudio đọc một bảng mà không cần join.
- Trong mẫu, cohort chỉ có 5 video (< `min_cohort_n` = 20) nên θ được nới từ 1.5 xuống 0.5: 3 video qua, 2 leader.

@answer scope="Schema v1 (bản thiết kế) · số liệu tính lại từ công thức · cosine trong mẫu là minh hoạ, chưa chạy model"
@meta locale=vi
@source idea title="Bản thiết kế FlashTrend (2026-10-28) — §4.2 candidates, ideas, embeddings, feedback"
@source pgvector title="pgvector — vector type, HNSW, distance operators" url=https://github.com/pgvector/pgvector

## Cohort mẫu được chấm thế nào? {#cohort}

Cohort `run_20261028T071700`: μ = 18,7156 và σ = 16,2272 trên `performance_ratio`; median engagement thô m = 0,0938.

| Video | ratio | z_score | engagement | time_decay (tuổi) | viral_score | passed_z (θ = 0.5) |
| --- | --- | --- | --- | --- | --- | --- |
| `yt_vid001` | 30,00 | 0,695 | 0,1002 | 0,768 (5,3 h) | 27,49 | true {good:Qua} |
| `yt_vid002` | 30,00 | 0,695 | 0,0938 | 0,645 (8,8 h) | 21,20 | true {good:Qua} |
| `yt_vid003` | 0,80 | −1,104 | 0,0704 | 0,163 (36,3 h) | 0,08 | false {bad:Loại} |
| `yt_vid004` | 31,67 | 0,798 | 0,1082 | 0,443 (16,3 h) | 17,39 | true {good:Qua} |
| `yt_vid005` | 1,11 | −1,085 | 0,0701 | 0,223 (30,0 h) | 0,25 | false {bad:Loại} |

Kiểm tra `yt_vid001`: Z = (30 − 18,7156) / 16,2272 = 0,695; engagement = (9.200·1,5 + 410·3 + 1.000·0,0938) / 151.000 = 0,1002; viral = 11,918 · 0,1002 · 30 · 0,768 = 27,49.

@callout level=warning title="Với θ = 1.5, cohort này không giữ video nào"
Ba video có ratio ~30 chiếm đa số nên kéo μ lên; Z lớn nhất chỉ 0,80. Đây đúng là lý do thiết kế đặt `min_cohort_n`.
Production cần 20+ video mỗi run; mẫu dùng θ = 0.5 như bản demo trong nghiên cứu ban đầu và ghi `runs.z_threshold_used`.

## candidates — điểm L1 của mọi video {#candidates}

Khoá `(run_id, video_id)`, xoá theo run (`CASCADE`). Các cột `title`, `url`, `platform` được sao chép lúc chấm vì tiêu đề có thể đổi sau.

| Field | Kiểu | Null | Mục đích | Mẫu (`yt_vid001`) |
| --- | --- | --- | --- | --- |
| `run_id` | text PK, FK → `runs` | không | Cohort tính μ, σ | `run_20261028T071700` |
| `video_id` | text PK, FK → `videos` | không | Video được chấm | `yt_vid001` |
| `platform` | `platform_t` | không | Sao chép để lọc không cần join | `youtube` |
| `title` | text | không | Tiêu đề lúc chấm | `Cách tạo Bot Python lấy dữ liệu TikTok tự động` |
| `url` | text | không | Link lúc chấm | `https://www.youtube.com/watch?v=vid001` |
| `channel_id` | text FK → `channels` | không | Truy baseline | `yt_UC_pythonlab` |
| `views` | bigint | không | Đầu vào ratio và `log1p(views)` | `150000` |
| `likes` | bigint | không | Đầu vào engagement | `9200` |
| `comments` | bigint | không | Đầu vào engagement | `410` |
| `age_hours` | float | không | `captured_at − published_at` theo giờ | `5.2867` |
| `channel_avg_views` | float | không | μ kênh **lúc chấm** (không đọc lại cache đã đổi) | `5000.0` |
| `performance_ratio` | float | không | `views / (channel_avg_views + ε)` | `30.0` |
| `z_score` | float | không | `(ratio − μ) / σ` của cohort | `0.6954` |
| `engagement` | float | không | `(likes·1.5 + comments·3 + C·m) / (views + C)` | `0.1002` |
| `time_decay` | float | không | `exp(−λ · age_hours)` | `0.7677` |
| `velocity` | float | có | Views/giờ so với snapshot trước; null ở lần đầu | `null` |
| `acceleration` | float | có | Δvelocity/Δt; cần 3 snapshot | `null` |
| `early_flag` | boolean | không | `velocity` cao **và** `acceleration > 0` (B4) | `false` |
| `viral_score` | float | không | `log1p(views) · engagement · ratio · decay` — khoá xếp hạng L1 | `27.493` |
| `passed_z` | boolean | không | `z_score >= θ đang dùng`; chỉ outlier vào L2 | `true` |
| `query_tag` | text | có | `chart` hoặc từ khoá A2 đã tìm ra video | `python bot` |
| `expire_at` | timestamptz | không | Cùng TTL với snapshot | `2027-01-26T07:17:12+07:00` |

Ở run `run_20261028T181700`, hàng của `yt_vid001` có `velocity = 23637.6` (xem bảng `snapshots`), `acceleration = null`, `early_flag = false`.

## ideas — leader cho estfstudio {#ideas}

Chỉ video thắng cụm mới được insert. `llm` bắt buộc khác null khi `runs.status = 'ok'`; `status` là cột duy nhất estfstudio được sửa.

| Field | Kiểu | Null | Mục đích | Mẫu `yt_vid001` | Mẫu `yt_vid004` |
| --- | --- | --- | --- | --- | --- |
| `run_id` | text PK, FK → `runs` | không | Digest của run nào | `run_20261028T071700` | cùng |
| `video_id` | text PK, FK → `videos` | không | Leader (gộp `yt_vid002` vào `yt_vid001`) | `yt_vid001` | `yt_vid004` |
| `platform` | `platform_t` | không | Sao chép | `youtube` | `youtube` |
| `title` | text | không | Hiện trong digest | `Cách tạo Bot Python…` | `Bí quyết quản lý tài chính…` |
| `url` | text | không | Nút xem nguồn / lồng tiếng | `…watch?v=vid001` | `…watch?v=vid004` |
| `published_at` | timestamptz | không | Hiện tuổi video | `2026-10-28T02:00:00+07:00` | `2026-10-27T15:00:00+07:00` |
| `views` / `likes` / `comments` | bigint | không | Sao chép lúc chốt | 150.000 / 9.200 / 410 | 95.000 / 6.100 / 380 |
| `channel_title` | text | không | Tên kênh, đọc không cần join `channels` | `Python Lab VN` | `Tài chính 20s` |
| `channel_id` | text FK → `channels` | không | Truy kênh | `yt_UC_pythonlab` | `yt_UC_fin20s` |
| `channel_avg_views` | float | không | Sao chép | `5000.0` | `3000.0` |
| `performance_ratio` | float | không | Sao chép | `30.0` | `31.6667` |
| `z_score` | float | không | Sao chép | `0.6954` | `0.7981` |
| `engagement` | float | không | Sao chép | `0.1002` | `0.1082` |
| `time_decay` | float | không | Sao chép | `0.7677` | `0.4429` |
| `viral_score` | float | không | `ORDER BY viral_score DESC` trong digest | `27.493` | `17.389` |
| `duplicates_count` | int | không | Số video cùng cụm, không tính leader | `1` | `0` |
| `novelty_score` | float | có | `1 − max cosine` với lịch sử 90 ngày (C3); 1.0 = chưa từng đề xuất | `1.0` | `1.0` |
| `cluster_id` | text | không | `{run_id}_c{n}` để debug cụm | `run_20261028T071700_c0` | `…_c1` |
| `llm` | jsonb | có | Kết quả Gemini (bảng dưới) | xem bên dưới | xem bên dưới |
| `status` | `idea_status_t` | không | `new` → `seen` / `used` / `rejected` (estfstudio ghi) | `used` | `seen` |
| `created_at` | timestamptz | không | Lúc insert sau L2 | `2026-10-28T07:18:35+07:00` | cùng |

| Khoá `llm` | Kiểu | Mục đích | Mẫu `yt_vid001` |
| --- | --- | --- | --- |
| `summary` | string | Tóm tắt tối đa 3 câu | Hướng dẫn bot Python lấy metadata TikTok, không tải file. |
| `why_viral` | string | Cơ chế lan truyền, không phải "vì hay" | Kênh 8k sub đạt 150k views; tiêu đề hứa một quy trình làm theo được. |
| `hook` | string | 3–5 giây mở đầu | Bạn đang copy TikTok bằng tay từng link? |
| `angles` | string[3] | Ba góc làm lại, không paraphrase tiêu đề | So sánh yt-dlp và API chính thức · Checklist điều khoản khi lấy metadata · Shorts: pipeline Python trong 60 giây |
| `format` | string | `long` · `short` · `compilation` · `review` | `review` |
| `risk` | string | `copyright` · `reused` · `kids` · `sensitive` | `reused` nếu bê nguyên kịch bản |

```json title="ideas.llm — mẫu yt_vid004"
{
  "summary": "Năm quy tắc chia thu nhập cho sinh viên, có bảng tính mẫu.",
  "why_viral": "Kênh 4,1k sub đạt 95k views; chủ đề đúng mùa nhập học, tiêu đề có năm 2026.",
  "hook": "Tiền trợ cấp hết trước ngày 15 mỗi tháng?",
  "angles": ["Thử sống 30 ngày với 3 triệu", "So sánh 50/30/20 và chia lọ", "Sai lầm tài chính năm nhất"],
  "format": "long",
  "risk": "sensitive"
}
```

## embeddings — vector mới nhất của mỗi video {#embeddings}

Quan hệ 1:1 với `videos`. Chiếm nhiều dung lượng nhất (~3,5 KB/hàng kể cả index HNSW), nên TTL của bảng này quyết định quota.

| Field | Kiểu | Null | Mục đích | Mẫu |
| --- | --- | --- | --- | --- |
| `video_id` | text PK, FK → `videos.id` | không | Video của vector | `yt_vid001` |
| `model` | text, mặc định `all-MiniLM-L6-v2` | không | Phải trùng model lúc encode và lúc so | `all-MiniLM-L6-v2` |
| `dim` | int, `check (dim = 384)` | không | Sai số chiều thì không insert được | `384` |
| `text_hash` | text | không | sha256 của văn bản đã encode; trùng thì bỏ qua encode | `sha256:6f2c1a9e…a4b5c6` |
| `source` | text, `title` hoặc `title+transcript` | không | Văn bản đầu vào: tiêu đề (MVP) hay kèm phụ đề (P1) | `title` |
| `embedding` | `vector(384)` | không | Đầu vào HNSW `vector_cosine_ops`; `<=>` trả khoảng cách = 1 − similarity | `[0.0214, -0.0881, 0.0533, …]` |
| `updated_at` | timestamptz | không | Lọc lịch sử 90 ngày cho C3 | `2026-10-28T07:18:20+07:00` |

| Cosine (minh hoạ) | `yt_vid001` | `yt_vid002` | `yt_vid004` |
| --- | --- | --- | --- |
| `yt_vid001` | 1,00 | 0,81 {good:Cùng cụm} | 0,12 |
| `yt_vid002` | 0,81 | 1,00 | 0,10 |
| `yt_vid004` | 0,12 | 0,10 | 1,00 |

0,81 ≥ τ = 0,70 nên `yt_vid002` vào cụm của `yt_vid001` (viral 27,49 > 21,20 → `yt_vid001` làm leader). Toán tử pgvector theo tài liệu dự án.[](source:pgvector)

```sql title="C3 — so với lịch sử 90 ngày, chạy trên server (không kéo vector về)"
select video_id, 1 - (embedding <=> $1::vector) as cosine_sim
from embeddings
where updated_at >= now() - interval '90 days'
order by embedding <=> $1::vector
limit 5;
```

```python title="Ghi vector bằng supabase-py (service_role, chỉ trên Actions)"
from supabase import create_client

supabase = create_client(url, service_role_key)
embedding_values = model.encode([title])[0].tolist()  # len == 384
supabase.table("embeddings").upsert({
    "video_id": "yt_vid001",
    "model": "all-MiniLM-L6-v2",
    "dim": 384,
    "text_hash": text_hash,          # sha256 trùng lần trước thì bỏ qua encode
    "source": "title",
    "embedding": embedding_values,
}).execute()
```

## feedback — nhãn để đo Precision@5 {#feedback}

Một nhãn cho mỗi idea (khoá trùng `ideas`). estfstudio ghi khi bạn bấm 👍 / 👎 trên tin digest.

| Field | Kiểu | Null | Mục đích | Mẫu |
| --- | --- | --- | --- | --- |
| `run_id` | text PK, FK kép → `ideas` | không | Digest của ngày nào | `run_20261028T071700` |
| `video_id` | text PK, FK kép → `ideas` | không | Leader được gắn nhãn | `yt_vid001` |
| `label` | `feedback_label_t` | không | `useful` / `not_useful` tính Precision@5; `duplicate`, `used` để kiểm tra | `useful` |
| `labeled_at` | timestamptz | không | Mục tiêu: gắn nhãn trong 7 ngày | `2026-10-28T17:05:00+07:00` |
| `note` | text | có | Góc sẽ làm hoặc lý do bỏ; không chứa dữ liệu cá nhân | Sẽ làm góc so sánh yt-dlp và API chính thức. |

| Hàng mẫu | label | note |
| --- | --- | --- |
| `yt_vid001` | useful | Sẽ làm góc so sánh yt-dlp và API chính thức. |
| `yt_vid004` | not_useful | Ngoài ngách kênh. |

Precision@5 của một ngày = số `useful` trong tối đa 5 idea đầu / số idea đó. Mẫu có 2 idea, 1 useful → 1/2 = 0,5 (mục tiêu ≥ 0,4).
