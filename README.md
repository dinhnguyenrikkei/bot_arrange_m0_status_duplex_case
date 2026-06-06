# Hướng dẫn Cấu hình & Triển khai Hệ thống Điều phối Data Lark Suite

Dự án này là một API chạy bằng Python (FastAPI) để tự động hóa việc phân chia và điều phối dữ liệu lead (data khách hàng) từ Lark Base cho các Thực tập sinh (TTS) và Tư vấn viên (TVV) theo các nghiệp vụ xoay vòng (Round-Robin), múi giờ bận/rảnh, ưu tiên khu vực và giới hạn quá tải 2 lượt/ngày.

---

## 1. Yêu cầu hệ thống & Cài đặt môi trường

### Bước 1: Cài đặt Python và các thư viện cần thiết
Đảm bảo máy tính hoặc server đã cài đặt **Python 3.8+**.

Mở terminal trong thư mục dự án và chạy lệnh sau để cài đặt các thư viện phụ thuộc:
```bash
pip install -r requirements.txt
```

### Bước 2: Tạo tệp cấu hình `.env`
Sao chép file cấu hình mẫu `.env.example` thành `.env`:
* Trên Windows (PowerShell):
  ```powershell
  cp env.example .env
  ```

Mở tệp `.env` vừa tạo và điền các thông tin cấu hình tương ứng với Lark Base của bạn (xem hướng dẫn lấy thông tin ở Mục 2).

---

## 2. Hướng dẫn thiết lập trên Lark Suite Open Platform

Để code có thể giao tiếp với Lark, bạn cần tạo một Ứng dụng tự xây dựng (Self-built App) và lấy các thông số kết nối.

### Bước A: Tạo Ứng dụng trên Lark Developer Console
1. Truy cập [Lark Open Platform Console](https://open.larksuite.com/open-apis/authen/v1/index).
2. Nhấp vào **Create Custom App** (Tạo ứng dụng tự xây dựng), đặt tên ứng dụng (ví dụ: *Điều phối Lead Tự động*) và nhấn tạo.
3. Tại trang tổng quan của App, bạn sẽ thấy thông tin:
   * **App ID** (ví dụ: `cli_xxxxxx`)
   * **App Secret** (ví dụ: `xxxxxx`)
   Điền 2 thông số này vào file `.env`.

### Bước B: Cấp quyền cho Ứng dụng (Scopes)
Tại menu bên trái, chọn **Permissions & Scopes** (Quyền hạn & Phạm vi), tìm kiếm và cấp các quyền sau:
1. `bitable:app` (Đọc và ghi dữ liệu Bitable - *View, comment, edit and manage Base*)
2. `bitable:app:readonly` (Xem thông tin Bitable - *View Base*)

Sau khi thêm các quyền này, nhấp vào **Create Version** (Tạo phiên bản), điền mô tả rồi nhấn **Release / Publish** để kích hoạt các quyền của App.

### Bước C: Lấy Base Token và Table ID
1. Mở trang Bitable của bạn trên trình duyệt web.
2. Nhìn lên thanh địa chỉ URL, định dạng sẽ như sau:
   `https://rikkeieducation.sg.larksuite.com/base/OgaVbI06xaTiwAs4yfglcyXpgLg?table=tblw9IGc8PmB3wR2&view=vewND6oust`
   * **Base Token**: Đoạn mã nằm sau `/base/` và trước dấu chấm hỏi (`?`). Trong URL trên, Base Token là `OgaVbI06xaTiwAs4yfglcyXpgLg`.
   * **Table ID của TikTok**: Đoạn mã sau `table=`. Trong URL trên, Table ID là `tblw9IGc8PmB3wR2`.
   * **Table ID của TVV**: Chuyển sang tab bảng điều phối TVV để lấy ID bảng TVV tương ứng.
3. Điền các giá trị này vào file `.env`.

### Bước D: Cấp quyền truy cập Bitable cho App (Quan trọng)
1. Mở Bitable trên Lark.
2. Click vào nút **Share** (Chia sẻ) ở góc trên bên phải $\rightarrow$ chọn **Invite** (Mời).
3. Nhập tên ứng dụng của bạn (ví dụ: *Điều phối Lead Tự động*) và cấp quyền **Editor** (Người chỉnh sửa) hoặc quyền quản trị cao nhất để ứng dụng có quyền đọc/ghi dữ liệu.

---

## 3. Khởi chạy Ứng dụng

Chạy lệnh sau để khởi động server FastAPI:
```bash
python main.py
```
Server sẽ chạy mặc định tại cổng `8000` (địa chỉ `http://localhost:8000`).

Để ứng dụng nhận được webhook từ Lark trực tiếp khi phát triển ở localhost, bạn cần dùng công cụ public URL tạm thời như **ngrok** hoặc **Cloudflare Tunnel**:
```bash
ngrok http 8000
```
Bạn sẽ nhận được một đường dẫn public HTTPS (ví dụ: `https://xxxx.ngrok-free.app`).

---

## 4. Cài đặt Webhook tự động hóa trên Lark Base

Khi một dòng dữ liệu được chuyển trạng thái sang `M0`, chúng ta cần kích hoạt webhook gửi tới server.

1. Mở Bitable $\rightarrow$ nhấp vào **Automations** (Tự động hóa) ở góc trên bên phải.
2. Tạo một quy trình tự động hóa mới:
   * **Trigger (Khi điều kiện xảy ra)**: Chọn **When a record updates** (Khi bản ghi được cập nhật) $\rightarrow$ Lọc điều kiện: cột **Trạng thái** thay đổi thành **M0**.
   * **Action (Hành động)**: Chọn **Send HTTP Request** (Gửi yêu cầu HTTP).
     * **Method**: `POST`
     * **URL**: Điền URL của server của bạn, ví dụ: `https://xxxx.ngrok-free.app/webhook/m0`
     * **Headers**: Thêm header nếu bạn cấu hình bảo mật (ví dụ: Key: `X-Webhook-Token`, Value: Giá trị token của bạn).
     * **Body**: Chọn dạng **JSON** và nhập nội dung sau:
       ```json
       {
         "record_id": "[Record ID]"
       }
       ```
       *(Lưu ý: Bấm vào nút `+` bên cạnh ô nhập để chèn biến động `Record ID` từ Lark vào vị trí `[Record ID]`)*
3. Nhấn **Save** và kích hoạt quy trình tự động hóa này.

---

## 5. Thiết lập Lịch chạy lúc 8:00 AM (Cron Job cho T0)

Để phân bổ tự động dữ liệu `T0` cho các TTS vào lúc 8:00 sáng hàng ngày:
* Cấu hình một công cụ lập lịch chạy (Cron Job) trên máy chủ hoặc sử dụng các dịch vụ như GitHub Actions, Google Cloud Scheduler để gửi một request HTTP POST hàng ngày vào lúc 8:00 AM (giờ Việt Nam) tới:
  `https://xxxx.ngrok-free.app/cron/daily-t0`
* Khi nhận được request này, server sẽ tự động chạy ngầm logic lấy data T0 và chia xoay vòng cho các TTS đang tích `Đi làm hôm nay`.
# bot_arrange_m0_status_duplex_case
