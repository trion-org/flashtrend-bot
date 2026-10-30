# Ảnh được upload ở đâu và lưu link thế nào? {#anh}

Ảnh FlashTrend tự tạo (biểu đồ run, ảnh bìa) được POST multipart tới **image host của hệ thống mẹ** (lệnh mẫu bên dưới); Supabase chỉ lưu URL trả về cùng `sha256` trong bảng `media`. Thumbnail YouTube đã có URL công khai (`i.ytimg.com`) nên **không cần upload**, chỉ lưu vào `videos.thumbnail_url`.

- Không dùng Supabase Storage: gói Free chỉ có 1 GB storage và 5 GB egress cho cả hai repo.[](source:pricing)
- `sha256` là khoá duy nhất: một ảnh chỉ upload một lần, kể cả khi run chạy lại.
- Endpoint là API của hệ thống mẹ, không phải dịch vụ ảnh có hợp đồng: phải coi là có thể hỏng bất cứ lúc nào.
- estfstudio cũng upload ảnh bìa từng phần lên cùng host, theo đúng quy trình dưới đây (`owner = 'estfstudio'`, `kind = 'cover'`).

@answer scope="Endpoint của hệ thống mẹ · đã thử upload thật (2026-10-31) · địa chỉ trong `S3_URL`"
@meta locale=vi
@source cmd title="Lệnh upload ảnh mẫu (PowerShell, 2026-10-28)"
@source pricing title="Supabase pricing — Free plan" url=https://supabase.com/pricing

## Một ảnh đi qua những bước nào? {#luong-upload}

@sequence id=upload-flow title="Upload ảnh và lưu link"
| actor job | GitHub Actions job | backend |
| actor db | Supabase | database |
| actor host | Image host | external |
| actor estf | estfstudio | backend |
| job | db | sha256 đã có trong media? |
| db | job | không có | return |
| job | host | POST /files/upload (multipart) | emphasis |
| host | job | JSON chứa URL | return |
| job | db | insert media (url, sha256, bytes) |
| estf | db | đọc digest + image_url |
| db | estf | top 10 ý tưởng | return |

@steps id=upload-steps
| u-check | GitHub Actions job | Tính `sha256` của tệp; nếu đã có trong `media` thì dùng lại URL, bỏ qua upload. | upload-flow | job |
| u-post | Image host | Gửi `file=@<ảnh>;type=image/png`, giới hạn 2 MB, timeout 30 giây, thử lại 2 lần. | upload-flow | host |
| u-save | Supabase | Lưu `url`, `host`, `sha256`, `bytes`, `kind`, `video_id` hoặc `run_id`. | upload-flow | db |
| u-read | estfstudio | Lấy `image_url` từ view digest, gửi ảnh qua Telegram bằng URL (không tải về). | upload-flow | estf |

Phía estfstudio dùng adapter riêng `infrastructure/image_host.py` bằng `urllib` (dự án không thêm `requests`); upload lỗi không chặn việc đăng bài, chỉ để `cover_media_id` trống. Cron `HEAD url` hằng tuần của FlashTrend kiểm mọi hàng `media`, kể cả `owner = 'estfstudio'`.

## Lệnh mẫu tương đương trong Python {#python}

```powershell title="Lệnh upload mẫu (PowerShell)"
curl.exe -X POST "https://nobinobi.vn/shop-service/api/v1/files/upload" `
  -H "Accept: application/json" `
  -H "Origin: https://nobinobi.vn" `
  -H "Referer: https://nobinobi.vn/profile/account" `
  -F "file=@Screenshot 2026-10-28 185840.png;type=image/png"
```

Đây là cú pháp PowerShell (`curl.exe`, dấu backtick cuối dòng để nối dòng), không phải cmd. Bản Python dự kiến cho adapter `infrastructure/image_host.py`:

```python title="Bản phác ban đầu (mã thật: infrastructure/image_host.py, tìm URL theo cấu trúc vì chưa biết tên trường)"
import hashlib, requests

UPLOAD_URL = "https://nobinobi.vn/shop-service/api/v1/files/upload"

def upload(path: str, timeout: float = 30) -> tuple[str, str]:
    data = open(path, "rb").read()
    if len(data) > 2_000_000:
        raise ValueError("image > 2 MB")
    digest = hashlib.sha256(data).hexdigest()
    r = requests.post(
        UPLOAD_URL,
        files={"file": (path.rsplit("/", 1)[-1], data, "image/png")},
        headers={"Accept": "application/json"},
        timeout=timeout,
    )
    r.raise_for_status()
    url = find_url(r.json())  # tên trường chưa biết: xác nhận bằng một lần chạy thử
    return url, digest
```

Lệnh mẫu gửi thêm `Origin` và `Referer`; chạy thử cho thấy hai header đó không bắt buộc nên mã không gửi.

## Rủi ro nào cần chấp nhận trước? {#rui-ro}

| Rủi ro | Hệ quả | Cách giảm |
| --- | --- | --- |
| Endpoint đổi hoặc chặn IP GitHub Actions | Run không có ảnh {caution:Mất ảnh} | Upload lỗi không làm run `error`; ghi `media` thiếu, digest vẫn gửi |
| Website xoá tệp cũ | Link chết trong Telegram | Cron kiểm `HEAD url` mỗi tuần, đặt `alive = false` |
| Hệ thống mẹ đổi hoặc gỡ endpoint | Run không có ảnh | Địa chỉ nằm trong `S3_URL`; adapter thay được (Catbox, imgbb, Cloudinary free) |
| Repo public lộ endpoint | Endpoint không cần khoá: ai biết địa chỉ (đã có trong lệnh mẫu của tài liệu này) đều upload được | Không đưa ảnh riêng tư; nên nhờ hệ thống mẹ giới hạn hoặc thêm khoá nếu bị lạm dụng; log của bot che `S3_URL` |
| Phản hồi không chứa URL công khai | Không có link để lưu | Đã thử: phản hồi có trường `url`; mã vẫn tìm URL theo cấu trúc phòng khi đổi tên trường |

@callout level=note title="Đã thử endpoint (2026-10-31)"
POST chỉ với `Accept: application/json` và `file=@ảnh.png;type=image/png` trả HTTP 200: không cần cookie, `Origin` hay `Referer`.
Phản hồi: `{"statusCode":200,"message":"Upload file successfully","url":"https://…s3…amazonaws.com/files/<hash>.png"}`. URL là S3 công khai (HEAD trả 200).

- [x] Chạy thử một lần với ảnh PNG nhỏ; định dạng phản hồi đã ghi ở trên.
- [x] Endpoint thuộc hệ thống mẹ của ứng dụng (cùng chủ), nên không còn câu hỏi về điều khoản sử dụng.
- [x] Địa chỉ nằm trong biến môi trường / secret `S3_URL` (tuỳ chọn): không có thì biểu đồ của run không được upload, run vẫn chạy.
- [ ] Chưa biết S3 có xoá tệp cũ không: cron `HEAD url` hằng tuần vẫn là lưới an toàn.
