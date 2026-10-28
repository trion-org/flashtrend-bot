# Ảnh được upload ở đâu và lưu link thế nào? {#anh}

Ảnh FlashTrend tự tạo (biểu đồ run, ảnh bìa) được POST multipart tới **image host bên thứ ba** trong `thirst-party.cmd`; Supabase chỉ lưu URL trả về cùng `sha256` trong bảng `media`. Thumbnail YouTube đã có URL công khai (`i.ytimg.com`) nên **không cần upload**, chỉ lưu vào `videos.thumbnail_url`.

- Không dùng Supabase Storage: gói Free chỉ có 1 GB storage và 5 GB egress cho cả hai repo.[](source:pricing)
- `sha256` là khoá duy nhất: một ảnh chỉ upload một lần, kể cả khi run chạy lại.
- Endpoint là API nội bộ của một website, không phải dịch vụ ảnh có hợp đồng: phải coi là có thể hỏng bất cứ lúc nào.

@answer scope="Endpoint lấy từ thirst-party.cmd (2026-10-28) · chưa kiểm định dạng phản hồi · thiết kế, chưa có mã"
@meta locale=vi
@source cmd title="thirst-party.cmd — lệnh upload mẫu" path=thirst-party.cmd
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

## Lệnh mẫu tương đương trong Python {#python}

`thirst-party.cmd` là cú pháp PowerShell (`curl.exe`, dấu backtick cuối dòng để nối dòng), không phải cmd. Bản Python dự kiến cho adapter `infrastructure/image_host.py`:

```python title="infrastructure/image_host.py (dự kiến)"
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

Lệnh mẫu gửi thêm `Origin` và `Referer` của website. Chỉ thêm hai header đó nếu chạy thử chứng minh endpoint bắt buộc, và ghi rõ lý do trong mã.

## Rủi ro nào cần chấp nhận trước? {#rui-ro}

| Rủi ro | Hệ quả | Cách giảm |
| --- | --- | --- |
| Endpoint đổi hoặc chặn IP GitHub Actions | Run không có ảnh {caution:Mất ảnh} | Upload lỗi không làm run `error`; ghi `media` thiếu, digest vẫn gửi |
| Website xoá tệp cũ | Link chết trong Telegram | Cron kiểm `HEAD url` mỗi tuần, đặt `alive = false` |
| Điều khoản website không cho dùng làm kho ảnh | Bị khoá {bad:Pháp lý} | Hỏi chủ website; giữ adapter thay được (Catbox, imgbb, Cloudinary free) |
| Repo public lộ endpoint | Người khác dùng chung, website siết lại | Không đưa ảnh riêng tư; không commit ảnh chụp màn hình |
| Phản hồi không chứa URL công khai | Không có link để lưu | Chạy thử một lần trước khi viết mã, ghi định dạng vào tài liệu này |

@callout level=open-question title="Cần xác nhận trước khi code"
Endpoint có cần cookie đăng nhập không? Lệnh mẫu không có, nhưng nó được chụp từ trang `profile/account`.
Phản hồi JSON đặt URL ở trường nào, và URL đó có công khai, không hết hạn không?

- [ ] Chạy `thirst-party.cmd` một lần với ảnh thử, lưu phản hồi (đã che thông tin) vào tài liệu này.
- [ ] Xác nhận có được phép dùng endpoint làm kho ảnh cho bot.
- [ ] Đổi tên tệp thành `third-party.cmd` khi viết mã (lỗi chính tả "thirst").
