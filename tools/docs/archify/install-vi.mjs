// Enroll the Vietnamese catalog (vi.json beside this file) into an Archify clone, and teach the
// explainer renderer Vietnamese page chrome. Idempotent. Usage: node install-vi.mjs <archify-clone>
import { copyFileSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const clone = process.argv[2];
if (!clone) throw new Error('usage: node install-vi.mjs <archify-clone>');
const here = dirname(fileURLToPath(import.meta.url));
const pkg = join(clone, 'archify');

copyFileSync(join(here, 'vi.json'), join(pkg, 'locales', 'vi.json'));

const manifestPath = join(pkg, 'locales', 'manifest.json');
const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
if (!manifest.catalogs.some(c => c.locale === 'vi')) {
  manifest.catalogs.push({ locale: 'vi', file: 'vi.json' });
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + '\n');
}

const renderPath = join(pkg, 'explainer', 'render.mjs');
let render = readFileSync(renderPath, 'utf8');
const vi = `  vi:{answer:'Kết luận',answerMark:'KL',scope:'Áp dụng cho',sources:'Nguồn',print:'In / PDF',image:'Ảnh dài',imageHints:['Nét nhất','Nhỏ nhất','Mở ở đâu cũng được'],export:'Xuất',style:'Kiểu',styles:{clean:'Gọn',editorial:'Tạp chí',product:'Sản phẩm',swiss:'Lưới'},auto:'Hệ thống',light:'Sáng',dark:'Tối',typical:'Giá trị điển hình',explore:'Mở sơ đồ tương tác',exploreTitle:'Phóng to, tìm nút, lần theo đường, lên/xuống nguồn, xuất ảnh hoặc chuyển động',close:'Đóng',loading:'Đang mở sơ đồ…',graph:'Cấu trúc sơ đồ',changes:'Thay đổi cấu trúc',added:'Thêm',removed:'Bỏ',modified:'Sửa',copy:'Chép',copied:'Đã chép',walk:'Xem từng bước',walkMessages:'Phát các thông điệp',walkFlow:'Đi theo luồng',prev:'Trước',next:'Tiếp',end:'Xong',ask:'Hỏi',askQuote:'Hỏi về đoạn này',askPlaceholder:'Chỗ nào chưa rõ, hoặc phần này nên nói thêm gì?',askCopy:'Chép câu hỏi',askCopied:'Đã chép. Dán cho agent của bạn.',askCancel:'Huỷ',askChips:['Tôi chưa hiểu phần này','Đi sâu hơn','Cho ví dụ','Dựa trên đâu?'],askPage:'Trang',askFile:'Tệp',askWhere:'Vị trí',askQuoteLabel:'Trích',askQuestion:'Câu hỏi',askNote:'Chép cả trang, panel và ID của nó để agent chỉ sửa phần này.',askPatch:'Chỉ sửa panel này bằng Archify panel replacement (patch explainer), giữ nguyên ID.',tagline:'Biến thứ bạn muốn hiểu, lập kế hoạch hay chia sẻ thành một hình ảnh tương tác.',facts:{panels:n=>\`\${n} panel\`,diagrams:n=>\`\${n} sơ đồ đã kiểm\`,sources:n=>\`\${n} nguồn\`,pinned:rev=>\`mã ghim ở \${rev}\`}},\n`;
if (!render.includes('  vi:{answer:')) {
  render = render.replace(/(const dictionaries = \{\n)/, `$1${vi}`);
  render = render.replace("const words = dictionaries[english ? 'en' : 'zh'];",
    "const words = dictionaries[locale.startsWith('vi') ? 'vi' : english ? 'en' : 'zh'];");
  if (!render.includes("locale.startsWith('vi') ? 'vi'")) throw new Error('render.mjs layout changed; patch by hand');
  writeFileSync(renderPath, render);
}
console.log('archify: vi locale installed');
