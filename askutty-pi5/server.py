import os
import json
import subprocess
import psutil
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string

from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
MEMORY_FILE = 'memory.json'
ACTION_LOG = 'action_log.json'
VERSION = "0.6"
ASKUTTY_TOKEN = os.getenv("ASKUTTY_TOKEN")

def check_auth():
    token = request.headers.get('X-ASKUTTY-TOKEN') or request.args.get('token')
    return token == ASKUTTY_TOKEN

def unauthorized():
    return render_template_string(HTML_TEMPLATE, version=VERSION, result="ASKUTTY locked. Token required."), 403

# Ensure files exist
if not os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, 'w') as f:
        json.dump({"entries": []}, f)

if not os.path.exists(ACTION_LOG):
    with open(ACTION_LOG, 'w') as f:
        json.dump([], f)

SAFE_COMMANDS = {
    "disk check": "df -h /",
    "cpu status": "uptime",
    "ram status": "free -h",
    "service status": "systemctl is-active askutty-pi5.service",
    "github status": "git status",
    "askutty status": "systemctl is-active askutty-pi5.service",
    "war room status": "systemctl is-active nova-war-room",
    "network status": "hostname -I"
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ASKUTTY Pi5 Brain v{{ version }}</title>
    <style>
        :root {
            --bg-color: #050505;
            --card-bg: #0a0a0a;
            --text-color: #e0e0e0;
            --accent-color: #00f3ff;
            --secondary-accent: #ff00ff;
            --success-color: #00ff41;
            --border-color: #1a1a1a;
            --neon-glow: 0 0 10px rgba(0, 243, 255, 0.5);
        }
        body {
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: 'Courier New', Courier, monospace;
            margin: 0;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 20px;
            min-height: 100vh;
            background-image: linear-gradient(rgba(0, 243, 255, 0.03) 1px, transparent 1px),
                              linear-gradient(90deg, rgba(0, 243, 255, 0.03) 1px, transparent 1px);
            background-size: 30px 30px;
        }
        .container {
            width: 100%;
            max-width: 600px;
        }
        .card {
            background-color: var(--card-bg);
            border: 1px solid var(--accent-color);
            border-radius: 4px;
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: var(--neon-glow);
            position: relative;
            overflow: hidden;
        }
        .card::before {
            content: "";
            position: absolute;
            top: 0; left: 0; width: 100%; height: 2px;
            background: linear-gradient(90deg, transparent, var(--accent-color), transparent);
        }
        h1 { 
            color: var(--accent-color); 
            text-align: center;
            margin-top: 0;
            font-size: 1.8rem;
            text-transform: uppercase;
            letter-spacing: 4px;
            text-shadow: var(--neon-glow);
        }
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
            margin-bottom: 20px;
        }
        @media (min-width: 480px) {
            .metrics-grid {
                grid-template-columns: repeat(4, 1fr);
            }
        }
        .metric-card {
            background: #000;
            border: 1px solid var(--border-color);
            padding: 15px;
            text-align: center;
            border-radius: 4px;
        }
        .metric-value {
            font-size: 1.2rem;
            color: var(--secondary-accent);
            display: block;
            margin-bottom: 5px;
            text-shadow: 0 0 5px rgba(255, 0, 255, 0.5);
        }
        .metric-label {
            font-size: 0.6rem;
            text-transform: uppercase;
            color: #666;
            letter-spacing: 1px;
        }
        .button-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-top: 20px;
        }
        .btn {
            background-color: transparent;
            border: 1px solid var(--accent-color);
            color: var(--accent-color);
            padding: 12px;
            text-align: center;
            text-decoration: none;
            font-size: 13px;
            border-radius: 2px;
            cursor: pointer;
            transition: 0.3s;
            text-transform: uppercase;
            font-weight: bold;
            letter-spacing: 1px;
        }
        .btn:hover { 
            background-color: var(--accent-color);
            color: #000;
            box-shadow: var(--neon-glow);
        }
        .btn-primary {
            border-color: var(--secondary-accent);
            color: var(--secondary-accent);
        }
        .btn-primary:hover {
            background-color: var(--secondary-accent);
            color: #000;
            box-shadow: 0 0 15px rgba(255, 0, 255, 0.7);
        }
        
        .output {
            margin-top: 20px;
            padding: 16px;
            background-color: #000;
            border: 1px solid var(--border-color);
            border-radius: 4px;
            width: 100%;
            box-sizing: border-box;
            white-space: pre-wrap;
            font-family: 'Consolas', monospace;
            font-size: 14px;
            line-height: 1.5;
            color: var(--success-color);
        }
        .output::before {
            content: "> ";
        }
        form { width: 100%; }
        .input-group {
            display: flex;
            gap: 8px;
            margin-bottom: 12px;
        }
        input[type="text"] {
            flex-grow: 1;
            padding: 12px;
            border-radius: 2px;
            border: 1px solid var(--border-color);
            background: #000;
            color: var(--accent-color);
            font-size: 16px;
            font-family: inherit;
        }
        input[type="text"]:focus {
            outline: none;
            border-color: var(--accent-color);
            box-shadow: var(--neon-glow);
        }
        .voice-controls {
            display: flex;
            gap: 8px;
            margin-top: 8px;
        }
        #mic-msg {
            color: #ff0055;
            font-size: 12px;
            margin-top: 4px;
            display: none;
            text-align: center;
        }
        .status-tag {
            font-size: 10px;
            position: absolute;
            top: 10px;
            right: 10px;
            color: var(--success-color);
            text-transform: uppercase;
        }
        .status-tag::before {
            content: "● ";
            animation: blink 1s infinite;
        }
        @keyframes blink { 
            0% { opacity: 1; } 
            50% { opacity: 0.3; } 
            100% { opacity: 1; } 
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <span class="status-tag">System Live</span>
            <h1>ASKUTTY v{{ version }}</h1>
            
            <div class="metrics-grid">
                <div class="metric-card">
                    <span class="metric-value" id="cpu-val">--%</span>
                    <span class="metric-label">CPU</span>
                </div>
                <div class="metric-card">
                    <span class="metric-value" id="ram-val">--%</span>
                    <span class="metric-label">RAM</span>
                </div>
                <div class="metric-card">
                    <span class="metric-value" id="temp-val">--°C</span>
                    <span class="metric-label">TEMP</span>
                </div>
                <div class="metric-card">
                    <span class="metric-value" id="disk-val">--%</span>
                    <span class="metric-label">DISK</span>
                </div>
            </div>

            <form action="/ask" method="get" id="ask-form">
                <div class="input-group">
                    <input type="text" name="q" id="query-input" placeholder="Type or use voice..." required autocomplete="off">
                    <button type="submit" class="btn btn-primary" style="padding: 0 20px;">EXE</button>
                </div>
                <div class="voice-controls">
                    <button type="button" id="talk-btn" class="btn" style="flex: 1;">🎤 LISTEN</button>
                    <button type="button" id="speak-reply-btn" class="btn" style="flex: 1;">🔊 SPEAK</button>
                </div>
                <div id="mic-msg">Mic blocked. Use keyboard mic.</div>
            </form>

            <div style="border-top: 1px solid var(--border-color); margin-top: 20px; padding-top: 20px;">
                <div id="unlock-box" style="margin-top: 10px; padding: 10px; border: 1px solid var(--border-color); display: flex; gap: 8px;">
                    <input type="password" id="token-input" placeholder="Token" style="flex: 1; padding: 5px; background: #000; color: var(--accent-color); border: 1px solid var(--border-color);">
                    <button onclick="saveToken()" class="btn" style="padding: 5px 10px; font-size: 10px;">UNLOCK</button>
                </div>
                <h3 style="color: var(--accent-color); font-size: 0.8rem; text-transform: uppercase;">Askutty Safe Operator</h3>
                <div class="input-group">
                    <input type="text" id="op-query" placeholder="e.g. disk check" autocomplete="off">
                    <button type="button" onclick="planCommand()" class="btn" style="padding: 0 15px;">PLAN</button>
                </div>
                <div class="button-grid" style="margin-top: 10px;">
                    <button onclick="approveLatest()" class="btn btn-primary" style="font-size: 10px;">APPROVE LATEST</button>
                    <button onclick="viewLogs()" class="btn" style="font-size: 10px;">SHOW LOGS</button>
                </div>
            </div>

            <div class="button-grid">
                <a href="/status" class="btn">STATUS</a>
                <a href="/memory_ui" class="btn">MEMORY</a>
                <a href="/disk" class="btn">DISK</a>
                <a href="/warroom" class="btn">WAR ROOM</a>
            </div>

            {% if result %}
            <div class="output" id="output-text">{{ result }}</div>
            {% endif %}
        </div>
    </div>

    <script>
        const talkBtn = document.getElementById('talk-btn');
        const speakReplyBtn = document.getElementById('speak-reply-btn');
        const queryInput = document.getElementById('query-input');
        const micMsg = document.getElementById('mic-msg');
        const outputText = document.getElementById('output-text');
        const askForm = document.getElementById('ask-form');

        // Update Metrics
        async function updateMetrics() {
            try {
                const res = await fetch('/api/metrics');
                const data = await res.json();
                document.getElementById('cpu-val').textContent = data.cpu + '%';
                document.getElementById('ram-val').textContent = data.ram + '%';
                document.getElementById('temp-val').textContent = data.temp + '°C';
                document.getElementById('disk-val').textContent = data.disk + '%';
            } catch (e) {
                console.error("Metrics sync failed");
            }
        }
        setInterval(updateMetrics, 5000);
        updateMetrics();

        // Security
        function saveToken() {
            const token = document.getElementById('token-input').value;
            sessionStorage.setItem('askutty_token', token);
            alert('ASKUTTY token stored in session.');
        }
        function getToken() {
            return sessionStorage.getItem('askutty_token') || '';
        }

        // Safe Operator Actions
        function planCommand() {
            const q = document.getElementById('op-query').value;
            if (q) window.location.href = `/plan?q=${encodeURIComponent(q)}&token=${getToken()}`;
        }

        function approveLatest() {
            window.location.href = `/approve_latest?token=${getToken()}`;
        }

        function viewLogs() {
            window.location.href = `/logs?token=${getToken()}`;
        }

        // Speech Recognition
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (SpeechRecognition) {
            const recognition = new SpeechRecognition();
            recognition.continuous = false;
            recognition.lang = 'en-US';

            talkBtn.addEventListener('click', () => {
                recognition.start();
                talkBtn.textContent = 'LISTENING...';
                talkBtn.style.borderColor = 'var(--secondary-accent)';
                micMsg.style.display = 'none';
            });

            recognition.onresult = (event) => {
                const transcript = event.results[0][0].transcript;
                queryInput.value = transcript;
                talkBtn.textContent = '🎤 LISTEN';
                talkBtn.style.borderColor = 'var(--accent-color)';
                setTimeout(() => askForm.submit(), 500);
            };

            recognition.onerror = (event) => {
                talkBtn.textContent = '🎤 LISTEN';
                talkBtn.style.borderColor = 'var(--accent-color)';
                if (event.error === 'not-allowed') {
                    micMsg.style.display = 'block';
                }
            };

            recognition.onend = () => {
                talkBtn.textContent = '🎤 LISTEN';
                talkBtn.style.borderColor = 'var(--accent-color)';
            };
        } else {
            talkBtn.disabled = true;
            talkBtn.textContent = 'VOICE N/A';
        }

        // Speech Synthesis
        speakReplyBtn.addEventListener('click', () => {
            if (outputText) {
                const text = outputText.textContent;
                const utterance = new SpeechSynthesisUtterance(text);
                window.speechSynthesis.speak(utterance);
            }
        });
    </script>
</body>
</html>
"""

def get_temp():
    try:
        temp = subprocess.check_output(['vcgencmd', 'measure_temp']).decode('utf-8')
        return temp.replace("temp=", "").replace("'C\n", "")
    except:
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                return str(round(int(f.read()) / 1000, 1))
        except:
            return "N/A"

def get_disk_usage():
    try:
        usage = psutil.disk_usage('/')
        return usage.percent
    except:
        return "N/A"

@app.route('/api/metrics')
def api_metrics():
    return jsonify({
        "cpu": psutil.cpu_percent(),
        "ram": psutil.virtual_memory().percent,
        "temp": get_temp(),
        "disk": get_disk_usage()
    })

@app.route('/api/status')
def api_status():
    return jsonify({
        "ok": True,
        "version": VERSION,
        "uptime": subprocess.check_output(['uptime', '-p']).decode('utf-8').strip(),
        "cpu": psutil.cpu_percent(),
        "ram": psutil.virtual_memory().percent,
        "temp": get_temp(),
        "disk": get_disk_usage()
    })

@app.route('/api/memory')
def api_memory():
    if not check_auth(): return unauthorized()
    try:
        with open(MEMORY_FILE, 'r') as f:
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/health')
def health():
    return "OK"

def get_status_text():
    try:
        uptime = subprocess.check_output(['uptime', '-p']).decode('utf-8').strip()
        temp = get_temp()
        disk = get_disk_usage()
        return f"SYSTEM STATUS (v{VERSION}):\nUptime: {uptime}\nCore Temp: {temp}°C\nCPU: {psutil.cpu_percent()}%\nRAM: {psutil.virtual_memory().percent}%\nDISK: {disk}%"
    except Exception as e:
        return f"Error: {str(e)}"

def get_action_logs():
    try:
        with open(ACTION_LOG, 'r') as f:
            return json.load(f)
    except:
        return []

def save_action_logs(logs):
    with open(ACTION_LOG, 'w') as f:
        json.dump(logs, f, indent=4)

@app.route('/plan')
def plan():
    if not check_auth(): return unauthorized()
    q = request.args.get('q', '').lower().strip()
    command = SAFE_COMMANDS.get(q)
    
    if not command:
        # Check for blocked keywords
        blocked = ["rm ", "shutdown", "reboot", "kill ", "sudo ", "curl", "chmod", "token", "key"]
        for b in blocked:
            if b in q:
                return render_template_string(HTML_TEMPLATE, version=VERSION, result="BLOCKED: Destructive or sensitive command pattern detected.")
        return render_template_string(HTML_TEMPLATE, version=VERSION, result="UNKNOWN REQUEST. No safe plan available.")
    
    plan_id = str(int(time.time()))
    new_plan = {
        "id": plan_id,
        "user_request": q,
        "command": command,
        "risk_level": "Low",
        "explanation": f"Safe read-only command to check {q}.",
        "status": "pending",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    logs = get_action_logs()
    logs.append(new_plan)
    save_action_logs(logs)
    
    res = f"PLAN CREATED (ID: {plan_id})\\nRequest: {q}\\nCommand: {command}\\nRisk: Low\\nExplanation: {new_plan['explanation']}\\nStatus: PENDING\\n\\nRun /approve?id={plan_id} to execute."
    return render_template_string(HTML_TEMPLATE, version=VERSION, result=res.replace('\\n', '\n'))

@app.route('/approve')
def approve():
    if not check_auth(): return unauthorized()
    plan_id = request.args.get('id', '')
    logs = get_action_logs()
    
    plan_obj = next((p for p in logs if p['id'] == plan_id), None)
    if not plan_obj:
        return render_template_string(HTML_TEMPLATE, version=VERSION, result="Plan not found.")
    
    if plan_obj['status'] != 'pending':
        return render_template_string(HTML_TEMPLATE, version=VERSION, result=f"Plan already {plan_obj['status']}.")
    
    try:
        output = subprocess.check_output(plan_obj['command'], shell=True, stderr=subprocess.STDOUT).decode('utf-8')
        plan_obj['status'] = 'approved'
        plan_obj['output'] = output
        plan_obj['executed_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_action_logs(logs)
        return render_template_string(HTML_TEMPLATE, version=VERSION, result=f"EXECUTED: {plan_obj['command']}\\n\\n{output}".replace('\\n', '\n'))
    except Exception as e:
        plan_obj['status'] = 'failed'
        plan_obj['error'] = str(e)
        save_action_logs(logs)
        return render_template_string(HTML_TEMPLATE, version=VERSION, result=f"EXECUTION FAILED: {str(e)}")

@app.route('/approve_latest')
def approve_latest_route():
    if not check_auth(): return unauthorized()
    logs = get_action_logs()
    pending = [p for p in logs if p['status'] == 'pending']
    if not pending:
        return render_template_string(HTML_TEMPLATE, version=VERSION, result="No pending plans found.")
    
    latest = pending[-1]
    # Redirect to approve with ID
    return approve_with_id(latest['id'])

def approve_with_id(plan_id):
    # This is a helper for approve_latest
    logs = get_action_logs()
    plan_obj = next((p for p in logs if p['id'] == plan_id), None)
    try:
        output = subprocess.check_output(plan_obj['command'], shell=True, stderr=subprocess.STDOUT).decode('utf-8')
        plan_obj['status'] = 'approved'
        plan_obj['output'] = output
        plan_obj['executed_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_action_logs(logs)
        return render_template_string(HTML_TEMPLATE, version=VERSION, result=f"EXECUTED LATEST: {plan_obj['command']}\\n\\n{output}".replace('\\n', '\n'))
    except Exception as e:
        return render_template_string(HTML_TEMPLATE, version=VERSION, result=f"EXECUTION FAILED: {str(e)}")

@app.route('/reject')
def reject():
    if not check_auth(): return unauthorized()
    plan_id = request.args.get('id', '')
    logs = get_action_logs()
    plan_obj = next((p for p in logs if p['id'] == plan_id), None)
    if plan_obj:
        plan_obj['status'] = 'rejected'
        save_action_logs(logs)
        return render_template_string(HTML_TEMPLATE, version=VERSION, result=f"PLAN {plan_id} REJECTED.")
    return render_template_string(HTML_TEMPLATE, version=VERSION, result="Plan not found.")

@app.route('/logs')
def logs_ui():
    if not check_auth(): return unauthorized()
    logs = get_action_logs()
    res = "ACTION LOGS:\\n"
    for p in reversed(logs[-15:]): # Show last 15, newest first
        status_icon = "✅" if p['status'] == 'approved' else "❌" if p['status'] == 'rejected' else "⏳"
        res += f"{status_icon} [{p['id']}] {p['user_request']} -> {p['status']}\\n"
    return render_template_string(HTML_TEMPLATE, version=VERSION, result=res.replace('\\n', '\n'))

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, version=VERSION, result="System initialized. v"+VERSION+" Online.")

@app.route('/status')
def status():
    return render_template_string(HTML_TEMPLATE, version=VERSION, result=get_status_text())

@app.route('/disk')
def disk():
    try:
        res = subprocess.check_output(['df', '-h', '/']).decode('utf-8')
        return render_template_string(HTML_TEMPLATE, version=VERSION, result=res)
    except Exception as e:
        return render_template_string(HTML_TEMPLATE, version=VERSION, result=str(e))

@app.route('/memory_ui')
def memory_ui():
    try:
        with open(MEMORY_FILE, 'r') as f:
            mem_data = json.load(f)
        res = "MEMORY RECORDS:\n"
        for entry in mem_data.get('entries', [])[-10:]: # Show last 10
            res += f"[{entry.get('timestamp')}] {entry.get('memo') or entry.get('query')}\n"
        return render_template_string(HTML_TEMPLATE, version=VERSION, result=res)
    except Exception as e:
        return render_template_string(HTML_TEMPLATE, version=VERSION, result=str(e))

@app.route('/ask')
def ask():
    q = request.args.get('q', '')
    if not q:
        return render_template_string(HTML_TEMPLATE, version=VERSION, result="No input received.")

    q_lower = q.lower().strip()
    
    # Identity
    if q_lower in ["who are you", "nee yaaru", "yaru", "நீ யாரு", "identity"]:
        response = f"I am ASKUTTY v{VERSION} (Aslam + Nova kutty). Safe Operator Mode Active."
    
    # Status
    elif q_lower in ["status", "metrics", "நிலை", "enna status"]:
        response = get_status_text()

    # Memory
    elif q_lower in ["memory", "நினைவு"]:
        return memory_ui()

    # Disk
    elif q_lower in ["disk", "storage", "space"]:
        return disk()

    # War Room
    elif q_lower in ["war room", "por room"]:
        response = "WAR ROOM STATUS: VIGILANT.\nStrategic response: All systems primed for Commander Aslam."
    
    # Search Memory
    elif q_lower.startswith("search memory "):
        term = q_lower[14:].strip()
        try:
            with open(MEMORY_FILE, 'r') as f:
                data = json.load(f)
            matches = []
            for entry in data.get('entries', []):
                if term in entry.get('query', '').lower() or term in (entry.get('memo') or '').lower():
                    matches.append(f"[{entry.get('timestamp')}] {entry.get('memo') or entry.get('query')}")
            
            if matches:
                response = f"SEARCH RESULTS FOR '{term}':\n" + "\n".join(matches)
            else:
                response = f"No records found for '{term}'."
        except Exception as e:
            response = f"Search error: {str(e)}"

    # Forget Last
    elif q_lower == "forget last":
        try:
            with open(MEMORY_FILE, 'r+') as f:
                data = json.load(f)
                if data['entries']:
                    last = data['entries'].pop()
                    f.seek(0)
                    json.dump(data, f, indent=4)
                    f.truncate()
                    response = f"FORGOTTEN: {last.get('memo') or last.get('query')}"
                else:
                    response = "Memory is already empty."
        except Exception as e:
            response = f"Forget failed: {str(e)}"

    # Remember command
    elif q_lower.startswith("remember "):
        memo = q[9:].strip()
        try:
            with open(MEMORY_FILE, 'r+') as f:
                data = json.load(f)
                data['entries'].append({
                    "query": q, 
                    "memo": memo,
                    "timestamp": subprocess.check_output(['date']).decode('utf-8').strip()
                })
                f.seek(0)
                json.dump(data, f, indent=4)
                f.truncate()
            response = f"MEMORIZED: {memo}"
        except Exception as e:
            response = f"Memory write failed: {str(e)}"
    
    else:
        # Default behavior: Log it
        try:
            with open(MEMORY_FILE, 'r+') as f:
                data = json.load(f)
                data['entries'].append({
                    "query": q, 
                    "timestamp": subprocess.check_output(['date']).decode('utf-8').strip()
                })
                f.seek(0)
                json.dump(data, f, indent=4)
                f.truncate()
            response = f"INPUT LOGGED: {q}"
        except Exception as e:
            response = f"Log failed: {str(e)}"
    
    return render_template_string(HTML_TEMPLATE, version=VERSION, result=response)

@app.route('/warroom')
def warroom():
    return render_template_string(HTML_TEMPLATE, version=VERSION, result="WAR ROOM STATUS: VIGILANT.\nAll systems green.")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7797)
