from ultralytics import YOLO
import cv2
import time
import smtplib
import threading
from email.message import EmailMessage
from picamera2 import Picamera2

SENDER_EMAIL = "phatduyen17@gmail.com"
APP_PASSWORD = "momtnvdrzejzurbs"
RECEIVER_EMAIL = "tanhaonguyen0402@gmail.com"

model = YOLO("yolov8n.pt")

LOW_W, LOW_H = 320, 240
HIGH_W, HIGH_H = 1280, 720

DETECT_EVERY_N = 3
STABLE_FRAMES = 4
STABLE_SECONDS = 2.0
RESET_AFTER_SECONDS = 3.0
EMAIL_COOLDOWN_SECONDS = 30.0
MIN_BOX_AREA = int(LOW_W * LOW_H * 0.02)
MIN_SHARPNESS = 120.0
CAPTURE_BURST = 3
CAPTURE_BURST_DELAY = 0.15

picam2 = Picamera2()
config = picam2.create_preview_configuration(
    main={"size": (HIGH_W, HIGH_H), "format": "RGB888"},
    lores={"size": (LOW_W, LOW_H), "format": "RGB888"},
    display="lores"
)
picam2.configure(config)
picam2.start()

frame_count = 0
last_boxes = []
email_sent = False
email_sending = False
email_armed = True
prev_time = time.time()
consecutive_detections = 0
first_detect_time = None
last_seen_time = None
last_email_time = 0.0
last_blur_time = 0.0


def send_email(image_path):
    msg = EmailMessage()
    msg["Subject"] = "CANH BAO: Phat hien nguoi"
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg.set_content("Da phat hien nguoi. Anh canh bao dinh kem.")

    with open(image_path, "rb") as f:
        msg.add_attachment(
            f.read(),
            maintype="image",
            subtype="jpeg",
            filename="person_detected.jpg"
        )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(SENDER_EMAIL, APP_PASSWORD)
        smtp.send_message(msg)


def sharpness_score(frame_rgb):
    gray = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def capture_best_frame(picam):
    best_frame = None
    best_score = -1.0
    for i in range(CAPTURE_BURST):
        frame = picam.capture_array("main")
        score = sharpness_score(frame)
        if score > best_score:
            best_frame = frame
            best_score = score
        if CAPTURE_BURST_DELAY > 0 and i < CAPTURE_BURST - 1:
            time.sleep(CAPTURE_BURST_DELAY)
    return best_frame, best_score


def send_email_thread(image_path):
    global email_sending, email_sent, last_email_time, email_armed
    try:
        send_email(image_path)
        print("DA GUI EMAIL")
        email_sent = True
        last_email_time = time.time()
    except Exception as e:
        print("LOI GUI EMAIL:", e)
        email_sent = False
        email_armed = True
    email_sending = False


while True:
    frame_small = picam2.capture_array("lores")
    frame_count += 1

    if frame_count % DETECT_EVERY_N == 0:
        results = model(
            frame_small,
            classes=[0],
            imgsz=256,
            conf=0.45,
            device="cpu",
            verbose=False
        )

        last_boxes = []
        detect_time = time.time()

        for box in results[0].boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            area = max(0, x2 - x1) * max(0, y2 - y1)
            if area >= MIN_BOX_AREA:
                last_boxes.append((x1, y1, x2, y2))

        if len(last_boxes) > 0:
            last_seen_time = detect_time
            if first_detect_time is None:
                first_detect_time = detect_time
            consecutive_detections += 1
        else:
            consecutive_detections = 0
            first_detect_time = None

        stable_time = (detect_time - first_detect_time) if first_detect_time else 0.0
        ready_to_send = (
            consecutive_detections >= STABLE_FRAMES
            and stable_time >= STABLE_SECONDS
        )
        cooldown_ok = (detect_time - last_email_time) >= EMAIL_COOLDOWN_SECONDS

        if ready_to_send and email_armed and not email_sending and cooldown_ok:
            image_path = "/home/admin/person_detected.jpg"

            frame_high, sharpness = capture_best_frame(picam2)
            if sharpness >= MIN_SHARPNESS:
                cv2.imwrite(image_path, cv2.cvtColor(frame_high, cv2.COLOR_RGB2BGR))
                email_armed = False
                email_sending = True

                threading.Thread(
                    target=send_email_thread,
                    args=(image_path,),
                    daemon=True
                ).start()
            else:
                last_blur_time = detect_time

    now = time.time()
    if last_seen_time is not None and (now - last_seen_time) >= RESET_AFTER_SECONDS:
        email_sent = False
        email_armed = True
        consecutive_detections = 0
        first_detect_time = None
        last_boxes = []
        last_seen_time = None

    display = frame_small.copy()

    for x1, y1, x2, y2 in last_boxes:
        cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)

    fps = 1 / (now - prev_time)
    prev_time = now

    cv2.putText(display, "FPS: %.1f" % fps, (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    if email_sending:
        status = "SENDING EMAIL"
    elif email_sent:
        status = "EMAIL SENT"
    elif len(last_boxes) > 0 and (now - last_blur_time) < 1.5:
        status = "BLURRY"
    elif len(last_boxes) > 0:
        status = "STABILIZING"
    else:
        status = "WAITING"

    cv2.putText(display, status, (10, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    cv2.imshow("Person Detect CSI", display)

    if cv2.waitKey(1) & 0xFF == 27:
        break

picam2.stop()
cv2.destroyAllWindows()
