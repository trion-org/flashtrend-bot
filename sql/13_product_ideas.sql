-- Migration 13 — which products to promote as a Shopee affiliate, by time of year (estfstudio bot: /keywords).
-- Run it on EVERY database (fresh or old) after 12_comment_templates.sql.
-- Safe to run again: every statement is `if not exists` / `on conflict do nothing`.
--
-- It reuses the occasions and windows of migration 12 (comment_occasions / comment_windows): an idea belongs to an
-- occasion, so it shows up when the day falls in one of that occasion's windows. A *product idea* is one product
-- group (Thời trang, Mỹ phẩm …) with the search keywords to type into Shopee and a short tip. The year-round
-- products hang on the occasion `quanh-nam`, whose window is the whole year (it has no comment templates, so
-- /comment skips it).
--
-- Edit the rows in the dashboard to add or change keywords; nothing in the code names one.

create table if not exists product_ideas (
  id text primary key,
  occasion_id text not null references comment_occasions (id) on delete cascade,
  category text not null,                       -- the product group: Thời trang, Mỹ phẩm, Công nghệ …
  keywords text[] not null check (cardinality(keywords) > 0),   -- what to search for on Shopee
  tip text,                                     -- how to sell it (content angle, what buyers look for)
  sort int not null default 100,                -- lower first inside an occasion
  enabled boolean not null default true,
  created_at timestamptz not null default now()
);
create index if not exists product_ideas_occasion on product_ideas (occasion_id) where enabled;
alter table product_ideas enable row level security;  -- service-role only (estfstudio's bot), like every table here

-- ---- seed ---------------------------------------------------------------------------------------------------------

insert into comment_occasions (id, title, mood, sort) values
  ('quanh-nam', 'Bán quanh năm', 'Nhu cầu đều, vòng đời ngắn, khách hay mua lại.', 900)
on conflict (id) do nothing;

insert into comment_windows (id, occasion_id, start_md, end_md, note) values
  ('quanh-nam', 'quanh-nam', '01-01', '12-31', 'cả năm')
on conflict (id) do nothing;

insert into product_ideas (id, occasion_id, category, keywords, tip, sort) values
  ('tet-thoi-trang', 'tet', 'Thời trang', array['áo dài cách tân','áo dài trẻ em','đầm đỏ đi Tết','giày cao gót đi Tết','túi xách nữ đi Tết'],
   'Video phối đồ đi chúc Tết; nhấn vải lên dáng và giao kịp Tết.', 10),
  ('tet-decor', 'tet', 'Decor nhà cửa', array['cành đào giả','cành mai giả','đèn lồng đỏ','câu đối Tết','tranh treo tường Tết','bao lì xì'],
   'Dọn nhà đón Tết, trang trí bàn thờ và phòng khách; đặt sớm kẻo sát Tết bên giao hàng nghỉ.', 20),
  ('tet-qua', 'tet', 'Bánh kẹo / Quà biếu', array['hộp bánh kẹo Tết','giỏ quà Tết','mứt Tết','hạt dinh dưỡng','set quà Tết biếu'],
   'Quà biếu vừa sang vừa rẻ; chọn shop Mall, đánh giá cao.', 30),
  ('tet-gia-dung', 'tet', 'Gia dụng', array['khay đựng mứt','bộ ấm chén','nồi chiên không dầu','bộ nồi inox'],
   'Sắm đồ nấu nướng và tiếp khách dịp Tết.', 40),

  ('valentine-nu', 'valentine', 'Quà tặng nữ', array['son thỏi','nước hoa mini','set skincare tặng bạn gái','hoa hồng sáp','gấu bông'],
   'Gợi ý quà cho các bạn nam chưa biết tặng gì.', 10),
  ('valentine-nam', 'valentine', 'Quà tặng nam', array['ví da nam','thắt lưng nam','đồng hồ nam','tai nghe bluetooth'],
   'Quà tinh tế, chính hãng; nhấn bảo hành.', 20),
  ('valentine-chung', 'valentine', 'Quà chung', array['hộp quà tặng','đèn ngủ','khung ảnh','nến thơm'],
   'Món nhỏ xinh, giá dễ chịu, giao nhanh.', 30),

  ('phu-nu-qua', 'phu-nu', 'Quà tặng mẹ / người yêu', array['set quà skincare','nước hoa nữ','kem dưỡng da tay','khăn lụa','máy massage mini'],
   'Chọn shop Mall có voucher; kèm lời nhắn tặng.', 10),
  ('phu-nu-thoi-trang', 'phu-nu', 'Thời trang / Phụ kiện', array['váy công sở','túi xách nữ','đồng hồ nữ','trang sức bạc','giày búp bê'],
   'Video phối đồ, chụp ảnh đẹp.', 20),
  ('phu-nu-lam-dep', 'phu-nu', 'Làm đẹp', array['son dưỡng môi','mặt nạ dưỡng da','serum vitamin C','dầu gội dưỡng tóc'],
   'Đồ làm đẹp khách hay mua lại; so sánh trước và sau.', 30),

  ('he-chong-nang', 'he-30-4', 'Chống nắng', array['kem chống nắng','xịt chống nắng','khẩu trang chống nắng','áo chống nắng','mũ rộng vành','kính mát'],
   'Nhấn chống nước, không nâng tone; mùa nắng bán đều tới tháng 7.', 10),
  ('he-di-bien', 'he-30-4', 'Đồ đi biển', array['bikini','đồ bơi nữ','váy đi biển','dép đi biển','túi chống nước điện thoại','phao bơi'],
   'Outfit đi du lịch, quay thử đồ.', 20),
  ('he-du-lich', 'he-30-4', 'Tiện ích du lịch', array['vali kéo','balo du lịch','chai chiết mỹ phẩm','túi đựng đồ du lịch','quạt mini cầm tay','gối cổ'],
   'Giá hạt dẻ, tiện, dễ mua bốc đồng.', 30),

  ('tt-hoc-tap', 'tuu-truong', 'Học tập', array['balo laptop','bút gel','vở sinh viên','hộp bút','máy tính cầm tay','đèn học chống cận'],
   'Giá sinh viên; combo văn phòng phẩm.', 10),
  ('tt-cong-nghe', 'tuu-truong', 'Công nghệ học tập', array['giá đỡ laptop','chuột không dây','tai nghe có mic','bàn phím không dây','ổ cứng di động'],
   'So sánh thông số, test độ tiện dụng.', 20),
  ('tt-phong-tro', 'tuu-truong', 'Decor phòng trọ', array['kệ sách mini','bàn học gấp gọn','đèn led dây','rèm cửa','thảm trải sàn'],
   'Set góc học tập; video trước và sau khi trang trí.', 30),

  ('sd-cong-nghe', 'sale-doi', 'Công nghệ', array['tai nghe bluetooth','sạc dự phòng','ốp lưng điện thoại','cáp sạc nhanh','loa bluetooth mini'],
   'Mã giảm sâu ngày đôi; nhắc lưu voucher trước.', 10),
  ('sd-gia-dung', 'sale-doi', 'Gia dụng', array['nồi chiên không dầu','máy hút bụi cầm tay','bình đun siêu tốc','máy xay sinh tố'],
   'Món giá trị lớn nên chờ sale; nhấn mã freeship.', 20),
  ('sd-tieu-dung', 'sale-doi', 'Hàng tiêu dùng', array['giấy vệ sinh combo','khăn giấy','nước giặt','đồ ăn vặt combo'],
   'Mua thùng, mua combo; lượt bán lớn.', 30),

  ('dt-tu-thuong', 'doc-than', 'Tự thưởng', array['máy massage','tai nghe chống ồn','nến thơm','chăn lông','đèn ngủ','set skincare'],
   'Tự thưởng cho bản thân, giọng văn thoải mái.', 10),

  ('gs-decor', 'giang-sinh', 'Decor Noel', array['cây thông Noel mini','đèn dây led','vòng hoa Noel','tất Noel','đồ trang trí Noel'],
   'Cắm phòng ngủ ấm cúng; đặt sớm đầu tháng 12.', 10),
  ('gs-thoi-trang', 'giang-sinh', 'Thời trang mùa đông', array['áo len','khăn len','áo khoác dạ','mũ len','găng tay'],
   'Diện đi chơi Noel; nhấn freeship extra.', 20),
  ('gs-qua', 'giang-sinh', 'Quà Giáng sinh', array['hộp quà Noel','gấu bông','hộp nhạc','nến thơm','set quà tặng'],
   'Quà nhỏ trao tay, giá mềm.', 30),

  ('qn-thoi-trang', 'quanh-nam', 'Thời trang & Phụ kiện', array['áo thun basic','set đồ nữ','giày sneaker','túi tote','trang sức bạc'],
   'Nhu cầu theo xu hướng; video phối đồ, thử đồ, review chất liệu.', 10),
  ('qn-my-pham', 'quanh-nam', 'Mỹ phẩm & Chăm sóc cá nhân', array['serum','kem chống nắng','sữa rửa mặt','dưỡng thể','xịt thơm','son kem'],
   'Khách mua lại liên tục, hoa hồng tốt; chia sẻ chu trình skincare, trước và sau.', 20),
  ('qn-gia-dung', 'quanh-nam', 'Gia dụng & Decor', array['nồi chiên không dầu','máy hút bụi mini','kệ bếp','thảm trải sàn','đèn ngủ'],
   'Video giải quyết tình huống: dọn dẹp, trang trí phòng trọ, làm bếp.', 30),
  ('qn-tieu-dung', 'quanh-nam', 'Hàng tiêu dùng & Ăn vặt', array['giấy vệ sinh','khăn lau đa năng','túi thơm','bánh kẹo ăn vặt','trà bánh combo'],
   'Giá rẻ, dễ mua bốc đồng, lượt bán lớn; mukbang, mở thùng hàng.', 40),
  ('qn-cong-nghe', 'quanh-nam', 'Phụ kiện công nghệ', array['tai nghe','sạc dự phòng','ốp lưng','giá đỡ điện thoại','cáp sạc'],
   'Tệp khách rộng; so sánh thông số, test độ bền.', 50)
on conflict (id) do nothing;
