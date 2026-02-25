# backend/server.py
import asyncio
import csv
import io
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import serial
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

# -------------------------
# CONFIG
# -------------------------
SERIAL_PORT: Optional[str] = "COM8"   # FIXED COM8 as requested
BAUDRATE = 115200
NUM_CHANNELS = 4

SAMPLE_PERIOD_SEC = 1.0
AVG_WINDOW = 60  # 1-min average

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "od_1min_avg_log.csv")
# -------------------------

app = FastAPI(title="TuRAC OD Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

latest_lock = asyncio.Lock()
pid_lock = asyncio.Lock()
clients_lock = asyncio.Lock()
serial_lock = asyncio.Lock()
log_lock = asyncio.Lock()

latest: Dict[str, Any] = {
    "ts": None,
    "od": [None] * NUM_CHANNELS,
    "status": "starting",
    "avg_1min": [None] * NUM_CHANNELS,
}

pid_params: Dict[str, Any] = {
    "setpoints": [0.65, 0.65, 0.65, 0.65],
    "kp": [10.0, 10.0, 10.0, 10.0],
    "ki": [1.2, 1.2, 1.2, 1.2],
    "kd": [0.0, 0.0, 0.0, 0.0],
}

clients: List[WebSocket] = []
ser: Optional[serial.Serial] = None

buffers: List[List[float]] = [[] for _ in range(NUM_CHANNELS)]

if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["timestamp_iso", "epoch", "avg1", "avg2", "avg3", "avg4"])


def avg(xs: List[float]) -> Optional[float]:
    return (sum(xs) / len(xs)) if xs else None


async def append_avg(ts: float, avgs: List[Optional[float]]):
    iso = datetime.fromtimestamp(ts).isoformat(timespec="seconds")
    row = [iso, f"{ts:.3f}"] + [(f"{x:.3f}" if x is not None else "") for x in avgs]
    async with log_lock:
        with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(row)


async def broadcast(message: dict):
    async with clients_lock:
        current = list(clients)
    payload = json.dumps(message)
    dead = []
    for ws in current:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    if dead:
        async with clients_lock:
            for ws in dead:
                if ws in clients:
                    clients.remove(ws)


async def open_serial() -> bool:
    global ser
    async with serial_lock:
        if ser is not None and ser.is_open:
            return True
        try:
            ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=0.2, write_timeout=0.2)
            async with latest_lock:
                latest["status"] = f"serial_connected:{SERIAL_PORT}"
            return True
        except Exception as e:
            async with latest_lock:
                latest["status"] = f"serial_open_failed:{SERIAL_PORT}:{e}"
            ser = None
            return False


async def close_serial():
    global ser
    async with serial_lock:
        try:
            if ser and ser.is_open:
                ser.close()
        except Exception:
            pass
        ser = None


def parse_od_line(line: str) -> Optional[List[float]]:
    # OD,v1,v2,v3,v4
    line = line.strip()
    if not line:
        return None
    parts = line.split(",")
    if len(parts) != 1 + NUM_CHANNELS:
        return None
    if parts[0].strip().upper() != "OD":
        return None
    try:
        return [float(parts[i + 1]) for i in range(NUM_CHANNELS)]
    except ValueError:
        return None


async def serial_loop():
    """
    Reads OD at 1 Hz. Logs ONLY 1-minute averages.
    """
    while True:
        ok = await open_serial()
        if not ok:
            await asyncio.sleep(1.0)
            continue

        try:
            async with serial_lock:
                raw = ser.readline().decode(errors="ignore") if ser else ""
            od = parse_od_line(raw)

            if od is not None:
                ts = time.time()

                # buffer update for averaging
                for ch in range(NUM_CHANNELS):
                    buffers[ch].append(od[ch])
                    if len(buffers[ch]) > AVG_WINDOW:
                        buffers[ch].pop(0)

                avgs = [avg(buffers[ch]) for ch in range(NUM_CHANNELS)]

                async with latest_lock:
                    latest["ts"] = ts
                    latest["od"] = od
                    latest["avg_1min"] = avgs
                    latest["status"] = f"streaming:{SERIAL_PORT}"

                # push live OD to UI
                await broadcast({"type": "od", "ts": ts, "od": od})

                # log once per minute when buffers full and at second 0
                if all(len(buffers[ch]) >= AVG_WINDOW for ch in range(NUM_CHANNELS)):
                    if int(ts) % 60 == 0:
                        await append_avg(ts, avgs)

        except Exception as e:
            async with latest_lock:
                latest["status"] = f"serial_failed:{e}"
            await close_serial()
            await asyncio.sleep(1.0)

        await asyncio.sleep(SAMPLE_PERIOD_SEC)


@app.on_event("startup")
async def startup():
    asyncio.create_task(serial_loop())


@app.get("/api/latest")
async def api_latest():
    async with latest_lock:
        return JSONResponse(latest)


@app.get("/api/pid")
async def api_pid():
    async with pid_lock:
        return JSONResponse(pid_params)


@app.post("/api/pid")
async def api_set_pid(body: Dict[str, Any]):
    """
    Updates PID parameters and forwards to Arduino in PID,... format.
    """
    async with pid_lock:
        for key in ["setpoints", "kp", "ki", "kd"]:
            if key in body:
                arr = body[key]
                if not isinstance(arr, list) or len(arr) != NUM_CHANNELS:
                    return JSONResponse(
                        {"status": "error", "msg": f"{key} must be list length {NUM_CHANNELS}"},
                        status_code=400,
                    )
                pid_params[key] = [float(x) for x in arr]
        current = dict(pid_params)

    # Forward to Arduino
    try:
        ok = await open_serial()
        if ok:
            cmd = (
                "PID,"
                + "SP," + ",".join(str(x) for x in current["setpoints"]) + ","
                + "KP," + ",".join(str(x) for x in current["kp"]) + ","
                + "KI," + ",".join(str(x) for x in current["ki"]) + ","
                + "KD," + ",".join(str(x) for x in current["kd"])
                + "\n"
            )
            async with serial_lock:
                if ser:
                    ser.write(cmd.encode())
    except Exception:
        pass

    return JSONResponse({"status": "ok", "pid": current})


def parse_ddmmyyyy(s: str) -> datetime:
    return datetime.strptime(s, "%d.%m.%Y")


def parse_hhmm(s: str) -> datetime.time:
    return datetime.strptime(s, "%H:%M").time()


@app.get("/api/log.csv")
async def api_log_csv(
    date_from: str,
    date_to: str,
    time_from: str = "00:00",
    time_to: str = "23:59",
):
    d_from = parse_ddmmyyyy(date_from).date()
    d_to = parse_ddmmyyyy(date_to).date()
    t_from = parse_hhmm(time_from)
    t_to = parse_hhmm(time_to)

    start_dt = datetime.combine(d_from, t_from)
    end_dt = datetime.combine(d_to, t_to)
    start_epoch = start_dt.timestamp()
    end_epoch = end_dt.timestamp()

    async with log_lock:
        if not os.path.exists(LOG_FILE):
            return JSONResponse({"status": "error", "msg": "log not found"}, status_code=404)
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()

    out = io.StringIO()
    if lines:
        out.write(lines[0] + "\n")
    for line in lines[1:]:
        parts = line.split(";")
        if len(parts) < 2:
            continue
        try:
            epoch = float(parts[1])
        except ValueError:
            continue
        if start_epoch <= epoch <= end_epoch:
            out.write(line + "\n")
    out.seek(0)

    filename = f"turac_1min_avg_{date_from.replace('.','-')}_to_{date_to.replace('.','-')}.csv"
    return StreamingResponse(
        out,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    async with clients_lock:
        clients.append(websocket)

    async with pid_lock:
        await websocket.send_text(json.dumps({"type": "pid", "pid": pid_params}))
    async with latest_lock:
        await websocket.send_text(json.dumps({"type": "status", "status": latest["status"]}))

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        async with clients_lock:
            if websocket in clients:
                clients.remove(websocket)
