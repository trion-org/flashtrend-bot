-- Migration 12 — Shopee-affiliate comment templates by time of year (estfstudio bot: /comment).
-- Run it on EVERY database (fresh or old) after 11_publish.sql.
-- Safe to run again: every statement is `if not exists` / `on conflict do nothing`.
--
-- An *occasion* (Tết, Valentine, 11.11 …) has one or more *windows* of the year in which its templates fit — the lead
-- time before the day itself is part of the window (people put things in the cart 7–10 days before a big sale).
-- A window is either recurring every year (`start_md`/`end_md`, 'MM-DD'; start after end = it crosses New Year) or one
-- fixed span (`start_date`/`end_date`) for an occasion that moves, like Tết (lunar) — add a row each year.
-- A *template* is a ready-to-paste comment; `{link}` marks where the admin's own affiliate link goes (the link itself
-- is never stored here). The bot reads everything in one call and picks the occasions whose window holds the day.
--
-- Edit the rows in the dashboard (or via PostgREST) to add occasions, windows or templates; nothing in the code names one.

create table if not exists comment_occasions (
  id text primary key check (id ~ '^[a-z0-9][a-z0-9-]{0,39}$'),
  title text not null,
  mood text,                                    -- what the buyer is thinking in this period (a hint for the writer)
  sort int not null default 100,                -- lower first when several occasions overlap
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists comment_windows (
  id text primary key,
  occasion_id text not null references comment_occasions (id) on delete cascade,
  start_md text check (start_md ~ '^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$'),
  end_md text check (end_md ~ '^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$'),
  start_date date,
  end_date date,
  note text,
  check ((start_md is not null and end_md is not null and start_date is null and end_date is null)
      or (start_md is null and end_md is null and start_date is not null and end_date is not null
          and start_date <= end_date))
);
create index if not exists comment_windows_occasion on comment_windows (occasion_id);

create table if not exists comment_templates (
  id text primary key,
  occasion_id text not null references comment_occasions (id) on delete cascade,
  category text,                                -- the product kind it suits: Thời trang, Mỹ phẩm …
  body text not null check (length(body) between 1 and 2000 and body like '%{link}%'),
  enabled boolean not null default true,
  created_at timestamptz not null default now()
);
create index if not exists comment_templates_occasion on comment_templates (occasion_id) where enabled;

alter table comment_occasions enable row level security;  -- service-role only (estfstudio's bot), like every table here
alter table comment_windows enable row level security;
alter table comment_templates enable row level security;

-- ---- seed: the occasions of the Vietnamese shopping year ------------------------------------------------------------

insert into comment_occasions (id, title, mood, sort) values
  ('tet',          'Tết Nguyên Đán',                     'Sắm đồ mới, trang trí nhà cửa, chuẩn bị đồ diện Tết, quà biếu.', 10),
  ('valentine',    'Valentine (14/2)',                   'Tìm quà tặng người yêu.', 20),
  ('phu-nu',       'Quốc tế Phụ nữ 8/3 & Phụ nữ Việt Nam 20/10', 'Chọn quà cho mẹ, người yêu, cô giáo, đồng nghiệp nữ.', 30),
  ('he-30-4',      'Nghỉ lễ 30/4 – 1/5 & mùa hè',        'Đồ đi biển, đi du lịch, chống nắng.', 40),
  ('tuu-truong',   'Tựu trường (Back to School)',        'Học sinh, sinh viên sắm balo, sách vở, phụ kiện học tập, decor phòng trọ.', 50),
  ('sale-doi',     'Siêu sale ngày đôi (9.9 · 10.10 · 11.11 · 12.12)', 'Săn mã giảm giá, săn deal 0đ và flash sale.', 60),
  ('doc-than',     'Lễ Độc thân 11/11',                  'Tự thưởng cho bản thân.', 70),
  ('giang-sinh',   'Giáng sinh & Năm mới',               'Decor Noel, áo len, quà tặng Giáng sinh.', 80)
on conflict (id) do nothing;

-- Recurring windows (lead time included). Tết moves with the lunar calendar: one fixed span per year, ending on mùng 5
-- (mùng 1 = 2027-02-06, 2028-01-26, 2029-02-13). Add the next year's row before the shopping season starts.
insert into comment_windows (id, occasion_id, start_md, end_md, start_date, end_date, note) values
  ('tet-2027',        'tet',        null,    null,    '2027-01-07', '2027-02-10', 'Tết Đinh Mùi — mùng 1 = 6/2/2027'),
  ('tet-2028',        'tet',        null,    null,    '2027-12-27', '2028-01-30', 'Tết Mậu Thân — mùng 1 = 26/1/2028'),
  ('tet-2029',        'tet',        null,    null,    '2029-01-14', '2029-02-17', 'Tết Kỷ Dậu — mùng 1 = 13/2/2029'),
  ('valentine',       'valentine',  '02-07', '02-14', null,         null,         '7 ngày trước 14/2'),
  ('phu-nu-8-3',      'phu-nu',     '03-01', '03-08', null,         null,         '8/3'),
  ('phu-nu-20-10',    'phu-nu',     '10-13', '10-20', null,         null,         '20/10'),
  ('he-30-4',         'he-30-4',    '04-20', '07-31', null,         null,         'từ trước 30/4 đến hết mùa hè'),
  ('tuu-truong',      'tuu-truong', '08-01', '09-15', null,         null,         'tháng 8 đến giữa tháng 9'),
  ('sale-doi-9-9',    'sale-doi',   '09-02', '09-09', null,         null,         '9.9'),
  ('sale-doi-10-10',  'sale-doi',   '10-03', '10-10', null,         null,         '10.10'),
  ('sale-doi-11-11',  'sale-doi',   '11-04', '11-11', null,         null,         '11.11'),
  ('sale-doi-12-12',  'sale-doi',   '12-05', '12-12', null,         null,         '12.12'),
  ('doc-than',        'doc-than',   '11-01', '11-11', null,         null,         '11/11'),
  ('giang-sinh',      'giang-sinh', '12-10', '12-31', null,         null,         'trước Noel đến hết năm')
on conflict (id) do nothing;

insert into comment_templates (id, occasion_id, category, body) values
  ('tet-1', 'tet', 'Thời trang / Giày dép',
   'Tết đến nơi rồi mọi người ơi! Mẫu này mặc đi chúc Tết xinh lắm mà vải lên dáng chuẩn. Đang có mã freeship ở đây nha: {link}'),
  ('tet-2', 'tet', 'Decor / Gia dụng',
   'Dọn nhà đón Tết mà thiếu mấy món decor này là dở rồi. Tớ săn được shop này giá rẻ mà giao nhanh kịp Tết nè: {link}'),
  ('tet-3', 'tet', 'Bánh kẹo / Quà biếu',
   'Set quà Tết này đem đi biếu vừa sang vừa rẻ. Mọi người đặt sớm kẻo sát Tết bên giao hàng họ nghỉ nha: {link}'),
  ('valentine-1', 'valentine', 'Quà tặng nữ (mỹ phẩm, son, nước hoa)',
   'Ai chưa biết tặng gì cho người yêu dịp Valentine thì chốt ngay em này nhé. Đúng gu chị em, săn deal giá êm ở đây: {link}'),
  ('valentine-2', 'valentine', 'Quà tặng nam (phụ kiện, đồ công nghệ)',
   'Gợi ý quà Valentine cho bạn nam tinh tế mà các ông lại thích mê. Link săn deal chính hãng đây nha: {link}'),
  ('phu-nu-1', 'phu-nu', 'Mỹ phẩm / Skincare',
   'Mua quà tặng Mẹ, tặng người yêu thì cứ chọn em này cho an toàn. Shop Mall uy tín đang sẵn voucher giảm giá nè: {link}'),
  ('phu-nu-2', 'phu-nu', 'Thời trang / Phụ kiện',
   'Mẫu váy, túi này diện đi chơi chụp ảnh siêu xinh luôn. Link shop chuẩn tớ mua ở đây nha: {link}'),
  ('he-30-4-1', 'he-30-4', 'Kem chống nắng / Mỹ phẩm hè',
   'Chuẩn bị đi biển mà không mang em kem chống nắng này là tiếc lắm. Chống nước tốt mà không nâng tone lố: {link}'),
  ('he-30-4-2', 'he-30-4', 'Thời trang đi biển / Đồ du lịch',
   'Outfit đi du lịch hè đỉnh, chụp hình lên cực ngầu. Link em mua săn sale ở đây nè: {link}'),
  ('he-30-4-3', 'he-30-4', 'Tiện ích du lịch',
   'Mấy món mini chiết mỹ phẩm, túi đựng đồ du lịch này tiện lắm luôn. Giá hạt dẻ ở link này nha: {link}'),
  ('tuu-truong-1', 'tuu-truong', 'Văn phòng phẩm / Balo',
   'Balo đi học vừa bền vừa đựng được laptop 15.6 inch cho tân sinh viên nè. Giá sinh viên ở đây nha: {link}'),
  ('tuu-truong-2', 'tuu-truong', 'Decor phòng trọ',
   'Set decor góc học tập siêu chill cho mùa nhập học mới. Link shop bán full set giá hời: {link}'),
  ('sale-doi-1', 'sale-doi', 'Hướng dẫn lưu mã',
   'Đợt sale đôi này em này giảm sâu khủng khiếp luôn. Mọi người lưu sẵn vào giỏ hàng, đêm nay bấm thanh toán là được: {link}'),
  ('sale-doi-2', 'sale-doi', 'Kích thích mua nhanh',
   'Sale lớn mà bỏ qua em này là tiếc hùi hụi! Mã giảm 50K/100K áp được hết ở link này nha: {link}'),
  ('doc-than-1', 'doc-than', 'Tự thưởng',
   'FA thì sao? Tự thưởng cho bản thân thôi! Ngày 11/11 áp mã này giảm sâu lắm, tớ để link ở đây cho ai cần nha: {link}'),
  ('giang-sinh-1', 'giang-sinh', 'Decor Noel',
   'Mấy món decor Noel này cắm phòng ngủ ấm cúng hết sức. Link mua trọn bộ giá rẻ đây nhé: {link}'),
  ('giang-sinh-2', 'giang-sinh', 'Thời trang mùa đông',
   'Áo len, áo ấm diện đi chơi Noel sang xịn mịn luôn. Đang được áp mã freeship extra nè: {link}')
on conflict (id) do nothing;
