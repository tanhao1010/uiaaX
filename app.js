const app = {
  // ── SYSTEM STATE ──
  state: {
    isAuthenticated: false,
    systemArmed: false,
    emailAlertsEnabled: false,
    buzzerAlertsEnabled: false,
    devices: {
      1: { name: "Thiết bị 1", state: false },
      2: { name: "Thiết bị 2", state: false },
      3: { name: "Thiết bị 3", state: false }
    },
    buzzerState: false,
    cpuTemp: 0.0,
    fps: 0.0,
    isPersonDetected: false,
    cameraMode: "simulation",
    eventLogs: [],
    pollingInterval: null
  },

  // ── INITIALIZATION ──
  init() {
    this.checkAuth();
    if (this.state.isAuthenticated) {
      this.startApp();
    }
  },

  checkAuth() {
    const savedAuth = localStorage.getItem('guardshield_auth');
    if (savedAuth === 'true') {
      this.state.isAuthenticated = true;
      document.getElementById('login-view').classList.remove('active');
      document.getElementById('main-layout').classList.add('active');
    } else {
      this.state.isAuthenticated = false;
      document.getElementById('login-view').classList.add('active');
      document.getElementById('main-layout').classList.remove('active');
    }
  },

  login() {
    const user = document.getElementById('username').value;
    const pass = document.getElementById('password').value;

    if (user === 'admin' && pass === '123456') {
      this.state.isAuthenticated = true;
      localStorage.setItem('guardshield_auth', 'true');
      document.getElementById('login-view').classList.remove('active');
      document.getElementById('main-layout').classList.add('active');
      this.startApp();
      this.showToast('Hệ thống an ninh đã kích hoạt thành công!');
    } else {
      this.showToast('Sai thông tin đăng nhập!');
    }
  },

  logout() {
    this.state.isAuthenticated = false;
    localStorage.removeItem('guardshield_auth');
    if (this.state.pollingInterval) {
      clearInterval(this.state.pollingInterval);
    }
    document.getElementById('main-layout').classList.remove('active');
    document.getElementById('login-view').classList.add('active');
    document.getElementById('password').value = '';
    this.showToast('Đã đăng xuất khỏi hệ thống.');
  },

  startApp() {
    this.navigate('dashboard');
    this.loadConfig(); // Fetch configuration variables from Pi 5
    this.loadLogs();   // Fetch security logs
    
    // Start continuous status polling every 1 second (1000ms)
    this.state.pollingInterval = setInterval(() => this.pollStatus(), 1000);
    this.pollStatus(); // Immediate initial pull
  },

  // ── NAVIGATION MODULE ──
  navigate(pageId) {
    // Toggle active pages
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    const targetPage = document.getElementById(pageId);
    if (targetPage) targetPage.classList.add('active');

    // Update bottom nav bar highlight
    document.querySelectorAll('.bnav-item').forEach(el => el.classList.remove('active'));
    const activeNav = document.querySelector(`.bnav-item[data-target="${pageId}"]`);
    if (activeNav) activeNav.classList.add('active');

    // Special triggers on navigation
    if (pageId === 'logs') {
      this.loadLogs();
    } else if (pageId === 'settings') {
      this.loadConfig();
    }

    window.scrollTo(0, 0);
  },

  // ── DATA POLLING & STATUS SYNC ──
  async pollStatus() {
    try {
      const response = await fetch('/api/status');
      if (!response.ok) throw new Error("Offline");
      
      const data = await response.json();
      
      // Update local states
      this.state.systemArmed = data.system_armed;
      this.state.emailAlertsEnabled = data.email_alerts_enabled;
      this.state.buzzerAlertsEnabled = data.buzzer_alerts_enabled;
      this.state.devices[1] = { name: data.device_1_name, state: data.device_1_state };
      this.state.devices[2] = { name: data.device_2_name, state: data.device_2_state };
      this.state.devices[3] = { name: data.device_3_name, state: data.device_3_state };
      this.state.buzzerState = data.buzzer_state;
      this.state.cpuTemp = data.cpu_temp;
      this.state.fps = data.detection_fps;
      this.state.isPersonDetected = data.is_person_detected;
      this.state.cameraMode = data.camera_mode;
      
      // Update UI displays
      this.updateStatusUI(true);
    } catch (error) {
      console.error("Polling error:", error);
      this.updateStatusUI(false); // Update UI to reflect offline state
    }
  },

  updateStatusUI(isOnline) {
    const statusDot = document.getElementById('system-status-dot');
    const statusText = document.getElementById('system-status-text');
    const cameraOffline = document.getElementById('camera-offline');
    const liveFps = document.getElementById('live-fps');
    const cameraModeBadge = document.getElementById('camera-mode-badge');
    const cameraHwInfo = document.getElementById('camera-hw-info');
    
    if (!isOnline) {
      // Offline HUD Display
      if (statusDot) {
        statusDot.className = 'status-dot';
        statusDot.style.background = 'var(--red)';
        statusDot.style.boxShadow = '0 0 10px var(--red)';
      }
      if (statusText) statusText.innerText = "Pi 5 Mất Kết Nối";
      if (cameraOffline) cameraOffline.classList.add('active');
      if (liveFps) liveFps.innerText = "FPS: 0.0";
      return;
    }
    
    // Online Display
    if (cameraOffline) cameraOffline.classList.remove('active');
    if (liveFps) liveFps.innerText = `AI FPS: ${this.state.fps.toFixed(1)}`;
    if (cameraModeBadge) {
      if (this.state.isPersonDetected && this.state.systemArmed) {
        cameraModeBadge.innerText = "🚨 CẢNH BÁO XÂM NHẬP 🚨";
        cameraModeBadge.parentElement.style.background = 'rgba(255, 71, 87, 0.25)';
        cameraModeBadge.parentElement.style.borderColor = 'rgba(255, 71, 87, 0.6)';
        cameraModeBadge.style.color = '#ff4757';
      } else {
        cameraModeBadge.innerText = this.state.cameraMode === 'simulation' ? "SIMULATOR ACTIVE" : "LIVE AI ACTIVE";
        cameraModeBadge.parentElement.style.background = '';
        cameraModeBadge.parentElement.style.borderColor = '';
        cameraModeBadge.style.color = '';
      }
    }
    
    if (cameraHwInfo) {
      cameraHwInfo.innerText = `Hardware: ${this.state.cameraMode === 'picamera2' ? 'CSI Camera' : this.state.cameraMode === 'webcam' ? 'USB Webcam' : 'Simulated Node'}`;
    }

    // Top Brand System Status Badge
    if (statusDot) {
      statusDot.className = 'status-dot';
      if (this.state.systemArmed) {
        statusDot.style.background = 'var(--green)';
        statusDot.style.boxShadow = '0 0 10px var(--green)';
        if (statusText) statusText.innerText = "Hệ thống: ARMED";
      } else {
        statusDot.style.background = 'var(--text-3)';
        statusDot.style.boxShadow = 'none';
        if (statusText) statusText.innerText = "Hệ thống: DISARMED";
      }
    }

    // Central Security Banner
    const homeArmStatus = document.getElementById('home-arm-status');
    if (homeArmStatus) {
      if (!this.state.systemArmed) {
        homeArmStatus.innerText = "VÔ HIỆU HÓA";
        homeArmStatus.style.color = "var(--text-3)";
      } else if (this.state.isPersonDetected) {
        homeArmStatus.innerText = "🚨 ĐỘT NHẬP 🚨";
        homeArmStatus.style.color = "var(--red)";
      } else {
        homeArmStatus.innerText = "AN TOÀN";
        homeArmStatus.style.color = "var(--green)";
      }
    }

    // Update Diagnostics
    const tempEl = document.getElementById('home-cpu-temp');
    if (tempEl) tempEl.innerText = `${this.state.cpuTemp.toFixed(1)}°C`;

    // Sync armed panic controls buttons
    const btnMasterArm = document.getElementById('btn-master-arm');
    if (btnMasterArm) {
      if (this.state.systemArmed) {
        btnMasterArm.innerHTML = `
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="width:24px;height:24px;margin-bottom:6px;">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
            <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
          </svg>
          HỦY GIÁM SÁT SYSTEM
        `;
        btnMasterArm.className = "btn-emergency btn-arm-toggle active";
      } else {
        btnMasterArm.innerHTML = `
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="width:24px;height:24px;margin-bottom:6px;">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
            <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
          </svg>
          KÍCH HOẠT HỆ THỐNG
        `;
        btnMasterArm.className = "btn-emergency btn-arm-toggle";
      }
    }

    // Sync Alert Mode configuration Toggles
    const toggleEmail = document.getElementById('toggle-email-alerts');
    if (toggleEmail) toggleEmail.checked = this.state.emailAlertsEnabled;

    const toggleBuzzer = document.getElementById('toggle-buzzer-alerts');
    if (toggleBuzzer) toggleBuzzer.checked = this.state.buzzerAlertsEnabled;

    // Sync 3 external smart devices switches & card classes
    for (let id = 1; id <= 3; id++) {
      const dev = this.state.devices[id];
      const switchEl = document.getElementById(`switch-dev-${id}`);
      const labelEl = document.getElementById(`label-dev-${id}`);
      const statusEl = document.getElementById(`status-dev-${id}`);
      const cardEl = document.getElementById(`device-card-${id}`);
      
      if (switchEl) switchEl.checked = dev.state;
      if (labelEl) labelEl.innerText = dev.name;
      if (statusEl) {
        statusEl.innerText = dev.state ? "ĐANG BẬT" : "ĐANG TẮT";
        statusEl.className = dev.state ? "dev-status-text active" : "dev-status-text";
      }
      if (cardEl) {
        if (dev.state) cardEl.classList.add('active');
        else cardEl.classList.remove('active');
      }
    }

    // Sync Manual Siren buzzer switch
    const switchBuz = document.getElementById('switch-buzzer');
    if (switchBuz) switchBuz.checked = this.state.buzzerState;
  },

  // ── DEVICE ACTIONS & TRIGGERS ──
  async controlDevice(deviceId, state) {
    try {
      const response = await fetch('/api/control_device', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id: deviceId, state: state })
      });
      
      if (response.ok) {
        if (deviceId === 'buzzer') {
          this.showToast(state ? "Đã Kích Hoạt Còi Hú Cảnh Báo!" : "Đã Tắt Còi Báo Động");
        } else {
          const devName = this.state.devices[deviceId]?.name || `Thiết bị ${deviceId}`;
          this.showToast(`${state ? 'Đã bật' : 'Đã tắt'} ${devName}`);
        }
        this.pollStatus(); // Sync state immediately
      } else {
        throw new Error("Failed to trigger device");
      }
    } catch (e) {
      this.showToast("Lỗi gửi lệnh điều khiển GPIO!");
      console.error(e);
    }
  },

  async toggleAlertMode(alertType, state) {
    try {
      const response = await fetch('/api/toggle_alert', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: alertType, state: state })
      });
      
      if (response.ok) {
        const typeVietnamese = alertType === 'email' ? 'Cảnh báo Email' : 'Cảnh báo Còi Hú';
        this.showToast(`${state ? 'Đã kích hoạt' : 'Đã vô hiệu hóa'} ${typeVietnamese}`);
        this.pollStatus();
      } else {
        throw new Error("Failed to toggle alert configuration");
      }
    } catch (e) {
      this.showToast("Không thể thay đổi cấu hình báo động!");
      console.error(e);
    }
  },

  async toggleMasterArm() {
    const nextState = !this.state.systemArmed;
    try {
      const response = await fetch('/api/toggle_alert', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'system', state: nextState })
      });
      
      if (response.ok) {
        this.showToast(nextState ? "🛡️ HỆ THỐNG AN NINH: ĐÃ KÍCH HOẠT (ARMED)!" : "⚠️ HỆ THỐNG AN NINH: ĐÃ TẮT (DISARMED)");
        this.pollStatus();
      } else {
        throw new Error("Arming error");
      }
    } catch (e) {
      this.showToast("Không thể kết nối đến máy chủ an ninh!");
      console.error(e);
    }
  },

  async triggerPanic() {
    try {
      const response = await fetch('/api/manual_trigger', { method: 'POST' });
      if (response.ok) {
        this.showToast("🚨 BÁO ĐỘNG KHẨN CẤP ĐÃ ĐƯỢC PHÁT KHỞI THÀNH CÔNG!");
        this.pollStatus();
      } else {
        throw new Error("Panic fail");
      }
    } catch (e) {
      this.showToast("Lỗi kích hoạt khẩn cấp!");
      console.error(e);
    }
  },

  // ── CONFIGURATION PANEL ──
  async loadConfig() {
    try {
      const response = await fetch('/api/config');
      if (response.ok) {
        const config = await response.json();
        
        // Load settings to HTML input fields
        const fields = [
          'sender_email', 'app_password', 'receiver_email', 
          'confidence', 'cooldown_seconds', 'stable_seconds',
          'device_1_name', 'device_2_name', 'device_3_name'
        ];
        
        fields.forEach(field => {
          const input = document.getElementById(field);
          if (input) {
            input.value = config[field] !== undefined ? config[field] : '';
          }
        });
      }
    } catch (e) {
      console.error("Config fetch error:", e);
    }
  },

  async saveSettings() {
    const newConfig = {};
    const fields = [
      'sender_email', 'app_password', 'receiver_email', 
      'confidence', 'cooldown_seconds', 'stable_seconds',
      'device_1_name', 'device_2_name', 'device_3_name'
    ];
    
    // Collect settings data
    fields.forEach(field => {
      const input = document.getElementById(field);
      if (input) {
        if (input.type === 'number') {
          newConfig[field] = parseFloat(input.value);
        } else {
          newConfig[field] = input.value;
        }
      }
    });

    try {
      const response = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newConfig)
      });
      
      if (response.ok) {
        this.showToast("⚙️ Đã lưu cấu hình an ninh lên Pi 5 thành công!");
        this.pollStatus(); // Pull status immediately to update labels
      } else {
        throw new Error("Config save failed");
      }
    } catch (e) {
      this.showToast("Lỗi lưu trữ cấu hình trên Pi 5!");
      console.error(e);
    }
  },

  // ── HISTORICAL LOG EVENTS ──
  async loadLogs() {
    const listWrapper = document.getElementById('event-logs-list');
    try {
      const response = await fetch('/api/logs');
      if (response.ok) {
        const logs = await response.json();
        this.state.eventLogs = logs;
        
        if (logs.length === 0) {
          listWrapper.innerHTML = `<div class="log-empty-state">Hộp nhật ký trống. Chưa ghi nhận sự kiện bảo mật nào.</div>`;
          return;
        }

        let html = '';
        logs.forEach(log => {
          let badgeClass = 'log-badge-info';
          if (log.category === 'success') badgeClass = 'log-badge-success';
          else if (log.category === 'danger') badgeClass = 'log-badge-danger';
          else if (log.category === 'warning') badgeClass = 'log-badge-warning';
          
          html += `
            <div class="log-item fade-up">
              <div class="log-item-meta">
                <span class="log-time">${log.timestamp}</span>
                <span class="log-badge ${badgeClass}">${log.category.toUpperCase()}</span>
              </div>
              <div class="log-desc">${log.description}</div>
            </div>
          `;
        });
        listWrapper.innerHTML = html;
      }
    } catch (e) {
      listWrapper.innerHTML = `<div class="log-empty-state" style="color:var(--red);">Không thể tải nhật ký an ninh</div>`;
      console.error(e);
    }
  },

  // ── UTILITIES (TOAST DIALOGS) ──
  showToast(msg) {
    const t = document.getElementById('toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 2800);
  }
};

// Start application on page load
window.addEventListener('DOMContentLoaded', () => app.init());
