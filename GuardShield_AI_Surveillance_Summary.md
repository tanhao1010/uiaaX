# 🛡️ HỆ THỐNG GIÁM SÁT AN NINH GUARDSHIELD AI™
## Tóm tắt Hệ thống & Hướng dẫn Vận hành trên Raspberry Pi 5

Tài liệu này tóm tắt cấu trúc và cách hoạt động của hệ thống giám sát an ninh thông minh AI tích hợp điều khiển thiết bị ngoại vi chạy trên Raspberry Pi 5.

---

## 1. Bản đồ cấu trúc thư mục Dự án
Dưới đây là các tệp tin đã được lập trình hoàn chỉnh trong dự án:

```text
d:\Project_PDUYEN\
├── cameradetect.py         # Backend chính (Flask Web Server + YOLOv8 Detection Thread)
├── config.json             # File lưu cấu hình thông số an ninh, SMTP & tên thiết bị (Tự sinh)
├── GuardShield_AI_Surveillance_Summary.md # File tóm tắt này
└── website/                # Thư mục chứa giao diện Website giám sát cao cấp
    ├── index.html          # Giao diện chính (Surveillance cyber dark dashboard)
    ├── app.js              # Logic Javascript tương tác API & Polling trạng thái
    ├── style.css           # Định dạng giao diện Glassmorphism & Cyber Neon Dark Theme
    └── logo.png            # Logo hệ thống (được tái sử dụng từ dự án trước)
```

---

## 2. Các Tính năng Cốt lõi của Hệ thống

### 📡 Truyền hình ảnh Live Stream AI thời gian thực
* Sử dụng luồng dữ liệu MJPEG nén truyền trực tiếp từ camera qua endpoint `/video_feed`.
* Giao diện hiển thị camera được bọc trong khung **Viewfinder** kỹ thuật số cao cấp, tự động hiển thị FPS thực tế của mô hình nhận dạng YOLOv8.
* Bản vẽ bounding box nhận diện người được vẽ đè lên luồng video bằng màu đỏ neon nổi bật và độ tin cậy phần trăm tin cậy của đối tượng xâm nhập.

### 🛡️ Kích hoạt hệ thống & Cảnh báo tức thì
* **Master Switch (Arm/Disarm)**: Kích hoạt hoặc tạm ngắt chế độ giám sát. Khi ngắt giám sát (Disarmed), còi hú báo động sẽ tự động ngắt và ngừng phân tích camera để tiết kiệm tài nguyên Pi 5.
* **Cảnh báo Email**: Khi hệ thống được bật (Armed) và phát hiện người đứng yên ổn định trong khu vực giám sát (mặc định $\ge$ 2.0 giây), hệ thống sẽ chụp lại ảnh camera thời gian thực, tự động gửi Email báo động khẩn cấp kèm ảnh chụp xâm nhập qua SMTP của Gmail.
* **Còi hú (Buzzer)**: Tự động kích hoạt còi báo động vật lý kết nối với chân GPIO của Pi 5 khi có đột nhập. Bạn cũng có thể kích hoạt hoặc tắt còi này thủ công qua bảng điều khiển trên website.
* **Nút báo động khẩn cấp (Panic Alarm)**: Bấm nút khẩn cấp trên Website để kích hoạt ngay lập tức còi hú và gửi email cảnh báo tức thời mà không cần đợi YOLO phát hiện.

### 💡 Điều khiển 3 Thiết bị Ngoại vi thông minh
* Điều khiển bật/tắt độc lập 3 thiết bị thông qua các công tắc chuyển mạch trên website.
* Tên hiển thị của 3 thiết bị có thể đặt lại một cách linh hoạt trực tiếp từ giao diện cấu hình của website (ví dụ: "Đèn Cổng", "Khóa Điện Tử", "Hệ Thống Phun Nước") và được lưu vĩnh viễn trên Pi 5.

---

## 3. Sơ đồ kết nối phần cứng Raspberry Pi 5
Hệ thống sử dụng chân BCM (GPIO) để điều khiển rơ-le kích hoạt thiết bị ngoại vi và còi báo động:

| Thiết bị ngoại vi | Chân GPIO (BCM) | Số chân vật lý (Header Pin) | Trạng thái mặc định |
| :--- | :---: | :---: | :---: |
| **Thiết bị 1** (Ví dụ: Đèn cổng) | **GPIO 17** | Chân 11 | LOW (TẮT) |
| **Thiết bị 2** (Ví dụ: Khóa điện) | **GPIO 27** | Chân 13 | LOW (TẮT) |
| **Thiết bị 3** (Ví dụ: Quạt gió) | **GPIO 22** | Chân 15 | LOW (TẮT) |
| **Còi hú báo động** (Buzzer) | **GPIO 23** | Chân 16 | LOW (TẮT) |

> 💡 **Mẹo**: Bạn có thể thay đổi các chân GPIO này bất cứ lúc nào bằng cách sửa giá trị pin trong lớp `HardwareController` tại dòng 45-50 trong file `cameradetect.py`.

---

## 4. Chế độ Giả lập Thông minh (Windows Simulation Mode)
Để giúp lập trình và kiểm thử dễ dàng ngay trên hệ điều hành Windows mà không cần cắm camera hay các chân GPIO vật lý của Raspberry Pi:
1. **Camera Simulator**: Nếu không có camera CSI/Webcam, hệ thống tự động sinh ra một luồng video màu tối cực đẹp, có vẽ các vòng tròn radar HUD quét mục tiêu, hiển thị ngày giờ thực tế và tự động vẽ một "humanoid target" di chuyển qua lại để kiểm tra tính năng nhận diện của YOLO và trigger báo động.
2. **GPIO Mocking**: Các thay đổi bật/tắt thiết bị sẽ không báo lỗi crash hệ thống do thiếu thư viện GPIO, thay vào đó sẽ in trực tiếp log thay đổi trạng thái ra cửa sổ Terminal/Console để lập trình viên theo dõi.

---

## 5. Hướng dẫn cài đặt & Vận hành trên Raspberry Pi 5

### Bước 1: Cài đặt các thư viện Python cần thiết
Mở terminal trên Raspberry Pi 5 của bạn và chạy lệnh cài đặt:
```bash
pip install Flask ultralytics opencv-python numpy gpiozero
```

### Bước 2: Khởi chạy hệ thống an ninh
Chạy tệp tin backend bằng Python:
```bash
python cameradetect.py
```
Hệ thống sẽ khởi động song song Web Server tại cổng `5000` và luồng AI Camera bắt đầu quét.

### Bước 3: Truy cập Bảng điều khiển từ Trình duyệt
* Truy cập trên thiết bị cục bộ: `http://localhost:5000`
* Truy cập từ các thiết bị khác (Điện thoại, Laptop) kết nối chung mạng WiFi: `http://<IP-CỦA-RASPBERRY-PI-5>:5000`
* **Tài khoản đăng nhập mặc định**:
  * Tên đăng nhập: `admin`
  * Mật khẩu: `123456`

### Bước 4: Cấu hình thông số gửi Email Cảnh báo
1. Truy cập vào tab **Cài đặt** (Settings) trên website.
2. Nhập thông tin tài khoản gửi Gmail cảnh báo (`sender_email`) và mật khẩu ứng dụng Gmail (`app_password` - gồm 16 chữ số do Google cấp trong phần bảo mật 2 lớp của tài khoản).
3. Nhập Email người nhận cảnh báo (`receiver_email`).
4. Nhập tên của 3 thiết bị ngoại vi theo ý thích của bạn và bấm **LƯU CẤU HÌNH LÊN RASPBERRY PI 5**.
5. Cấu hình sẽ tự động được ghi đè vào file `config.json` và áp dụng tức thì.

---
🛡️ *Hệ thống Giám sát An ninh GuardShield AI™ - Bảo vệ tối ưu cho ngôi nhà của bạn!*
