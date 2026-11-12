# Kết quả kiểm tra bản giao

Môi trường thực hiện: Python 3.12, Node.js 24.22, MySQL Community Server 8.4.13.

| Kiểm tra | Kết quả |
|---|---|
| Bộ kiểm thử Python với SQLite tạm | 23 đạt, 1 bỏ qua vì kiểm thử khóa dòng chỉ áp dụng MySQL |
| Cùng bộ kiểm thử trên MySQL 8.4 | 24 đạt, gồm hai yêu cầu ghi đồng thời |
| Import file `schema.sql` vào MySQL | Tạo thành công 14 bảng và view `wallet_balances` |
| Python compile và cú pháp JavaScript | Đạt |
| Luồng thao tác JavaScript bằng jsdom + Flask test client | Đạt: đăng ký, trạng thái rỗng, thu/chi, ngân sách, hũ tiết kiệm, tìm/sửa, báo cáo, danh mục, ví, hồ sơ, quỹ nhóm, đăng xuất/đăng nhập lại |
| Trình duyệt thật / ảnh chụp giao diện | Chưa thực hiện: luồng môi trường Sites không cung cấp công cụ `cua_repl.js` bắt buộc cho browser QA |
| HTTPS trên domain thật, email/push, tải lớn | Chưa thực hiện; cần cấu hình triển khai hoặc nằm ngoài phạm vi bản giao |

Các kiểm thử dữ liệu xác nhận:

- Tài khoản mới không có dữ liệu mẫu; mật khẩu lưu bằng scrypt.
- Đăng nhập lại qua một phiên bản ứng dụng mới vẫn đọc đúng dữ liệu đã ghi.
- Người khác không truy cập được ví, giao dịch và nhóm không thuộc quyền.
- Ngân sách cập nhật ngay sau thêm/sửa/xóa khoản chi; cảnh báo theo ngưỡng và cài đặt bật/tắt.
- Trích hũ không tính trùng thành chi tiêu; thao tác không đủ tiền được rollback toàn bộ.
- Đóng hũ rỗng giữ nguyên số dư, kể cả nạp từ ví A rồi rút về ví B.
- Chia 10.001 đồng cho ba người bảo toàn tổng tiền; bù trừ rồi thanh toán đưa nợ về 0.
- Quỹ thiếu tiền không được chi; hủy khoản nộp đã chi không làm âm quỹ.
- Chỉ đúng quyền được tải hóa đơn; gửi lại multipart với cùng khóa không tạo thêm bản ghi.
- Cùng khóa lưu hai lần trả cùng ID; hai yêu cầu khác khóa không thể đồng thời chi vượt số dư.

Source đóng gói không chứa tài khoản kiểm thử, dữ liệu tài chính mẫu, file `.env`, database, khóa phiên hay môi trường ảo.
