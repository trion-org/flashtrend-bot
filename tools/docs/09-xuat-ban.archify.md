# v2: lấy nguồn, biến đổi và đăng YouTube thế nào? {#xuat-ban}

v2 nối ba bước sau digest: **lấy nguồn** (yt-dlp cho Bilibili/Douyin, chỉ nội dung bạn được phép dùng), **biến đổi thành tác phẩm mới** (lồng tiếng Việt bằng estfstudio, review, tổng hợp có luận điểm) và **đăng bằng YouTube Data API** với `publishAt` để YouTube tự công khai đúng giờ. Không bước nào chạy ở MVP.

- Tự động hoá không giúp lách bản quyền: Content ID vẫn quét video ngay khi upload xong.[](source:research)
- Lật hình, crop, chỉnh tốc độ 1.02× **không** phải biện pháp hợp lệ và không được dùng để né bản quyền.
- Quota mặc định 10.000 unit/ngày, mỗi lần upload ~1.600 unit → tối đa khoảng 6 video/ngày.

@answer scope="Nghiên cứu ban đầu (YouTube upload, Bilibili/Douyin) + thiết kế A5–A6, F, G · thiết kế v2, chưa có mã · quota theo hội thoại research"
@meta locale=vi
@source research title="Ghi chép nghiên cứu ban đầu (2026-10-28) — upload YouTube, Bilibili/Douyin"
@source idea title="Bản thiết kế FlashTrend (2026-10-28) — A5, A6, F1–F4, G1–G5"
@source yt-insert title="YouTube Data API — videos.insert" url=https://developers.google.com/youtube/v3/docs/videos/insert
@source yt-quota title="YouTube Data API — quota cost" url=https://developers.google.com/youtube/v3/determine_quota_cost

## Luồng v2 từ idea tới video đã đăng {#luong span=12}

@workflow id=v2-flow title="Idea → nguồn → tác phẩm mới → YouTube"
| idea | Idea status=used | database |
| fetch | yt-dlp lấy nguồn | external |
| make | estfstudio lồng tiếng | backend |
| job | publish_jobs queued | database |
| up | videos.insert | cloud |
| yt | YouTube tự công khai | cloud |
| idea > fetch | |
| fetch > make | |
| make > job | |
| job > up | |
| up > yt | publishAt | emphasis |

@steps id=v2-steps
| s1 | Chọn idea | Bạn chọn một idea trong digest Telegram và đánh `used`; chỉ nguồn bạn có quyền hoặc được phép dùng mới đi tiếp. |
| s2 | Lấy nguồn | yt-dlp tải mp4 + JSON metadata; `--download-archive` ghi ID đã tải để không tải lại. |
| s3 | Biến đổi | estfstudio dịch và lồng tiếng Việt, thêm phụ đề, chương, phần bình luận; nhạc nền gốc thay bằng YouTube Audio Library. |
| s4 | Xếp hàng | Ghi một hàng `publish_jobs` trạng thái `queued`, kèm `publish_at` mong muốn. |
| s5 | Upload | Resumable upload `videos.insert` với `privacyStatus=private`, `publishAt`, `selfDeclaredMadeForKids`; ghi `youtube_video_id`, đổi `scheduled`. |
| s6 | Công khai | YouTube xử lý HD sẵn rồi tự chuyển Public đúng `publishAt`; không cần cron canh giờ. |

## Lấy nguồn từ Bilibili và Douyin {#nguon}

| Mục | Bilibili (A5) | Douyin (A6) |
| --- | --- | --- |
| Kiểu nội dung | Video dài, chia tập P1, P2…, ID dạng `BV…` | Video ngắn, link chia sẻ `v.douyin.com/…` |
| Rào cản | Luồng DASH tách video `.m4s` và audio `.m4s`; khách chỉ ~480p | Không có API công khai ngoài Trung Quốc; link chia sẻ dính watermark |
| Cách lấy | `yt-dlp --cookies cookies.txt -f "bv*+ba/b" --merge-output-format mp4 URL` | `yt-dlp URL`; lỗi thì `yt-dlp -U` rồi chạy lại |
| Xác thực | Cookie `SESSDATA` của tài khoản bạn (HD/1080p) | Thường không cần; cookie khi bị chặn |
| Công cụ khác | BBDown (.NET, playlist, phụ đề) | Thư viện cộng đồng, API thuê trên RapidAPI {caution:Dễ gãy} |
| Rủi ro | Cookie hết hạn; bản quyền MCN | Thuật toán chống cào đổi vài tháng một lần; nhạc trend có bản quyền |

```bash title="Lệnh yt-dlp dùng chung cho v2"
yt-dlp --cookies cookies.txt \
  -f "bv*+ba/b" --merge-output-format mp4 \
  --write-info-json --download-archive archive.txt \
  -o "%(extractor)s_%(id)s.%(ext)s" "URL"
```

Quy mô hàng trăm video/ngày trên một IP sẽ gặp CAPTCHA hoặc HTTP 403; v2 nhắm vài video/ngày nên không dùng proxy xoay vòng.

## Biến đổi thế nào là hợp lệ? {#bien-doi}

| Cách làm | Hợp lệ? | Ghi chú |
| --- | --- | --- |
| Lồng tiếng Việt + dịch phụ đề (estfstudio) | Có {good:Hợp lệ} | Tác phẩm mới có giá trị ngôn ngữ; ghi nguồn |
| Review / react có bình luận thật | Có {good:Hợp lệ} | Phần bình luận chiếm phần lớn thời lượng |
| Tổng hợp nhiều clip có luận điểm chung | Có | Biên tập, không ghép nguyên bản |
| Thay nhạc nền bằng YouTube Audio Library | Có | Tránh claim âm thanh |
| Đăng lại nguyên bản | Không {bad:Không} | Reused content: không bật kiếm tiền, dễ nhận gậy |
| Lật hình, crop viền, tốc độ 1.02× | Không {bad:Không dựa vào} | Không phải biến đổi; không dùng để né Content ID |

## Đăng bằng YouTube Data API {#dang}

| Tham số | Giá trị | Vì sao |
| --- | --- | --- |
| `snippet.title` | Tiêu đề tiếng Việt | Bắt buộc |
| `snippet.description` | Mô tả, hashtag, **ghi nguồn gốc** | Minh bạch nguồn |
| `snippet.categoryId` | `22` People & Blogs, `27` Education… | Danh mục |
| `status.privacyStatus` | `private` | Bắt buộc khi đặt `publishAt` |
| `status.publishAt` | ISO 8601 giờ VN kèm `+07:00`, ví dụ `2026-11-01T22:00:00+07:00` | YouTube tự công khai đúng giờ |
| `status.selfDeclaredMadeForKids` | `false` (hoặc `true` nếu đúng) | COPPA; thiếu thì 400 Bad Request |
| Kiểu upload | Resumable (SDK Python có sẵn) | Không dùng multipart thường cho tệp lớn |

| Thao tác | Unit | Số lần / ngày với 10.000 unit |
| --- | --- | --- |
| Upload video | ~1.600 | ~6 |
| Đặt thumbnail | 50 | — |
| Sửa title/description | 50 | — |
| Quét digest FlashTrend (A1–A3) | vài chục đến vài trăm | Dùng chung quota project |

Chi phí theo bảng quota của Google.[](source:yt-quota) Tham số theo tài liệu `videos.insert`.[](source:yt-insert)

| Cách hẹn giờ | Lịch của YouTube (`publishAt`) | Cron upload đúng giờ |
| --- | --- | --- |
| Bản chất | Upload ngay, YouTube canh giờ công khai | Tới giờ mới bắt đầu upload |
| Ưu | Xử lý HD xong trước giờ đăng; máy sập không ảnh hưởng {good:Chọn} | Chưa đụng quota trước ngày đăng |
| Nhược | Phải upload sẵn mọi tệp | Xử lý video ngay giờ đăng nên dễ trễ |

## Rủi ro kênh cần chấp nhận {#rui-ro}

| Rủi ro | Biểu hiện | Giảm thiểu |
| --- | --- | --- |
| App OAuth chưa xác minh | Video bị khoá Private, không đổi Public được {bad:Chặn} | Test user khi thử; OAuth Verification trước production |
| Content ID | Claim hoặc gậy ngay sau upload | Chỉ nội dung có quyền; thay nhạc; biến đổi thật |
| Spam | Đăng dày cùng cấu trúc → giảm đề xuất, khoá upload | ≤ 1–2 video/ngày, cấu trúc khác nhau |
| Hết quota | `quotaExceeded` khi upload | `publish_jobs.status = failed`, `error.code = YT_QUOTA`, thử lại hôm sau |
| Refresh token bị thu hồi | `invalid_grant` | Lấy lại token (trang 08 · Cài đặt, mục OAuth) |
