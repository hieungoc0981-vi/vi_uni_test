# Ví Uni

Ứng dụng giúp sinh viên theo dõi thu chi, hạn mức ngân sách và mục tiêu tiết kiệm.

## Công nghệ

- Backend: Flask
- Giao diện: HTML, CSS và JavaScript
- PostgreSQL: hỗ trợ Neon qua biến môi trường `VI_UNI_DATABASE_URL`.
- Khi chưa cấu hình PostgreSQL, phát triển cục bộ dùng SQLite tại `instance/vi_uni.sqlite3`.

## Chức năng hiện có

- Đăng ký, đăng nhập và đăng xuất; mật khẩu được băm trước khi lưu.
- Ghi, lọc theo thời gian, sửa và xóa giao dịch thu/chi.
- Quản lý danh mục và ví cá nhân; danh mục cơ bản được tạo tự động.
- Đặt ngân sách theo danh mục và tháng; cảnh báo khi chi tiêu đạt 80% hoặc vượt hạn mức.
- Tạo mục tiêu tiết kiệm và cập nhật thủ công số tiền đã dành dụm.
- Tổng quan tính số dư, tổng thu, tổng chi và tiến độ tiết kiệm từ dữ liệu cục bộ.
- Tạo quỹ nhóm, tham gia bằng mã, ghi góp/chi quỹ, chia đều khoản riêng, ghi quyết toán và xem gợi ý cân đối dư nợ.
- Ghi nhật ký hoạt động nhóm và chỉ cho phép thành viên xem/quản lý dữ liệu của nhóm đó.

## Giới hạn hiện tại

- Chia khoản hiện chia đều cho toàn bộ thành viên; chưa có chọn nhóm con, đính kèm hóa đơn hoặc xóa thành viên.
- Góp tiết kiệm chỉ cập nhật sổ theo dõi mục tiêu, chưa trừ tiền từ ví hoặc tạo giao dịch.
- Neon và Vercel dự kiến triển khai vào ngày cuối dự án.

## Dùng PostgreSQL trên Neon

1. Tạo một Neon project/database riêng cho Ví Uni; không dùng database đang chứa website khác.
2. Chạy `database/schema.sql` một lần trên database Ví Uni mới.
3. Đặt `VI_UNI_DATABASE_URL` bằng connection string dạng pooled của database đó và `SECRET_KEY` bằng chuỗi ngẫu nhiên dài.
4. Chạy local với các biến môi trường trên, hoặc đặt chúng trong Vercel Project Settings.

Ứng dụng không tự chạy schema trên PostgreSQL khi khởi động. Khi chưa cấu hình PostgreSQL, app dùng SQLite cục bộ. Khi chạy trên Vercel, thiếu `VI_UNI_DATABASE_URL` hoặc `SECRET_KEY` sẽ làm app báo lỗi cấu hình thay vì ghi dữ liệu vào filesystem tạm.

Đổi từ SQLite sang Neon không tự chuyển tài khoản hoặc giao dịch cũ; cần xuất/nhập dữ liệu riêng trước khi chuyển người dùng sang database mới.

Vercel nhận diện Flask app từ `main.py` và biến `app`; không cần cấu hình build riêng. Sau khi kết nối Git repository, có thể tạo preview deployment rồi promote lên production.
