#!/usr/bin/env python3
import time
import math
from flask import Flask, render_template_string
from flask_socketio import SocketIO
from smbus2 import SMBus

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

SENSOR_ADDR = 0x1E
BUS_NUMBER = 1

# Globale Zustandsvariablen
tareX = 0.0
tareY = 0.0
alpha = 0.3
filtered_x = 0.0
filtered_y = 0.0

def init_sensor():
    try:
        bus = SMBus(BUS_NUMBER)
        # Konfiguration für HMC5883L / GY-273
        bus.write_byte_data(SENSOR_ADDR, 0x00, 0x70) # 8-average, 15 Hz, normal measurement
        bus.write_byte_data(SENSOR_ADDR, 0x01, 0x20) # Gain configuration
        bus.write_byte_data(SENSOR_ADDR, 0x02, 0x00) # Continuous-measurement mode
        time.sleep(0.1)
        print("-> GY-273 Sensor erfolgreich initialisiert!")
        return True
    except Exception as e:
        print(f"-> Fehler bei der Sensor-Initialisierung: {e}")
        return False

def read_raw_sensor():
    with SMBus(BUS_NUMBER) as bus:
        data = bus.read_i2c_block_data(SENSOR_ADDR, 0x03, 6)
        x = (data[0] << 8) | data[1]
        z = (data[2] << 8) | data[3]
        y = (data[4] << 8) | data[5]

        # Zweierkomplement korrigieren (Negative Werte)
        x = x - 65536 if x > 32767 else x
        y = y - 65536 if y > 32767 else y
        z = z - 65536 if z > 32767 else z
        return x, y, z

def get_cardinal_direction(deg):
    dirs = ["NORDEN", "NORD-OST", "OSTEN", "SÜD-OST", "SÜDEN", "SÜD-WEST", "WESTEN", "NORD-WEST"]
    index = int((deg + 22.5) / 45) % 8
    return dirs[index]

# HTML / CSS / JS Dashboard Template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <title>Pi 3B+ Magnetometer Studio</title>
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0b0f19; color: #f8fafc; margin: 0; padding: 15px; }
        .header { display: flex; justify-content: space-between; align-items: center; background: #111827; padding: 12px 20px; border-radius: 8px; border: 1px solid #1f2937; margin-bottom: 20px; flex-wrap: wrap; gap: 10px; }
        .header-title { font-size: 1.1rem; font-weight: bold; color: #38bdf8; }
        .header-sub { font-size: 0.75rem; color: #94a3b8; }
        .header-controls { display: flex; align-items: center; gap: 10px; }
        .header input { background: #1f2937; border: 1px solid #374151; color: #f8fafc; padding: 6px 10px; border-radius: 4px; font-size: 0.85rem; }
        .btn { background: #2563eb; color: white; border: none; padding: 6px 14px; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 0.85rem; }
        .btn:hover { background: #1d4ed8; }
        .btn-dark { background: #1f2937; border: 1px solid #374151; color: #94a3b8; }
        .btn-dark:hover { background: #374151; color: white; }
        .main-grid { display: grid; grid-template-columns: 320px 1fr; gap: 20px; }
        @media(max-width: 900px) { .main-grid { grid-template-columns: 1fr; } }
        .card { background: #111827; border: 1px solid #1f2937; border-radius: 10px; padding: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        .card-title { font-size: 0.75rem; text-transform: uppercase; color: #94a3b8; letter-spacing: 0.05em; margin-bottom: 12px; font-weight: 600; }
        .bearing-val { font-size: 2.2rem; font-weight: bold; color: #f8fafc; margin-bottom: 5px; }
        .bearing-dir { display: inline-block; background: #1e293b; color: #38bdf8; font-size: 0.75rem; font-weight: bold; padding: 3px 10px; border-radius: 4px; border: 1px solid #334155; margin-bottom: 15px; }
        .compass-container { width: 170px; height: 170px; border: 2px solid #1f2937; border-radius: 50%; margin: 10px auto; position: relative; background: #0d1322; }
        .compass-rose { position: absolute; width: 100%; height: 100%; }
        .dir { position: absolute; font-size: 0.7rem; color: #64748b; font-weight: bold; }
        .dir-n { top: 4px; left: 50%; transform: translateX(-50%); color: #ef4444; }
        .dir-s { bottom: 4px; left: 50%; transform: translateX(-50%); }
        .dir-e { right: 6px; top: 50%; transform: translateY(-50%); }
        .dir-w { left: 6px; top: 50%; transform: translateY(-50%); }
        .needle { width: 3px; height: 75px; background: linear-gradient(to top, #38bdf8 50%, #ef4444 50%); position: absolute; top: 10px; left: 83.5px; transform-origin: bottom center; transition: transform 0.05s linear; border-radius: 2px; }
        .btn-group { display: flex; gap: 8px; margin: 15px 0; }
        .btn-group .btn { flex: 1; font-size: 0.75rem; padding: 8px; }
        .axis-info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 15px; }
        .axis-box { background: #0d1322; border: 1px solid #1f2937; padding: 8px; border-radius: 6px; text-align: left; }
        .axis-label { font-size: 0.65rem; color: #94a3b8; text-transform: uppercase; }
        .axis-val { font-size: 1.1rem; font-weight: bold; color: #ef4444; }
        .axis-val.y { color: #22c55e; }
        .slider-box { background: #0d1322; border: 1px solid #1f2937; padding: 10px; border-radius: 6px; text-align: left; }
        .slider-header { display: flex; justify-content: space-between; font-size: 0.75rem; color: #94a3b8; margin-bottom: 8px; }
        input[type=range] { width: 100%; accent-color: #38bdf8; cursor: pointer; }
        .slider-footer { display: flex; justify-content: space-between; font-size: 0.65rem; color: #64748b; margin-top: 5px; }
        .charts-column { display: flex; flex-direction: column; gap: 20px; }
        .chart-box { position: relative; height: 180px; width: 100%; }
        .chart-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
        .legend-indicator { display: flex; gap: 15px; font-size: 0.75rem; color: #94a3b8; }
        .dot-x { color: #ef4444; }
        .dot-y { color: #22c55e; }
        .footer-bar { margin-top: 20px; background: #111827; border: 1px solid #1f2937; padding: 10px 15px; border-radius: 8px; display: flex; justify-content: space-between; font-size: 0.75rem; color: #94a3b8; }
        .status-live { color: #22c55e; font-weight: bold; }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <div class="header-title">Pi 3B+ Magnetometer Studio</div>
            <div class="header-sub">GY-273 Sensor • HMC5883L</div>
        </div>
        <div class="header-controls">
            <input type="text" id="serverIp" value="192.168.178.162:5000" style="width: 140px; text-align: center;">
            <button class="btn" onclick="location.reload()">Verbinden</button>
            <button class="btn btn-dark">Pi Python Code</button>
        </div>
    </div>

    <div class="main-grid">
        <div class="card">
            <div class="card-title">&gt; DIGITAL_COMPASS_BEARING</div>
            <div id="bearingVal" class="bearing-val">0.0°</div>
            <div><span id="bearingDir" class="bearing-dir">NORDEN (N)</span></div>

            <div class="compass-container">
                <div class="compass-rose">
                    <span class="dir dir-n">N</span>
                    <span class="dir dir-e">O</span>
                    <span class="dir dir-s">S</span>
                    <span class="dir dir-w">W</span>
                </div>
                <div id="needle" class="needle"></div>
            </div>

            <div class="btn-group">
                <button class="btn btn-dark" onclick="resetTare()">Tare (0°)</button>
                <button class="btn btn-dark" onclick="alert('Kalibrierung aktiv')">Kalibrieren</button>
            </div>

            <div class="axis-info-grid">
                <div class="axis-box">
                    <div class="axis-label">X-Achse (Ost/West)</div>
                    <div id="xVal" class="axis-val">0</div>
                </div>
                <div class="axis-box">
                    <div class="axis-label">Y-Achse (Nord/Süd)</div>
                    <div id="yVal" class="axis-val y">0</div>
                </div>
            </div>

            <div class="slider-box">
                <div class="slider-header">
                    <span>Signal-Filter &amp; Glättung</span>
                    <span id="alphaLabel">EMA (&alpha; = 0.3)</span>
                </div>
                <input type="range" id="alphaRange" min="0.05" max="1.0" step="0.05" value="0.3" oninput="updateAlpha(this.value)">
                <div class="slider-footer">
                    <span>Starke Glättung (Träge)</span>
                    <span>Direkt / Ungefiltert</span>
                </div>
            </div>
        </div>

        <div class="charts-column">
            <div class="card">
                <div class="chart-header">
                    <div class="card-title" style="margin:0;">&gt; ECHTZEIT MAGNETFELDVERLAUF (XY-EBENE)</div>
                    <div class="legend-indicator">
                        <span><span class="dot-x">■</span> X-Achse</span>
                        <span><span class="dot-y">■</span> Y-Achse</span>
                        <span style="color: #64748b;">10 Hz Sample Rate</span>
                    </div>
                </div>
                <div class="chart-box">
                    <canvas id="timeChart"></canvas>
                </div>
            </div>

            <div class="card">
                <div class="chart-header">
                    <div class="card-title" style="margin:0;">&gt; 2D MAGNETFELD-VEKTOR &amp; AUSRICHTUNG (XY)</div>
                    <div class="legend-indicator">
                        <span><span class="dot-x">■</span> X-Achse</span>
                        <span><span class="dot-y">■</span> Y-Achse</span>
                    </div>
                </div>
                <div class="chart-box">
                    <canvas id="vectorChart"></canvas>
                </div>
            </div>
        </div>
    </div>

    <div class="footer-bar">
        <div>Sensor Status: <span class="status-live">Aktiv / Live</span></div>
        <div>Hardware: Raspberry Pi 3 B+</div>
    </div>

    <script>
        const socket = io();
        let currentAlpha = 0.3;

        function updateAlpha(val) {
            currentAlpha = parseFloat(val);
            document.getElementById('alphaLabel').innerText = `EMA (α = ${currentAlpha.toFixed(2)})`;
        }

        function resetTare() {
            socket.emit('reset_tare');
        }

        const timeCtx = document.getElementById('timeChart').getContext('2d');
        const timeChart = new Chart(timeCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    { label: 'X', borderColor: '#ef4444', data: [], borderWidth: 1.5, tension: 0.1, pointRadius: 0 },
                    { label: 'Y', borderColor: '#22c55e', data: [], borderWidth: 1.5, tension: 0.1, pointRadius: 0 }
                ]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { display: false },
                    y: { grid: { color: '#1f2937' }, ticks: { color: '#94a3b8', font: { size: 10 } } }
                },
                plugins: { legend: { display: false } }
            }
        });

        const vectorCtx = document.getElementById('vectorChart').getContext('2d');
        const vectorChart = new Chart(vectorCtx, {
            type: 'scatter',
            data: {
                datasets: [{
                    label: 'Vektor',
                    borderColor: '#38bdf8',
                    backgroundColor: ['#ef4444', '#22c55e'],
                    data: [{x: 0, y: 0}, {x: 0, y: 0}],
                    showLine: true,
                    borderWidth: 2,
                    pointRadius: 5
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { grid: { color: '#1f2937' }, ticks: { color: '#94a3b8', font: { size: 10 } }, min: -500, max: 500 },
                    y: { grid: { color: '#1f2937' }, ticks: { color: '#94a3b8', font: { size: 10 } }, min: -500, max: 500 }
                },
                plugins: { legend: { display: false } }
            }
        });

        socket.on('sensor_data', (data) => {
            document.getElementById('bearingVal').innerText = data.heading.toFixed(1) + '°';
            document.getElementById('bearingDir').innerText = data.cardinal;
            document.getElementById('needle').style.transform = `rotate(${data.heading}deg)`;
            
            document.getElementById('xVal').innerText = data.x;
            document.getElementById('yVal').innerText = data.y;

            const timeLabel = new Date().toLocaleTimeString();
            if (timeChart.data.labels.length > 40) {
                timeChart.data.labels.shift();
                timeChart.data.datasets[0].data.shift();
                timeChart.data.datasets[1].data.shift();
            }
            timeChart.data.labels.push(timeLabel);
            timeChart.data.datasets[0].data.push(data.x);
            timeChart.data.datasets[1].data.push(data.y);
            timeChart.update('none');

            vectorChart.data.datasets[0].data = [{x: 0, y: 0}, {x: data.x, y: data.y}];
            vectorChart.update('none');
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@socketio.on('reset_tare')
def handle_tare():
    global tareX, tareY, filtered_x, filtered_y
    tareX = filtered_x
    tareY = filtered_y

def background_sensor_loop():
    global filtered_x, filtered_y, tareX, tareY
    while True:
        try:
            raw_x, raw_y, raw_z = read_raw_sensor()
            
            filtered_x = (alpha * raw_x) + ((1 - alpha) * filtered_x)
            filtered_y = (alpha * raw_y) + ((1 - alpha) * filtered_y)
            
            px = int(filtered_x - tareX)
            py = int(filtered_y - tareY)
            
            heading = math.atan2(py, px) * (180.0 / math.pi)
            if heading < 0:
                heading += 360.0
                
            cardinal = get_cardinal_direction(heading)
            
            socketio.emit('sensor_data', {
                'x': px, 'y': py, 'z': raw_z,
                'heading': heading, 'cardinal': cardinal
            })
        except Exception as e:
            # Fängt I2C-Fehler ab, damit die Schleife nicht abstürzt
            print(f"Hintergrund-Lesefehler: {e}")
        
        socketio.sleep(0.1)

@socketio.on('connect')
def handle_connect():
    print("Studio Client verbunden!")

if __name__ == '__main__':
    print("Starte Magnetometer Studio Webserver...")
    init_sensor()
    socketio.start_background_task(background_sensor_loop)
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)