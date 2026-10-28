# Cần cấu hình những dịch vụ nào để chạy MVP? {#cai-dat}

Bốn secret là đủ cho MVP: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `YOUTUBE_API_KEY`, `GEMINI_API_KEY`. Làm theo thứ tự GitHub → Supabase → YouTube → Gemini → Actions; OAuth upload và cookie yt-dlp chỉ cần ở v2.

- Không có `TELEGRAM_*` trong repo này: token bot thuộc estfstudio.[](source:setup)
- Dùng `service_role`, không dùng `anon`: RLS bật và không có policy, nên `anon` không ghi được.
- API key YouTube chỉ giới hạn theo API, không giới hạn IP: IP của GitHub Actions thay đổi liên tục.
- Image host (trang 07) hiện không cần khoá; nếu sau này cần thì thêm secret `IMAGE_HOST_*`.

@answer scope="Hướng dẫn cài đặt (2026-10-28) · cron tính theo UTC · chưa có main.py nên workflow sẽ fail tới Phase 1"
@meta locale=vi
@source setup title="Hướng dẫn cài đặt dịch vụ (2026-10-28) — Third-party setup"
@source actions-cron title="GitHub Actions — schedule event" url=https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#schedule

## Làm theo thứ tự nào? {#thu-tu span=12}

@workflow id=setup-order title="Thứ tự cấu hình"
| lane repo | Repo |
| lane svc | Dịch vụ |
| lane run | Chạy |
| gh | GitHub repo public | frontend | repo |
| sb | Supabase + schema | database | svc |
| yt | YouTube API key | external | svc |
| gem | Gemini key | cloud | svc |
| sec | GitHub Secrets | security | run |
| act | workflow_dispatch | backend | run |
| gh > sb | |
| sb > yt | |
| yt > gem | |
| gem > sec | 4 secret |
| sec > act | | emphasis |

@steps id=setup-steps
| st-gh | GitHub repo public | Repo public để có phút Actions không giới hạn; đặt Spending limit = $0. |
| st-sb | Supabase + schema | Project Free (Singapore hoặc Tokyo), chạy DDL lõi + bảng `media` (trang 03), seed `app_config`. |
| st-yt | YouTube API key | Bật YouTube Data API v3, tạo API key, Restrict key theo đúng API đó. |
| st-gem | Gemini key | Tạo key ở Google AI Studio; model mặc định `gemini-2.5-flash` (xác nhận còn hỗ trợ khi code). |
| st-sec | GitHub Secrets | Settings → Secrets and variables → Actions; dán không ngoặc kép, không khoảng trắng. |
| st-act | workflow_dispatch | Chạy tay một lần; thành công khi `runs.status = ok` và mọi `ideas.llm` khác null. |

## Secret nào lấy ở đâu? {#secret}

| Biến | Khi nào | Lấy ở đâu |
| --- | --- | --- |
| `SUPABASE_URL` | MVP {good:Bắt buộc} | Supabase → Project Settings → API → Project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | MVP {good:Bắt buộc} | Cùng trang → `service_role` (không phải `anon`) |
| `YOUTUBE_API_KEY` | MVP {good:Bắt buộc} | Google Cloud → Credentials → API key |
| `GEMINI_API_KEY` | MVP {good:Bắt buộc} | aistudio.google.com/apikey |
| `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN` | v2 upload | OAuth client Desktop + OAuth Playground |
| `BILI_COOKIES` | v2 tải nguồn | Cookie Netscape của tài khoản bạn; không commit |

estfstudio giữ `SUPABASE_URL` và `SUPABASE_SERVICE_ROLE_KEY` của cùng project trong `.secrets/secrets.yml` của nó, không qua git.

## GitHub: repo, Spending limit, Secrets {#github}

| Việc | Cách làm |
| --- | --- |
| Visibility | Public: phút Linux không giới hạn (vẫn giới hạn job 6 giờ, 20 job song song); private chỉ 2.000 phút/tháng. Public không lộ giá trị Secrets, chỉ lộ code và YAML |
| Spending limit = $0 | Settings của **tài khoản** (không phải repo) → Billing and plans → Spending limits / Cost management → `$0`, tránh trừ thẻ khi hết phút |
| Secrets | Token, key, URL có thông tin đăng nhập; được che trong log. Repo → Settings → Secrets and variables → Actions → New repository secret |
| Variables | Cờ không nhạy cảm như `REGION`; để ở Secrets cũng được |
| Cố ý không cấu hình | Telegram bot, Supabase Auth / Realtime / Storage / Edge Functions; không cần tài khoản Hugging Face (MiniLM tải công khai) |

## Google Cloud và Gemini {#google}

@steps id=gcp-steps
| g1 | Project + bật API | console.cloud.google.com, cùng tài khoản sở hữu kênh (v2 cần) → New Project `flashtrend-bot` → APIs & Services → Library → `YouTube Data API v3` → Enable. |
| g2 | API key | Credentials → Create credentials → API key → `YOUTUBE_API_KEY` (dạng `AIzaSy…`). |
| g3 | Siết key | Edit API key → API restrictions → Restrict key → chỉ YouTube Data API v3; Application restrictions để None (IP của Actions đổi liên tục, giới hạn IP sẽ 403). |
| g4 | Gemini key | aistudio.google.com/apikey → Create API key, nên gắn vào cùng project `flashtrend-bot` để gom quota; nếu có mục restrict thì chỉ cho Generative Language API. |
| g5 | Model | Mặc định `gemini-2.5-flash` (rẻ, đủ JSON có cấu trúc); kiểm danh sách model trên AI Studio khi code, đổi nếu bị deprecate. |

| Gọi API đọc | Unit | Ghi chú |
| --- | --- | --- |
| `videos.list` (chart mostPopular) | 1 | Rẻ |
| `channels.list` | 1 | Cache 24 giờ qua `stale_after` |
| `search.list` | 100 | Đắt — hạn chế số từ khoá |
| Upload (chỉ v2) | ~1.600 | MVP không upload |

Theo dõi quota: APIs & Services → Dashboard / Quotas. Free tier Gemini đủ cho 1–2 run/ngày × vài ý tưởng; gặp 429 thì chỉ gửi top sau Z-Score và thử lại có backoff.

## Workflow chạy theo lịch {#workflow}

```yaml title=".github/workflows/flashtrend.yml"
name: FlashTrend digest
on:
  schedule:
    - cron: "17 0 * * *"   # 00:17 UTC = 07:17 giờ VN
  workflow_dispatch:
jobs:
  digest:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.10" }
      - uses: actions/cache@v4
        with:
          path: |
            ~/.cache/pip
            ~/.cache/huggingface
          key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements.txt') }}
      - run: pip install -r requirements.txt
      - run: python main.py
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
          YOUTUBE_API_KEY: ${{ secrets.YOUTUBE_API_KEY }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
```

GitHub luôn đọc cron theo UTC.[](source:actions-cron) Phút lệch `17` tránh hàng chờ đầu giờ. Muốn chạy lần hai thì thêm `- cron: "17 11 * * *"` (11:17 UTC = 18:17 giờ VN = 20:17 giờ Nhật). Bản đầy đủ nên có thêm bước `python -m pip install --upgrade pip` và `restore-keys: ${{ runner.os }}-pip-` cho cache.

| Muốn chạy lúc | Múi giờ | Giờ UTC | cron |
| --- | --- | --- | --- |
| 09:17 Nhật | UTC+9 | 00:17 | `17 0 * * *` |
| 09:17 Việt Nam | UTC+7 | 02:17 | `17 2 * * *` |
| 18:17 Nhật | UTC+9 | 09:17 | `17 9 * * *` |

Chạy thử: tab Actions → workflow **FlashTrend digest** → Run workflow. Log không được in `YOUTUBE_API_KEY`, `SERVICE_ROLE`, `GEMINI_API_KEY` (GitHub chỉ che khi trùng chuỗi chính xác). Nếu cài `torch` thì chỉ bản CPU: `pip install torch --index-url https://download.pytorch.org/whl/cpu`.

## Supabase: tạo project và chạy schema {#supabase}

@steps id=sb-steps
| sb1 | Tạo project | supabase.com → New project; tên `flashtrend-bot`; region Tokyo (máy ở Nhật) hoặc Singapore (mạng VN); gói Free; lưu mật khẩu DB vào trình quản lý mật khẩu. |
| sb2 | Lấy URL và key | Project Settings → API: Project URL → `SUPABASE_URL`; `service_role` → Reveal → `SUPABASE_SERVICE_ROLE_KEY` (JWT bắt đầu `eyJ`). |
| sb3 | Chạy DDL | SQL Editor → New query → dán DDL lõi + bảng `media` (trang 03 · Dữ liệu) → Run; `create extension if not exists vector` nằm đầu DDL. |
| sb4 | Seed app_config | `insert into app_config (keywords, regions, llm_enabled) …`; chạy lần hai sẽ lỗi khoá chính, khi đó dùng `update … where id = 1`. |
| sb5 | Chung với estfstudio | Một project cho cả hai repo; estfstudio chạy migration `estf_*` sau DDL này. |

Connection string (chỉ khi sau này dùng `psycopg`): Project Settings → Database → URI chế độ Transaction pooler, cổng `6543`; lưu thành secret `SUPABASE_DB_URL`, không commit.

```sql title="Seed lại khi đã có hàng (chạy lần hai sẽ lỗi khoá chính)"
update app_config
set keywords = array['python bot', 'ai tools', 'personal finance', 'street food', 'youtube shorts'],
    regions = array['VN', 'JP'],
    llm_enabled = true,
    updated_at = now()
where id = 1;
```

```text title="Connection string (Transaction pooler, cổng 6543) — chỉ khi dùng psycopg"
postgresql://postgres.YOUR_PROJECT_REF:YOUR_DB_PASSWORD@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres
```

Host và region đổi theo project. MVP chỉ cần `supabase-py` + URL + `service_role`. Mật khẩu DB chỉ cần cho connection string, không đưa lên GitHub. Khoá `anon` / `publishable` bị RLS chặn nên job không ghi được; `service_role` bỏ qua RLS — coi như root: chỉ để trong Secret, không log, không đưa vào client.

## v2: OAuth để upload YouTube {#oauth}

Chỉ cần khi đăng video **bạn có quyền**. App chưa qua OAuth Verification thì video bị khoá Private.

@steps id=oauth-steps
| o1 | OAuth consent screen | Cùng project Google Cloud → User Type External → tên app `FlashTrend Bot`, email hỗ trợ và liên hệ developer → scope `https://www.googleapis.com/auth/youtube.upload` → Test users: Gmail sở hữu kênh. |
| o2 | OAuth client | Credentials → OAuth client ID → Desktop app (script) hoặc Web application với redirect `https://developers.google.com/oauthplayground` → lấy Client ID (`…apps.googleusercontent.com`) và Client Secret (`GOCSPX-…`). |
| o3 | Refresh token | OAuth 2.0 Playground → bánh răng → Use your own OAuth credentials → chọn scope `youtube.upload` → Authorize bằng test user → Exchange → Refresh token (`1//0g…`). |
| o4 | Lưu secret | `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`; access token sống ~1 giờ, script tự xin lại bằng refresh token. |
| o5 | Production | Gửi OAuth Verification trước khi kỳ vọng `publishAt` tự công khai video. |

## v2: cookie cho yt-dlp {#cookie}

Cookie là thông tin đăng nhập: chỉ để trong Secret hoặc tệp cục bộ, không bao giờ commit `cookies.txt`.

- [ ] Đăng nhập Bilibili/Douyin bằng tài khoản của bạn, xuất cookie dạng Netscape (tiện ích kiểu "Get cookies.txt LOCALLY").
- [ ] Máy cục bộ: `yt-dlp --cookies cookies.txt "URL"`.
- [ ] Actions: lưu toàn bộ nội dung tệp vào secret `BILI_COOKIES`, job ghi ra tệp tạm và xoá sau khi chạy.
- [ ] Cookie hết hạn thì xuất lại; không dùng cookie của người khác.

## Chạy trên máy cục bộ {#local}

```bash title=".env ở gốc repo (đã có trong .gitignore)"
YOUTUBE_API_KEY=AIzaSy_your_key_here
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ_your_service_role_here
GEMINI_API_KEY=your-google-ai-studio-key
```

```bash title="Kiểm tra key Gemini (không commit)"
curl -s "https://generativelanguage.googleapis.com/v1beta/models?key=$GEMINI_API_KEY" | head
```

```powershell title="Windows: kiểm key Gemini và nạp .env vào phiên hiện tại"
$env:GEMINI_API_KEY = "PASTE_KEY"
curl.exe -s "https://generativelanguage.googleapis.com/v1beta/models?key=$env:GEMINI_API_KEY"

Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
  $k, $v = $_.Split('=', 2)
  Set-Item -Path "Env:$($k.Trim())" -Value $v.Trim()
}
```

JSON liệt kê model nghĩa là key sống; `API_KEY_INVALID` là sai key hoặc sai project.

## Lỗi thường gặp {#loi}

| Triệu chứng | Cách xử lý |
| --- | --- |
| `new row violates row-level security` | Đang dùng `anon`; đổi sang `service_role` |
| `extension "vector" is not available` | Database → Extensions → bật `vector` |
| YouTube `quotaExceeded` | Bớt `search.list` (100 unit/lần); quota reset theo giờ Pacific |
| Gemini 429 | Gửi ít ý tưởng hơn, thử lại có backoff |
| `runs.status = error` nhưng có `candidates` | Gemini lỗi sau L2 — đúng thiết kế, estfstudio bỏ qua run đó |
| Project Supabase bị pause | Wake trên dashboard; giữ cron ít nhất 1 lần/ngày |
| `relation "ideas" does not exist` | Chưa chạy DDL hoặc sai project |
| YouTube `API key not valid` / 403 | Sai project, chưa bật API, hoặc restrict nhầm API |
| Gemini `API_KEY_INVALID` | Sai key hoặc thừa khoảng trắng trong Secret |
| Actions `secret not found` | Tên Secret khác tên trong YAML (phân biệt hoa thường) |
| Job treo quá 10 phút | `timeout-minutes` dừng job; kiểm bước pip/torch CUDA |
| Video v2 kẹt Private | App chưa xác minh; thêm test user hoặc làm OAuth Verification |
| Hugging Face chậm lần đầu | Bình thường; lần sau nhờ cache |

- [ ] Repo GitHub; Spending limit `$0`.
- [ ] Supabase Healthy; đủ 10 bảng lõi (+ `media`); RLS bật; không có policy `anon`.
- [ ] `app_config` đúng một hàng `id = 1`, `llm_enabled = true`.
- [ ] `SUPABASE_URL` + `service_role` (không phải `anon`).
- [ ] YouTube Data API v3 đã bật; API key chỉ giới hạn theo API đó.
- [ ] Key Gemini; lệnh `curl` liệt kê được model.
- [ ] Bốn secret MVP đã gắn; không có `TELEGRAM_*` trên repo này.
- [ ] estfstudio (ngoài repo) có cùng `SUPABASE_URL` + `service_role`.
- [ ] `.env` có trong `.gitignore`; không secret nào trong tệp được track.
- [ ] `workflow_dispatch` chạy được (fail trước khi có `main.py` ở Phase 1 là bình thường).
