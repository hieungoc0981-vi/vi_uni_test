# Ví Uni — Quản lý tài chính sinh viên

**Deploy miễn phí bằng Neon + Vercel: đọc `NEON_FREE.md` trước.** Bản này thêm PostgreSQL, vẫn hỗ trợ MySQL. Với Neon dùng `schema_postgresql.sql`; `schema.sql` dành cho MySQL.

**Muốn deploy Vercel? Đọc [VERCEL.md](VERCEL.md).** Cần MySQL bên ngoài và các biến môi trường; không thể dùng SQLite local để giữ tài khoản trên Vercel. Bản này đã có `vercel.json`, `build.py` và `.python-version`.

Mã nguồn Python Flask + MySQL, giao diện tiếng Việt theo bố cục ảnh tham khảo. Dùng HTML/CSS/JavaScript thuần; không cần Node.js để chạy ứng dụng, không phụ thuộc CDN.

**Tài khoản mới có số dư 0, danh mục mặc định và không có giao dịch mẫu. Đăng xuất, đóng trình duyệt hoặc khởi động lại ứng dụng không làm mất dữ liệu đã lưu.** Đăng nhập bằng cùng email để lấy lại dữ liệu. Không xóa cơ sở dữ liệu/volume nếu muốn giữ thông tin.

## 1. Cấu trúc

```text
vi-uni/
├── main.py                 # Máy chủ, mô hình dữ liệu, API, kiểm tra quyền
├── schema.sql              # Cấu trúc MySQL và view số dư, không có dữ liệu cá nhân
├── templates/index.html    # Giao diện chính và đăng nhập/đăng ký
├── static/app.js           # Các màn hình, biểu đồ, biểu mẫu, gọi API
├── static/style.css        # Giao diện xanh–trắng, hỗ trợ điện thoại
├── requirements.txt
├── requirements-dev.txt
├── .env.example            # Mẫu cấu hình, chép thành .env
├── compose.yaml            # Cách chạy MySQL bằng Docker, không bắt buộc
├── .vscode/                # Cấu hình chạy bằng F5
└── tests/test_app.py        # Kiểm thử tích hợp dữ liệu và quyền truy cập
```

## 2. Chạy với MySQL trong VS Code (khuyến nghị)

Cài **Python 3.11 trở lên**, **MySQL Community Server 8.0.16 trở lên** (khuyến nghị 8.4 LTS), VS Code và extension Python. MySQL Workbench là công cụ quản trị; vẫn cần MySQL Server đang chạy.

### Bước 1: Mở thư mục và cài thư viện

Giải nén, chọn **File → Open Folder → vi-uni**. Mở Terminal trong VS Code.

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

macOS/Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Không bắt buộc activate môi trường ảo. Cách gọi trực tiếp trên cũng tránh lỗi ExecutionPolicy của PowerShell.

### Bước 2: Tạo database và tài khoản MySQL

Đăng nhập MySQL Workbench bằng tài khoản quản trị, mở tab SQL và chạy (thay mật khẩu mẫu bằng mật khẩu riêng):

```sql
CREATE DATABASE vi_uni CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'vi_uni'@'localhost' IDENTIFIED BY 'MAT_KHAU_RIENG_CUA_BAN';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, REFERENCES
ON vi_uni.* TO 'vi_uni'@'localhost';
```

Ứng dụng sẽ tạo các bảng còn thiếu khi chạy `main.py`. Hoặc quản trị viên có thể import `schema.sql` vào database mới trước. File này không có lệnh xóa dữ liệu. View `wallet_balances` là tùy chọn để đối chiếu bằng SQL; import view cần quyền `CREATE VIEW`, ứng dụng không cần quyền đó khi chạy bình thường.

### Bước 3: Sửa `.env`

```dotenv
DATABASE_URL=mysql+pymysql://vi_uni:MAT_KHAU_RIENG_CUA_BAN@127.0.0.1:3306/vi_uni?charset=utf8mb4
SECRET_KEY=THAY_BANG_CHUOI_NGAU_NHIEN
COOKIE_SECURE=0
HOST=127.0.0.1
PORT=5000
```

Tạo `SECRET_KEY`:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

macOS/Linux thay đường dẫn Python bằng `.venv/bin/python`.

Nếu mật khẩu MySQL có `@`, `:`, `/`, `#`, `%`, cần URL-encode các ký tự đó trong `DATABASE_URL` (ví dụ `@` → `%40`, `#` → `%23`). Không đưa `.env` lên Git. `SECRET_KEY` là khóa ký cookie của máy chủ, không phải mật khẩu người dùng.

### Bước 4: Chạy

Windows:

```powershell
.\.venv\Scripts\python.exe main.py
```

macOS/Linux:

```bash
.venv/bin/python main.py
```

Mở **http://127.0.0.1:5000**, chọn **Đăng ký**. Hoặc dùng `Ctrl+Shift+P → Python: Select Interpreter`, chọn `.venv`, sau đó F5 với cấu hình **Chạy Ví Uni (main.py)**.

**Không mở `index.html` trực tiếp hoặc dùng Live Server.** Giao diện cần API Flask để đăng nhập và lưu dữ liệu. `templates/index.html` là cách tổ chức chuẩn của Flask.

## 3. Chạy thử nhanh khi chưa có MySQL

Vẫn cài thư viện như bước 1, sau đó đặt trong `.env`:

```dotenv
DATABASE_URL=sqlite:///vi_uni.db
COOKIE_SECURE=0
```

Chạy `main.py`. Dữ liệu nằm trong `instance/vi_uni.db` và được giữ sau mỗi lần mở lại. Nếu chưa có `.env`, ứng dụng cũng dùng SQLite mặc định.

**SQLite chỉ dành cho dùng thử trên máy cá nhân.** Bản chính dùng MySQL có khóa dòng để xử lý giao dịch đồng thời. Đổi từ SQLite sang MySQL sẽ mở một database khác; không tự chuyển tài khoản/dữ liệu cũ. Muốn chuyển dữ liệu cần một bước migration riêng.

## 4. MySQL bằng Docker (tùy chọn)

Cài Docker Desktop. Thêm dòng `MYSQL_PASSWORD=mat_khau_rieng` vào `.env`; dùng cùng mật khẩu trong `DATABASE_URL`. Sau đó:

```bash
docker compose up -d db
docker compose ps
```

Chờ MySQL sẵn sàng rồi chạy Python như trên. Database là `vi_uni`, user `vi_uni`, cổng 3306. Nếu máy đã dùng cổng 3306, sửa cổng bên trái trong `compose.yaml` thành 3307 và sửa `DATABASE_URL` tương ứng.

`docker compose stop` giữ dữ liệu. `docker compose down -v` **xóa volume chứa dữ liệu**; không dùng nếu cần giữ tài khoản.

## 5. Chức năng đã triển khai

| Phần | Hoạt động |
|---|---|
| Tài khoản | Đăng ký, đăng nhập, đăng xuất, sửa họ tên/trường/mã sinh viên, đổi mật khẩu có kiểm tra mật khẩu cũ |
| Dữ liệu riêng | Mọi ví, giao dịch, ngân sách, hũ chỉ thuộc người đang đăng nhập; máy chủ kiểm tra quyền cho từng ID |
| Ví | Nhiều ví VND, số dư ban đầu, đổi tên, xóa ví trống; số dư khả dụng tính từ sổ giao dịch |
| Thu/chi | Thêm/sửa/xóa; số tiền, ngày, danh mục, ví, phương thức, ghi chú, ba mức ưu tiên |
| Tra cứu | Tìm ghi chú/danh mục; lọc khoảng ngày, loại, danh mục; phân trang 15 dòng; xuất CSV UTF-8 cho Excel |
| Danh mục | Các nhóm mặc định dành cho sinh viên; thêm/sửa/xóa danh mục cá nhân chưa được sử dụng |
| Ngân sách | Tổng hoặc từng danh mục; khoảng ngày tùy chọn cho ngày/tuần/tháng; số đã chi/còn lại; ngưỡng mặc định 80%, tùy chỉnh 1–100%; bật/tắt thông báo |
| Tiết kiệm | Tạo/sửa mục tiêu, hạn hoàn thành, tiến độ, nạp/rút từ ví, xem lịch sử; gợi ý trích 5–20% khi ghi thu nhập và thực hiện cùng giao dịch khi người dùng chọn |
| Báo cáo | Tổng thu/chi, chênh lệch trong kỳ; gộp theo ngày/tuần/tháng/năm; phân bổ danh mục; so sánh 6 tháng; top 10 khoản chi; tỷ lệ chi theo mức ưu tiên |
| Nhóm | Tạo, tham gia bằng mã, đổi mã, trưởng nhóm/thành viên; sao kê chung, người ghi và thời điểm; nộp quỹ/chi quỹ/ứng tiền/trả nợ; chia đều cho thành viên được chọn |
| Đối chiếu | Phân bổ phần lẻ từng đồng, nợ ròng và gợi ý bù trừ; hóa đơn PNG/JPEG/PDF ≤5 MB; hủy có lý do, giữ bản ghi gốc và nhật ký |
| Tra cứu nhóm | Lọc sao kê theo loại, ưu tiên, người thanh toán; sắp xếp ngày, số tiền hoặc thiết yếu trước |
| Toàn vẹn | Tiền là số nguyên VND; commit/rollback đồng thời; khóa dòng MySQL; khóa chống trùng cùng commit với giao dịch; chặn âm ví, âm hũ và âm quỹ |
| Giao diện | Tiếng Việt, bố cục theo ảnh, menu trên điện thoại, trạng thái chưa có dữ liệu, thông báo lỗi cụ thể |

## 6. Những phần giản lược hoặc chưa có

Theo yêu cầu có thể bỏ phần khó nhưng phải báo lại, bản này có các giới hạn cụ thể:

- **Cập nhật nhóm bằng polling mỗi 15 giây** khi trang nhóm đang mở, có nút cập nhật thủ công; chưa dùng WebSocket tức thời.
- **Mời nhóm bằng mã**, chưa tạo/quét QR. Yêu cầu cho phép QR hoặc mã, nên mã đã đáp ứng luồng tham gia.
- **Cảnh báo trong ứng dụng**, gồm thông báo sau khi lưu và biểu tượng cảnh báo. Chưa gửi email/SMS/push khi người dùng đóng trang. Có bật/tắt và chỉnh ngưỡng, chưa chọn nhiều kênh gửi.
- **Trích hũ cần người dùng đánh dấu xác nhận** trong biểu mẫu thu nhập; hệ thống tự ghi bút toán sau khi xác nhận. Không có liên kết hay chuyển tiền ngân hàng thực tế.
- **Thuật toán bù trừ nợ ròng tham lam**, bảo toàn số tiền, giảm việc trả nợ vòng quanh; không tuyên bố tìm số lượt chuyển ít nhất tuyệt đối trong mọi trường hợp.
- **Chưa có bỏ phiếu duyệt chi**, quản lý lời mời từng email, rời/xóa nhóm, chuyển trưởng nhóm hoặc phân quyền tùy chỉnh. Có hai quyền cơ bản. Mức ưu tiên được người ghi lựa chọn; sự thống nhất nhóm diễn ra ngoài ứng dụng.
- **Giao diện nhóm hiển thị 200 giao dịch gần nhất**, nhật ký và lịch sử hũ hiển thị 100 dòng gần nhất; database giữ toàn bộ. Chưa có phân trang lịch sử nhóm/hũ. Lịch sử giao dịch cá nhân đã có phân trang và CSV theo bộ lọc.
- **Chưa có xác minh email, quên mật khẩu qua email, đăng nhập Google, xác thực hai bước**, đồng bộ ngân hàng hay đọc hóa đơn bằng OCR. Không có nút giả cho các chức năng này.
- **HTTPS cần cấu hình khi đưa lên Internet**, không thể cấp chứng chỉ cho máy bạn chỉ bằng source. Khi chạy local dùng HTTP loopback. Xem mục triển khai dưới đây.
- **Chưa kiểm tra hình ảnh hiển thị trong trình duyệt thực** trong môi trường giao mã; không có công cụ duyệt web được hỗ trợ cho luồng Sites tại thời điểm tạo. Đã kiểm tra API và luồng DOM JavaScript riêng; chi tiết xem `KIEM_THU.md`.

## 7. Quy tắc tính tiền

### Cá nhân

```text
Số dư khả dụng của ví
  = Số dư ban đầu + Tổng thu − Tổng chi − Tổng nạp hũ + Tổng rút hũ

Tiền trong hũ = Tổng nạp − Tổng rút
Tài sản đang theo dõi = Tổng ví khả dụng + Tổng tiền trong hũ
```

Số dư được tính từ các bản ghi đã commit, tránh lưu hai bản số dư có thể lệch nhau. MySQL view `wallet_balances` có cột `CurrentBalance` để kiểm tra trực tiếp. Khoản chuyển hũ không phải chi tiêu. Số dư ban đầu không phải thu nhập trong kỳ.

Sửa/xóa khoản thu sẽ hoàn lại trích hũ cũ trước khi tính lại. Nếu khoản trích đó đã được rút/dùng khiến hũ âm hoặc ví thiếu tiền, toàn bộ thao tác bị chặn và rollback. Không thể ghi giao dịch tương lai. Mọi số tiền dùng VND nguyên, không dùng số thực.

Xóa hũ rỗng thực chất là **đóng/ẩn hũ**, vẫn giữ bút toán chuyển tiền để không làm đổi số dư từng ví. Xóa danh mục đang dùng và ví có lịch sử bị chặn.

### Nhóm

- **Nộp quỹ**: tăng tiền quỹ. Là khoản đóng góp chung, không phát sinh nợ phải hoàn trả. Trưởng nhóm xác nhận ai đã nộp.
- **Chi từ quỹ**: giảm tiền quỹ. Có thể phân bổ để đối chiếu, không tạo thêm nợ cá nhân.
- **Ứng tiền & chia đều**: một thành viên trả bằng tiền cá nhân. Cộng số đã ứng cho người trả và trừ phần phải chia của từng người; không thay đổi số dư quỹ.
- **Thanh toán nợ**: trưởng nhóm xác nhận tiền đã chuyển thực tế; giảm nợ người trả và giảm khoản phải nhận của người nhận. Không thay đổi quỹ.

Ví dụ 10.001 ₫ chia 3 người có mã tăng dần → 3.334 + 3.334 + 3.333 = 10.001 ₫. Tổng dư nợ ròng của nhóm luôn bằng 0. Người vào sau không bị tính vào khoản chia trước đó.

**Sổ nhóm độc lập với ví cá nhân**: ghi nộp/ứng/chi nhóm không âm thầm thêm giao dịch vào ví thành viên. Nếu muốn phản ánh dòng tiền cá nhân, thành viên ghi thêm giao dịch ở phần cá nhân. Không cộng tổng chi nhóm vào báo cáo cá nhân để tránh tính hai lần.

Giao dịch nhóm không sửa trực tiếp; trưởng nhóm hủy có lý do rồi ghi lại đúng. Lịch sử và hóa đơn vẫn được giữ. Không thể hủy khoản nộp đã được dùng nếu khiến quỹ âm. Hủy khoản ứng sau khi có thanh toán có thể tạo nghĩa vụ hoàn tiền mới; hệ thống giữ khoản thanh toán thực tế và tính lại nợ ròng.

## 8. Bảo mật và triển khai

- Mật khẩu băm bằng scrypt, không lưu hay trả về mật khẩu gốc. Cookie phiên ký, HttpOnly, SameSite=Lax; CSRF cho API thay đổi dữ liệu. Truy vấn qua ORM, nội dung giao diện được escape, CSV có xử lý ô bắt đầu bằng công thức.
- Chặn đăng nhập sai sau 8 lần/email hoặc 60 lần/IP trong 15 phút, lưu trong DB. Không tin `X-Forwarded-For` do khách tự gửi.
- Hóa đơn lưu trong MySQL dưới dạng binary; kiểm tra chữ ký tệp, giới hạn kích thước, tải dưới dạng attachment và kiểm tra tư cách thành viên. Kiểm tra chữ ký không thay thế quét mã độc.
- `Idempotency-Key` cùng nội dung sẽ trả lại kết quả cũ; cùng khóa khác nội dung nhận 409. JavaScript giữ khóa cho lần thử lại và khóa nút lưu khi đang gửi. Các bản ghi khóa được giữ; chưa có tác vụ tự dọn.
- Dùng Waitress khi chạy `main.py`, tắt Flask debug. Nếu đưa lên Internet, đặt Nginx/Caddy trước Waitress, cấp chứng chỉ HTTPS, đặt `COOKIE_SECURE=1`, `SECRET_KEY` ngẫu nhiên, giữ cổng MySQL và Waitress nội bộ. Không để secret mẫu hoặc tài khoản DB root. Chỉ bật `COOKIE_SECURE=1` khi truy cập HTTPS, nếu không trình duyệt không gửi cookie đăng nhập.
- Đây là dự án chức năng để chạy và phát triển tiếp; chưa có kiểm thử tải lớn, kiểm toán bảo mật độc lập, mã hóa dữ liệu lưu trữ hoặc hệ thống giám sát vận hành. Nhật ký có thể được quản trị viên DB thay đổi, chưa có chữ ký chống giả mạo.

Sao lưu MySQL bằng tài khoản được cấp quyền phù hợp:

```bash
mysqldump --single-transaction --no-tablespaces -u vi_uni -p vi_uni > vi_uni_backup.sql
```

Mật khẩu nhập qua lời nhắc, không ghi trên câu lệnh. Sao lưu chứa thông tin tài chính và mật khẩu băm: lưu riêng, bảo vệ quyền truy cập. Nếu đã tạo view, dùng tài khoản backup có `SHOW VIEW`. `db.create_all()` chỉ tạo bảng thiếu, **không cập nhật cấu trúc bảng cũ**; khi sửa model ở giai đoạn sau cần migration (ví dụ Alembic).

## 9. Kiểm thử

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q tests
```

Mặc định tạo SQLite tạm riêng cho từng test. Muốn kiểm tra khóa dòng MySQL, tạo một database **dùng riêng cho test**, tên kết thúc `_test`, rồi đặt `TEST_DATABASE_URL`.

PowerShell:

```powershell
$env:TEST_DATABASE_URL="mysql+pymysql://test_user:password@127.0.0.1:3306/vi_uni_test?charset=utf8mb4"
python -m pytest -q tests
```

macOS/Linux:

```bash
TEST_DATABASE_URL='mysql+pymysql://test_user:password@127.0.0.1:3306/vi_uni_test?charset=utf8mb4' python -m pytest -q tests
```

**Các test sẽ xóa/tạo lại bảng trong database test đã chỉ định. Không dùng database thật.** Tài khoản test cần quyền tạo/xóa bảng. Cơ sở dữ liệu chạy ứng dụng không bị truy cập bởi bộ test mặc định.

Kiểm thử thêm các thao tác giao diện bằng DOM (tùy chọn, cần Node.js 20 trở lên):

```bash
npm --prefix tests/ui ci
npm --prefix tests/ui test
```

Test dùng jsdom và Flask test client, không mở cổng web và không cần trình duyệt. Mặc định chọn Python trong `.venv`; nếu thư viện được cài ở interpreter khác, đặt biến `PYTHON` trỏ đến file Python đó. Dữ liệu UI test nằm trong thư mục tạm riêng. Đây là kiểm thử thao tác, không thay thế kiểm tra bố cục bằng trình duyệt thật.

## 10. Lỗi thường gặp

| Lỗi | Cách xử lý |
|---|---|
| `Access denied for user` | Kiểm tra user, mật khẩu, host và quyền MySQL; URL-encode mật khẩu |
| `Can't connect to MySQL server` | Bật MySQL Server, kiểm tra cổng 3306/3307; Workbench không thay thế MySQL Server |
| `Unknown database` | Chạy `CREATE DATABASE vi_uni ...` trước |
| `ModuleNotFoundError` | Cài requirements bằng đúng Python `.venv`, chọn đúng interpreter trong VS Code |
| Đăng nhập xong quay lại trang đăng nhập | Trên HTTP local, đặt `COOKIE_SECURE=0`; mở bằng URL Flask; kiểm tra cookie |
| Báo CSRF hết hạn | Tải lại trang, tránh dùng tab cũ sau khi đăng xuất ở tab khác |
| Không nhập được khoản chi | Ví phải có đủ tiền; thêm thu nhập hoặc số dư ban đầu trước |
| Không thấy dữ liệu cũ | Đăng nhập cùng email, kiểm tra đang dùng cùng `DATABASE_URL` và database; không xóa `instance/` khi dùng SQLite |
| Mở HTML thấy giao diện nhưng không lưu | Chạy `main.py`, vào `http://127.0.0.1:5000`; không dùng Live Server |

