"""Backend de procesamiento en tiempo real para el dron DJI.

Recibe frames (imagen + ubicación GPS) desde la app Android, ejecuta
detección de postura con YOLO y emite alertas cuando detecta una persona
acostada (posición anormal), entregando la ubicación exacta.

Endpoints:
  GET  /                        -> mensaje de estado / información del servicio
  GET  /api/health              -> estado del servidor (healthcheck)
  POST /api/frame               -> recibe un frame y ubicación
  POST /api/detect              -> alias de /api/frame (usado por la app)
  GET  /api/alerts              -> últimas alertas (REST)
  GET  /api/alerts/recent       -> alertas recientes
  WS   /ws/alerts               -> stream de alertas en vivo
"""

import asyncio
import base64
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from posture_detector import PostureDetector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backend")

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"

app = FastAPI(
    title="DJI Reconocimiento Backend",
    description="API para procesar transmisión de video del dron DJI y detectar posturas anormales.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Modelo de detección (se carga una vez al iniciar).
DETECTOR = PostureDetector(model_path="yolov8n-pose.pt", confidence=0.4)

# Estado compartido
_latest_alerts: list[dict[str, Any]] = []
_lock = threading.Lock()
_active_websockets: list[WebSocket] = []
_event_loop: asyncio.AbstractEventLoop | None = None


@app.on_event("startup")
async def startup_event() -> None:
    global _event_loop
    _event_loop = asyncio.get_running_loop()


class FrameRequest(BaseModel):
    """Payload enviado por la app Android."""
    model_config = {"extra": "ignore"}

    image: str  # base64 JPEG
    lat: float
    lon: float
    altitude: float = 0.0
    speed: float = 0.0
    battery: int = 100
    device_id: str = "DRONE-01"
    drone_model: str = ""
    timestamp: str | None = None


class TelemetryRequest(BaseModel):
    """Telemetría ligera enviada periódicamente por el dron."""
    model_config = {"extra": "ignore"}

    lat: float
    lon: float
    altitude: float = 24.5
    speed: float = 14.2
    battery: int = 89
    device_id: str = "DRONE-01"
    drone_model: str = "DJI Mavic 3 Enterprise"
    timestamp: str | None = None


class FrameResponse(BaseModel):
    success: bool
    detections: list[dict[str, Any]]
    alert: bool
    message: str


# --- Utilidades ---


def _decode_image(image_b64: str) -> np.ndarray | None:
    try:
        raw = base64.b64decode(image_b64)
        arr = np.frombuffer(raw, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error decodificando imagen: %s", exc)
        return None


def _encode_image(frame_bgr: np.ndarray) -> str:
    try:
        success, buffer = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if success:
            return base64.b64encode(buffer).decode("utf-8")
    except Exception as exc:
        logger.warning("Error codificando imagen: %s", exc)
    return ""


async def _broadcast(message: dict[str, Any]) -> None:
    for ws in list(_active_websockets):
        try:
            await ws.send_json(message)
        except Exception:
            if ws in _active_websockets:
                _active_websockets.remove(ws)


def _emit_alert(alert: dict[str, Any]) -> None:
    """Registra la alerta en la cola compartida y la transmite vía WebSocket."""
    with _lock:
        _latest_alerts.append(alert)
        if len(_latest_alerts) > 200:
            _latest_alerts.pop(0)

    if _event_loop and _event_loop.is_running():
        asyncio.run_coroutine_threadsafe(_broadcast(alert), _event_loop)


def _emit_telemetry(telemetry: dict[str, Any]) -> None:
    if _event_loop and _event_loop.is_running():
        asyncio.run_coroutine_threadsafe(_broadcast(telemetry), _event_loop)


# --- Endpoints ---


@app.get("/")
def read_root():
    """Sirve el dashboard interactivo de monitoreo en tiempo real."""
    if INDEX_HTML.exists():
        return FileResponse(INDEX_HTML)
    return {
        "status": "online",
        "service": "DJI Reconocimiento Backend",
        "docs": "/docs",
        "health": "/api/health",
    }


@app.get("/dashboard")
def get_dashboard():
    if INDEX_HTML.exists():
        return FileResponse(INDEX_HTML)
    return {"error": "Dashboard no disponible"}


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@app.post("/api/telemetry")
def receive_telemetry(req: TelemetryRequest) -> dict[str, Any]:
    """Recibe paquetes de telemetría de vuelo pura desde el dron."""
    ts = req.timestamp or datetime.now(timezone.utc).isoformat()
    _emit_telemetry({
        "type": "telemetry",
        "device_id": req.device_id,
        "drone_model": req.drone_model,
        "lat": req.lat,
        "lon": req.lon,
        "altitude": req.altitude,
        "speed": req.speed,
        "battery": req.battery,
        "timestamp": ts,
    })
    return {"success": True, "message": "Telemetría recibida"}


@app.post("/api/frame", response_model=FrameResponse)
@app.post("/api/detect", response_model=FrameResponse, include_in_schema=False)
def process_frame(req: FrameRequest) -> FrameResponse:
    frame = _decode_image(req.image)
    if frame is None:
        return FrameResponse(
            success=False,
            detections=[],
            alert=False,
            message="Imagen no válida",
        )

    # 1. Inferencia de posturas corporales con YOLO
    detections = DETECTOR.detect(frame)
    abnormal = [d for d in detections if DETECTOR.is_abnormal(d["posture"])]
    alert_triggered = len(abnormal) > 0

    # 2. Generar imagen con cajas y puntos anatómicos dibujados
    annotated_frame = DETECTOR.annotate(frame, detections)
    annotated_b64 = _encode_image(annotated_frame)

    ts = req.timestamp or datetime.now(timezone.utc).isoformat()

    # 3. Transmitir telemetría para ver el dron en vivo en el mapa
    _emit_telemetry({
        "type": "telemetry",
        "device_id": req.device_id,
        "drone_model": req.drone_model,
        "lat": req.lat,
        "lon": req.lon,
        "altitude": req.altitude,
        "speed": req.speed,
        "battery": req.battery,
        "timestamp": ts,
        "detections_count": len(detections),
    })

    # 4. Si hay postura anormal (persona en peligro/acostada), emitir alerta
    if alert_triggered:
        for d in abnormal:
            alert = {
                "type": "alert",
                "posture": d["posture"],
                "score": d["score"],
                "location": {"lat": req.lat, "lon": req.lon, "altitude": req.altitude},
                "device_id": req.device_id,
                "drone_model": req.drone_model,
                "timestamp": ts,
                "image": annotated_b64,
            }
            _emit_alert(alert)

    message = (
        f"🚨 ALERTA: {len(abnormal)} persona(s) en peligro"
        if alert_triggered
        else f"{len(detections)} persona(s) detectada(s)"
    )

    return FrameResponse(
        success=True,
        detections=detections,
        alert=alert_triggered,
        message=message,
    )


@app.get("/api/alerts")
def get_alerts() -> dict[str, Any]:
    with _lock:
        alerts = list(_latest_alerts)
    return {"count": len(alerts), "alerts": alerts}


@app.get("/api/alerts/recent")
def get_recent_alerts(limit: int = 20) -> dict[str, Any]:
    with _lock:
        alerts = list(_latest_alerts[-limit:])
    return {"count": len(alerts), "alerts": alerts}


@app.websocket("/ws/alerts")
async def ws_alerts(ws: WebSocket) -> None:
    await ws.accept()
    _active_websockets.append(ws)
    try:
        while True:
            # Mantener la conexión activa esperando mensajes o pings
            await ws.receive_text()
    except (WebSocketDisconnect, Exception):
        if ws in _active_websockets:
            _active_websockets.remove(ws)