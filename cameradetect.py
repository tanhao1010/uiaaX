import os
import sys
import time
import json
import cv2
import smtplib
import threading
from email.message import EmailMessage
from datetime import datetime
import numpy as np

# Flask imports
try:
    from flask import Flask, Response, jsonify, request, send_from_directory
except ImportError:
    print("[SYSTEM] Flask not found. Please install it using: pip install Flask")
    # We will let the script proceed so it can be installed, or we can run a command later

# YOLO Import
try:
    from ultralytics import YOLO
except ImportError:
    print("[SYSTEM] YOLO not found. Please install it using: pip install ultralytics")

# Hardware Pi 5 GPIO Import Handler
GPIO_MODE = "mock"
try:
    from gpiozero import LED, Buzzer
    GPIO_MODE = "gpiozero"
except ImportError:
    try:
        import RPi.GPIO as GPIO
        GPIO_MODE = "rpi_gpio"
    except ImportError:
        GPIO_MODE = "mock"

# Setup Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
WEBSITE_DIR = os.path.join(BASE_DIR, "website")

# Ensure website directory exists
if not os.path.exists(WEBSITE_DIR):
    os.makedirs(WEBSITE_DIR)

# ----------------- CONFIGURATION MANAGEMENT -----------------
DEFAULT_CONFIG = {
    "sender_email": "phatduyen17@gmail.com",
    "app_password": "momtnvdrzejzurbs",
    "receiver_email": "tanhaonguyen0402@gmail.com",
    "email_alerts_enabled": True,
    "buzzer_alerts_enabled": True,
    "system_armed": True,
    "cooldown_seconds": 30.0,
    "stable_seconds": 2.0,
    "confidence": 0.45,
    "min_box_area": 1500,
    "device_1_name": "Đèn Cổng Chính",
    "device_2_name": "Khóa Cửa Điện",
    "device_3_name": "Quạt Thông Gió"
}

def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
                # Merge with defaults in case of missing keys
                for k, v in DEFAULT_CONFIG.items():
                    if k not in config:
                        config[k] = v
                return config
        except Exception as e:
            print(f"[CONFIG] Error loading config: {e}. Using defaults.")
    
    # Save default config if not found
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()

def save_config(config_data):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
        print("[CONFIG] Configuration saved successfully")
    except Exception as e:
        print(f"[CONFIG] Error saving config: {e}")

system_config = load_config()

# ----------------- HARDWARE GPIO CONTROLLER -----------------
class HardwareController:
    def __init__(self):
        self.mode = GPIO_MODE
        print(f"[HARDWARE] Initializing in '{self.mode}' mode")
        self.devices = {1: None, 2: None, 3: None}
        self.buzzer = None
        
        # BCM Pin mappings (Default Pi 5 setup)
        self.pins = {
            1: 17,        # Device 1: GPIO 17
            2: 27,        # Device 2: GPIO 27
            3: 22,        # Device 3: GPIO 22
            "buzzer": 23  # Buzzer: GPIO 23
        }
        
        self.states = {
            1: False,
            2: False,
            3: False,
            "buzzer": False
        }
        
        if self.mode == "gpiozero":
            try:
                self.devices[1] = LED(self.pins[1])
                self.devices[2] = LED(self.pins[2])
                self.devices[3] = LED(self.pins[3])
                self.buzzer = Buzzer(self.pins["buzzer"])
                # Reset all to off
                for dev in self.devices.values():
                    dev.off()
                self.buzzer.off()
            except Exception as e:
                print(f"[HARDWARE] Gpiozero initialization failed: {e}. Falling back to MOCK.")
                self.mode = "mock"
                
        elif self.mode == "rpi_gpio":
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setwarnings(False)
                for dev_id, pin in self.pins.items():
                    GPIO.setup(pin, GPIO.OUT)
                    GPIO.output(pin, GPIO.LOW)
            except Exception as e:
                print(f"[HARDWARE] RPi.GPIO initialization failed: {e}. Falling back to MOCK.")
                self.mode = "mock"

    def set_device(self, device_id, state):
        if device_id not in [1, 2, 3]:
            return
        state = bool(state)
        self.states[device_id] = state
        print(f"[HARDWARE] GPIO Control - Device {device_id} ({system_config.get(f'device_{device_id}_name')}) -> {'ON' if state else 'OFF'}")
        
        if self.mode == "gpiozero":
            try:
                if state:
                    self.devices[device_id].on()
                else:
                    self.devices[device_id].off()
            except Exception as e:
                print(f"[HARDWARE] Gpiozero error on device {device_id}: {e}")
                
        elif self.mode == "rpi_gpio":
            try:
                pin = self.pins[device_id]
                GPIO.output(pin, GPIO.HIGH if state else GPIO.LOW)
            except Exception as e:
                print(f"[HARDWARE] RPi.GPIO error on device {device_id}: {e}")
                
    def set_buzzer(self, state):
        state = bool(state)
        self.states["buzzer"] = state
        print(f"[HARDWARE] GPIO Control - Buzzer/Siren -> {'ON' if state else 'OFF'}")
        
        if self.mode == "gpiozero":
            try:
                if state:
                    self.buzzer.on()
                else:
                    self.buzzer.off()
            except Exception as e:
                print(f"[HARDWARE] Gpiozero error on buzzer: {e}")
                
        elif self.mode == "rpi_gpio":
            try:
                pin = self.pins["buzzer"]
                GPIO.output(pin, GPIO.HIGH if state else GPIO.LOW)
            except Exception as e:
                print(f"[HARDWARE] RPi.GPIO error on buzzer: {e}")

    def cleanup(self):
        print("[HARDWARE] Cleaning up GPIO connections...")
        if self.mode == "rpi_gpio":
            try:
                GPIO.cleanup()
            except Exception as e:
                print(f"[HARDWARE] GPIO cleanup error: {e}")

hw_controller = HardwareController()

# ----------------- GLOBALS & SHARED VARIABLES -----------------
raw_frame = None                # Unannotated frame shared for YOLO
encoded_jpeg_frame = None       # Pre-encoded annotated JPEG byte array
detected_boxes = []             # Decoupled bounding boxes updated by YOLO
detection_fps = 0.0
is_person_detected = False
email_sending = False
last_email_time = 0.0
last_alert_trigger_time = 0.0
active_alert_timer = None       # Auto shutoff buzzer timer
event_logs = []                 # Store security event history in-memory

def add_event(description, category="info"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_item = {
        "timestamp": timestamp,
        "description": description,
        "category": category
    }
    event_logs.insert(0, log_item)
    # Keep only recent 100 logs
    if len(event_logs) > 100:
        event_logs.pop()
    print(f"[EVENT LOG] {timestamp} - {description}")

add_event("Hệ thống khởi động thành công. Sẵn sàng giám sát.", "success")

# ----------------- EMAIL SENDING THREAD -----------------
def send_email_alert(image_path):
    global email_sending, last_email_time
    try:
        email_sending = True
        add_event("Đang chuẩn bị gửi email cảnh báo...", "info")
        
        sender = system_config["sender_email"]
        password = system_config["app_password"]
        receiver = system_config["receiver_email"]
        
        msg = EmailMessage()
        msg["Subject"] = "🚨 CẢNH BÁO: Phát hiện xâm nhập trái phép! 🚨"
        msg["From"] = sender
        msg["To"] = receiver
        
        body = f"""Hệ thống Giám sát An ninh GuardShield AI™ đã phát hiện có người xuất hiện trong khu vực giám sát.
        
Thời gian phát hiện: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
Trạng thái: Báo động còi hú đã được kích hoạt.
        
Chi tiết hình ảnh camera ghi nhận được gửi kèm trong thư này."""
        
        msg.set_content(body)
        
        # Attach image
        if os.path.exists(image_path):
            with open(image_path, "rb") as f:
                img_data = f.read()
                msg.add_attachment(
                    img_data,
                    maintype="image",
                    subtype="jpeg",
                    filename="guardshield_snapshot.jpg"
                )
        
        # Send SMTP
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender, password)
            smtp.send_message(msg)
            
        last_email_time = time.time()
        add_event(f"Đã gửi email cảnh báo xâm nhập thành công tới {receiver}", "success")
    except Exception as e:
        add_event(f"Lỗi gửi email cảnh báo: {str(e)}", "danger")
    finally:
        email_sending = False

# ----------------- CAMERA & YOLO DETECTION PIPELINE -----------------
class CameraDetector:
    def __init__(self):
        self.model = None
        self.running = False
        self.cam = None
        self.picam2 = None
        self.mode = "simulation" # 'picamera2', 'webcam', 'simulation'
        
    def init_camera(self):
        # 1. Try Picamera2 (Pi CSI Camera)
        try:
            from picamera2 import Picamera2
            print("[CAMERA] Picamera2 library found, attempting initialization...")
            self.picam2 = Picamera2()
            config = self.picam2.create_preview_configuration(
                main={"size": (1280, 720), "format": "RGB888"},
                lores={"size": (320, 240), "format": "RGB888"},
                display="lores"
            )
            self.picam2.configure(config)
            self.picam2.start()
            self.mode = "picamera2"
            print("[CAMERA] Picamera2 initialized successfully!")
            return True
        except Exception as e:
            print(f"[CAMERA] Picamera2 init failed or not on Raspberry Pi: {e}")
            
        # 2. Try Standard OpenCV Webcam (USB)
        try:
            print("[CAMERA] Attempting standard webcam initialization via OpenCV...")
            self.cam = cv2.VideoCapture(0)
            if self.cam.isOpened():
                self.mode = "webcam"
                self.cam.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                print("[CAMERA] USB Webcam (OpenCV) initialized successfully!")
                return True
            else:
                self.cam = None
                print("[CAMERA] No USB Webcams could be opened")
        except Exception as e:
            print(f"[CAMERA] Webcam init failed: {e}")
            
        # 3. Fallback to Simulation
        self.mode = "simulation"
        print("[CAMERA] CAMERA FALLBACK: Running in Simulation Mode. Generating synthetic security frames.")
        return True

    def init_model(self):
        try:
            print("[YOLO] Loading YOLOv8 nano model...")
            self.model = YOLO("yolov8n.pt")
            print("[YOLO] YOLOv8 loaded successfully!")
        except Exception as e:
            print(f"[YOLO] Error loading YOLO model: {e}. Detection will be simulated.")

    def run_capture(self):
        global encoded_jpeg_frame, raw_frame, detected_boxes, is_person_detected, detection_fps
        
        self.init_camera()
        self.running = True
        
        sim_person_x = 50
        sim_person_y = 150
        sim_person_dir = 1
        
        prev_time = time.time()
        fps_camera = 0.0
        
        print("[CAMERA THREAD] Camera Capture loop started.")
        
        while self.running:
            start_loop = time.time()
            frame_raw = None
            
            # --- 1. CAPTURE FRAME ---
            if self.mode == "picamera2":
                try:
                    frame_raw = self.picam2.capture_array("main")
                    frame_raw = cv2.cvtColor(frame_raw, cv2.COLOR_RGB2BGR)
                except Exception as e:
                    print(f"[CAMERA] Picamera2 read error: {e}. Switching to Simulation.")
                    self.mode = "simulation"
                    
            elif self.mode == "webcam":
                try:
                    ret, frame_raw = self.cam.read()
                    if not ret or frame_raw is None:
                        raise Exception("Failed to read webcam frame")
                except Exception as e:
                    print(f"[CAMERA] USB Webcam read error: {e}. Switching to Simulation.")
                    self.mode = "simulation"
                    
            if self.mode == "simulation":
                frame_raw = np.zeros((480, 640, 3), dtype="uint8")
                
                # Make simulated canvas more complex & interactive
                cv2.rectangle(frame_raw, (0, 0), (640, 480), (18, 12, 8), -1) # Sleek cyber dark base
                
                # Draw technical crosshair/grid lines
                cv2.line(frame_raw, (40, 240), (600, 240), (40, 30, 20), 1)
                cv2.line(frame_raw, (320, 40), (320, 440), (40, 30, 20), 1)
                cv2.circle(frame_raw, (320, 240), 100, (40, 30, 20), 1)
                cv2.circle(frame_raw, (320, 240), 5, (0, 242, 254), -1) # glowing cyan center point
                
                # Draw border HUD corners
                HUD_COLOR = (120, 80, 30) # High-tech blue HUD
                # Top Left
                cv2.line(frame_raw, (10, 10), (40, 10), HUD_COLOR, 2)
                cv2.line(frame_raw, (10, 10), (10, 40), HUD_COLOR, 2)
                # Top Right
                cv2.line(frame_raw, (630, 10), (600, 10), HUD_COLOR, 2)
                cv2.line(frame_raw, (630, 10), (630, 40), HUD_COLOR, 2)
                # Bottom Left
                cv2.line(frame_raw, (10, 470), (40, 470), HUD_COLOR, 2)
                cv2.line(frame_raw, (10, 470), (10, 440), HUD_COLOR, 2)
                # Bottom Right
                cv2.line(frame_raw, (630, 470), (600, 470), HUD_COLOR, 2)
                cv2.line(frame_raw, (630, 470), (630, 440), HUD_COLOR, 2)
                
                # Draw UI Text
                cv2.putText(frame_raw, "SIMULATION NODE - GUARDSHIELD AI", (20, 35),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 242, 254), 1)
                cv2.putText(frame_raw, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), (430, 35),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 242, 254), 1)
                
                # Simulate a moving person if System is ARMED or on demand
                sim_person_x += 5 * sim_person_dir
                if sim_person_x > 450:
                    sim_person_dir = -1
                elif sim_person_x < 50:
                    sim_person_dir = 1
                
                # Let's run a continuous simulation: intruder appears for 15 seconds, disappears for 15 seconds
                curr_second = int(time.time()) % 30
                simulated_intrusion = curr_second < 15
                
                if not system_config["system_armed"]:
                    simulated_intrusion = False
                    
                mock_boxes = []
                if simulated_intrusion:
                    # Draw a mock target intruder box
                    x1, y1 = sim_person_x, sim_person_y
                    x2, y2 = x1 + 120, y1 + 240
                    mock_boxes.append((x1, y1, x2, y2))
                    
                    # Draw visual simulated humanoid box in high-res frame
                    cv2.rectangle(frame_raw, (x1, y1), (x2, y2), (54, 51, 255), 2) # Neon Red Alert Box
                    cv2.rectangle(frame_raw, (x1, y1 - 25), (x1 + 100, y1), (54, 51, 255), -1)
                    cv2.putText(frame_raw, "INTRUDER 94%", (x1 + 5, y1 - 8),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                    
                    # Simulated overlay lines pointing to target
                    cv2.line(frame_raw, (320, 240), (int((x1+x2)/2), int((y1+y2)/2)), (0, 165, 255), 1)
                
                detected_boxes = mock_boxes
                is_person_detected = len(mock_boxes) > 0
                
            raw_frame = frame_raw.copy()
            
            # --- 2. RENDER OVERLAYS & DETECTION BOXES ---
            display_frame = frame_raw.copy()
            
            # Use local reference to avoid list-size changes during iteration
            local_boxes = list(detected_boxes)
            for x1, y1, x2, y2 in local_boxes:
                # Draw neon red alarm rectangle
                cv2.rectangle(display_frame, (x1, y1), (x2, y2), (54, 51, 255), 2)
                # Draw corner brackets on targets for high-tech aesthetic
                offset = 15
                # Top-left corner
                cv2.line(display_frame, (x1, y1), (x1 + offset, y1), (0, 242, 254), 2)
                cv2.line(display_frame, (x1, y1), (x1, y1 + offset), (0, 242, 254), 2)
                # Top-right corner
                cv2.line(display_frame, (x2, y1), (x2 - offset, y1), (0, 242, 254), 2)
                cv2.line(display_frame, (x2, y1), (x2, y1 + offset), (0, 242, 254), 2)
                # Bottom-left corner
                cv2.line(display_frame, (x1, y2), (x1 + offset, y2), (0, 242, 254), 2)
                cv2.line(display_frame, (x1, y2), (x1, y2 - offset), (0, 242, 254), 2)
                # Bottom-right corner
                cv2.line(display_frame, (x2, y2), (x2 - offset, y2), (0, 242, 254), 2)
                cv2.line(display_frame, (x2, y2), (x2, y2 - offset), (0, 242, 254), 2)
                
            # Write high-tech HUD overlay onto display frame
            # 1. Arm Status Badge
            arm_color = (0, 180, 80) if system_config["system_armed"] else (100, 100, 100)
            arm_text = "SYSTEM ARMED" if system_config["system_armed"] else "SYSTEM DISARMED"
            cv2.rectangle(display_frame, (20, 420), (220, 455), arm_color, -1)
            cv2.putText(display_frame, arm_text, (35, 442),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
            
            # 2. Intrusion Alert Badge
            if is_person_detected and system_config["system_armed"]:
                cv2.rectangle(display_frame, (420, 420), (620, 455), (54, 51, 255), -1) # Neon red alert badge
                cv2.putText(display_frame, "INTRUSION DETECTED", (430, 442),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 2)
            else:
                cv2.rectangle(display_frame, (420, 420), (620, 455), (30, 30, 30), -1)
                cv2.putText(display_frame, "SCANNING AREA", (465, 442),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)
                
            # 3. Calculation of FPS
            now = time.time()
            fps_camera = 1 / (now - prev_time)
            prev_time = now
            
            # Draw FPS
            cv2.putText(display_frame, f"STREAM FPS: {fps_camera:.1f}", (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 242, 254), 1)
            cv2.putText(display_frame, f"AI FPS: {detection_fps:.1f}", (20, 70),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 242, 254), 1)
            cv2.putText(display_frame, f"CAM NODE: {self.mode.upper()}", (20, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 242, 254), 1)
            
            # --- 3. JPEG COMPRESSION (ONCE IN BACKGROUND) ---
            # Using quality=80 significantly reduces image size, maximizing streaming performance and saving CPU
            ret, buffer = cv2.imencode('.jpg', display_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if ret:
                encoded_jpeg_frame = buffer.tobytes()
            
            # Control frame rate loop to match butter-smooth 30fps
            sleep_time = 0.033 - (time.time() - start_loop)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def run_inference(self):
        global raw_frame, detected_boxes, is_person_detected, detection_fps, last_email_time
        
        self.init_model()
        
        # Optimize PyTorch core threading to utilize 4 threads (max CPU on Pi 5)
        try:
            import torch
            torch.set_num_threads(4)
            print("[YOLO THREAD] PyTorch successfully configured to use 4 threads.")
        except Exception as e:
            print(f"[YOLO THREAD] PyTorch thread optimization skipped: {e}")
            
        consecutive_detections = 0
        first_detect_time = None
        last_seen_time = None
        
        prev_time = time.time()
        print("[YOLO THREAD] Async YOLO Inference loop started.")
        
        while self.running:
            start_loop = time.time()
            
            # In simulation, the mock bounding box is generated at capture level
            if self.mode == "simulation":
                time.sleep(0.1)
                continue
                
            if raw_frame is None:
                time.sleep(0.02)
                continue
                
            # Perform a fast copy of raw frame & resize for AI detection speedup
            frame_local = raw_frame.copy()
            frame_detect = cv2.resize(frame_local, (256, 256))
            
            detected = []
            if self.model is not None:
                try:
                    results = self.model(
                        frame_detect,
                        classes=[0], # Person class
                        imgsz=256,
                        conf=system_config["confidence"],
                        device="cpu",
                        verbose=False
                    )
                    
                    # Scale boxes back to frame_local dimensions
                    scale_x = frame_local.shape[1] / 256.0
                    scale_y = frame_local.shape[0] / 256.0
                    
                    for box in results[0].boxes:
                        bx1, by1, bx2, by2 = map(int, box.xyxy[0])
                        x1 = int(bx1 * scale_x)
                        y1 = int(by1 * scale_y)
                        x2 = int(bx2 * scale_x)
                        y2 = int(by2 * scale_y)
                        
                        area = (x2 - x1) * (y2 - y1)
                        if area >= system_config["min_box_area"]:
                            detected.append((x1, y1, x2, y2))
                except Exception as e:
                    print(f"[YOLO THREAD] Model inference error: {e}")
                    
            # Update global variables atomic values
            detected_boxes = detected
            is_person_detected = len(detected) > 0
            
            # --- 3. FILTER / STABILIZATION / ARMED TRIGGER LOGIC ---
            detect_time = time.time()
            if system_config["system_armed"]:
                if is_person_detected:
                    last_seen_time = detect_time
                    if first_detect_time is None:
                        first_detect_time = detect_time
                    consecutive_detections += 1
                else:
                    # Reset if person disappears for more than 3 seconds
                    if last_seen_time is not None and (detect_time - last_seen_time) >= 3.0:
                        consecutive_detections = 0
                        first_detect_time = None
                        last_seen_time = None
                        
                stable_duration = (detect_time - first_detect_time) if first_detect_time else 0.0
                
                # Check alert trigger threshold
                ready_to_alert = (
                    consecutive_detections >= 4 # stable frames count
                    and stable_duration >= system_config["stable_seconds"]
                )
                
                if ready_to_alert:
                    # 1. Trigger Buzzer immediately if configured
                    if system_config["buzzer_alerts_enabled"] and not hw_controller.states["buzzer"]:
                        hw_controller.set_buzzer(True)
                        add_event("⚠️ CẢNH BÁO ĐỘT NHẬP! Đã kích hoạt còi hú báo động.", "danger")
                        
                    # 2. Trigger Email alerts if cooldown has passed
                    cooldown_ok = (detect_time - last_email_time) >= system_config["cooldown_seconds"]
                    if system_config["email_alerts_enabled"] and cooldown_ok and not email_sending:
                        # Capture image snapshot to send
                        snapshot_path = os.path.join(BASE_DIR, "guardshield_snapshot.jpg")
                        cv2.imwrite(snapshot_path, frame_local)
                        
                        # Start sending email in a background daemon thread
                        threading.Thread(
                            target=send_email_alert,
                            args=(snapshot_path,),
                            daemon=True
                        ).start()
                        last_email_time = detect_time
            else:
                # System disarmed: Turn off buzzer/siren if it was on
                if hw_controller.states["buzzer"]:
                    hw_controller.set_buzzer(False)
                consecutive_detections = 0
                first_detect_time = None
                
            # Calculation of FPS
            now = time.time()
            detection_fps = 1 / (now - prev_time)
            prev_time = now
            
            # Limit YOLO processing slightly to prevent CPU thermal throttling (target ~8fps)
            sleep_time = 0.12 - (time.time() - start_loop)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def stop(self):
        self.running = False
        if self.picam2:
            try:
                self.picam2.stop()
            except:
                pass
        if self.cam:
            try:
                self.cam.release()
            except:
                pass
        print("[CAMERA] Camera detector threads stopped.")

camera_detector = CameraDetector()

# ----------------- FLASK WEB SERVER INITS -----------------
app = Flask(__name__, static_folder="website", static_url_path="")

# Disable access logs to prevent console cluttering
import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

def get_cpu_temp():
    try:
        # Works on Raspberry Pi OS
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp = float(f.read()) / 1000.0
            return round(temp, 1)
    except:
        return 42.5  # Standard mockup temp for PC simulation

@app.route('/')
def index():
    return send_from_directory(WEBSITE_DIR, "index.html")

# Static files fallback
@app.route('/style.css')
def style():
    return send_from_directory(WEBSITE_DIR, "style.css")

@app.route('/app.js')
def app_js():
    return send_from_directory(WEBSITE_DIR, "app.js")

@app.route('/logo.png')
def logo():
    return send_from_directory(WEBSITE_DIR, "logo.png")

# Real-time Video Stream Endpoint (MJPEG)
@app.route('/video_feed')
def video_feed():
    def generate():
        global encoded_jpeg_frame
        while True:
            if encoded_jpeg_frame is not None:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + encoded_jpeg_frame + b'\r\n')
            time.sleep(0.033) # limit to 30 FPS stream
            
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

# API Endpoints
@app.route('/api/status', methods=['GET'])
def api_status():
    status_data = {
        "system_armed": system_config["system_armed"],
        "email_alerts_enabled": system_config["email_alerts_enabled"],
        "buzzer_alerts_enabled": system_config["buzzer_alerts_enabled"],
        "device_1_state": hw_controller.states[1],
        "device_2_state": hw_controller.states[2],
        "device_3_state": hw_controller.states[3],
        "buzzer_state": hw_controller.states["buzzer"],
        "device_1_name": system_config["device_1_name"],
        "device_2_name": system_config["device_2_name"],
        "device_3_name": system_config["device_3_name"],
        "is_person_detected": is_person_detected,
        "detection_fps": round(detection_fps, 1),
        "cpu_temp": get_cpu_temp(),
        "camera_mode": camera_detector.mode,
        "email_sending": email_sending,
        "gpio_mode": hw_controller.mode
    }
    return jsonify(status_data)

@app.route('/api/control_device', methods=['POST'])
def api_control_device():
    data = request.json or {}
    device_id = data.get("device_id") # 1, 2, 3 or 'buzzer'
    state = data.get("state") # True/False
    
    if state is None or device_id is None:
        return jsonify({"success": False, "error": "Invalid arguments"}), 400
        
    if device_id in [1, 2, 3]:
        hw_controller.set_device(device_id, state)
        name = system_config.get(f"device_{device_id}_name")
        add_event(f"Thiết bị '{name}' được thay đổi trạng thái sang: {'BẬT' if state else 'TẮT'} thủ công.", "info")
        return jsonify({"success": True})
        
    elif device_id == "buzzer":
        hw_controller.set_buzzer(state)
        add_event(f"Còi còi báo động được {'BẬT' if state else 'TẮT'} thủ công.", "warning")
        return jsonify({"success": True})
        
    return jsonify({"success": False, "error": "Unknown device"}), 400

@app.route('/api/toggle_alert', methods=['POST'])
def api_toggle_alert():
    data = request.json or {}
    alert_type = data.get("type") # 'email', 'buzzer' or 'system'
    state = data.get("state") # True/False
    
    if state is None or alert_type is None:
        return jsonify({"success": False, "error": "Invalid arguments"}), 400
        
    if alert_type == "email":
        system_config["email_alerts_enabled"] = bool(state)
        save_config(system_config)
        add_event(f"Thay đổi cấu hình: {'KÍCH HOẠT' if state else 'VÔ HIỆU HÓA'} cảnh báo qua Email.", "info")
        return jsonify({"success": True})
        
    elif alert_type == "buzzer":
        system_config["buzzer_alerts_enabled"] = bool(state)
        save_config(system_config)
        add_event(f"Thay đổi cấu hình: {'KÍCH HOẠT' if state else 'VÔ HIỆU HÓA'} còi Buzzer khi có báo động.", "info")
        return jsonify({"success": True})
        
    elif alert_type == "system":
        system_config["system_armed"] = bool(state)
        save_config(system_config)
        add_event(f"🛡️ HỆ THỐNG AN NINH: {'KÍCH HOẠT GIÁM SÁT (ARMED)' if state else 'TẮT GIÁM SÁT (DISARMED)'}.", "success" if state else "warning")
        
        # Turn off alarms immediately on disarm
        if not state:
            hw_controller.set_buzzer(False)
            
        return jsonify({"success": True})
        
    return jsonify({"success": False, "error": "Unknown alert type"}), 400

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    global system_config
    if request.method == 'GET':
        return jsonify(system_config)
    else:
        new_config = request.json or {}
        # Update config fields safely
        for key in system_config.keys():
            if key in new_config:
                # Maintain data types
                if isinstance(system_config[key], bool):
                    system_config[key] = bool(new_config[key])
                elif isinstance(system_config[key], float):
                    system_config[key] = float(new_config[key])
                elif isinstance(system_config[key], int):
                    system_config[key] = int(new_config[key])
                else:
                    system_config[key] = str(new_config[key])
                    
        save_config(system_config)
        add_event("Cấu hình hệ thống an ninh đã được cập nhật thành công.", "success")
        return jsonify({"success": True})

@app.route('/api/logs', methods=['GET'])
def api_logs():
    return jsonify(event_logs)

@app.route('/api/manual_trigger', methods=['POST'])
def api_manual_trigger():
    # Force a manual security intrusion simulation trigger (great for testing alerts!)
    add_event("🚨 KÍCH HOẠT BÁO ĐỘNG KHẨN CẤP THỦ CÔNG 🚨", "danger")
    if system_config["buzzer_alerts_enabled"]:
        hw_controller.set_buzzer(True)
        
    if system_config["email_alerts_enabled"] and not email_sending:
        # Send instant email using last captured frame
        snapshot_path = os.path.join(BASE_DIR, "guardshield_snapshot.jpg")
        if raw_frame is not None:
            cv2.imwrite(snapshot_path, raw_frame)
            
        threading.Thread(
            target=send_email_alert,
            args=(snapshot_path,),
            daemon=True
        ).start()
        
    return jsonify({"success": True})

# ----------------- MAIN LAUNCH SEQUENCE -----------------
if __name__ == "__main__":
    # Create a clean exit sequence
    try:
        # Start camera acquisition loop in background
        capture_thread = threading.Thread(target=camera_detector.run_capture, daemon=True)
        capture_thread.start()
        
        # Start YOLO async inference loop in background
        yolo_thread = threading.Thread(target=camera_detector.run_inference, daemon=True)
        yolo_thread.start()
        
        # Start Flask Server
        print("[SYSTEM] GuardShield AI Security server launching at http://0.0.0.0:5000")
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
        
    except KeyboardInterrupt:
        print("\n[SYSTEM] Server shutting down safely...")
    finally:
        camera_detector.stop()
        hw_controller.cleanup()
        print("[SYSTEM] All background systems terminated safely.")
