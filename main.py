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

from __future__ import annotations

import base64
import logging
import threading
from datetime import datetime, timezone
from typing import Any

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from posture_detector import PostureDetector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backend")

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

# Modelo de detección (se carga una vez al iniciar).
DETECTOR = PostureDetector(model_path="yolov8n-pose.pt", confidence=0.4)

# Estado compartido
_latest_alerts: list[dict[str, Any]] = []
_lock = threading.Lock()
_alerts_condition = threading.Condition()
_alert_counter = 0  # para que los clientes WS sepan si hay alertas nuevas


class FrameRequest(BaseModel):
    """Payload enviado por la app Android.

    ``extra = "ignore"`` permite que la app mande campos adicionales
    (``type``, ``risk``, etc.) sin que FastAPI rechace el request.
    """

    model_config = {"extra": "ignore"}

    image: str  # base64 JPEG
    lat: float
    lon: float
    altitude: float = 0.0
    device_id: str = "DRONE-01"
    drone_model: str = ""
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
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return frame
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error decodificando imagen: %s", exc)
        return None


def _emit_alert(alert: dict[str, Any]) -> None:
    """Registra la alerta en la cola compartida."""
    global _alert_counter
    with _alerts_condition:
        _latest_alerts.append(alert)
        if len(_latest_alerts) > 200:
            _latest_alerts.pop(0)
        _alert_counter += 1
        _alerts_condition.notify_all()


# --- Endpoints ---


@app.get("/")
def read_root() -> dict[str, Any]:
    """Endpoint en la raíz para evitar errores 404 al abrir en el navegador."""
    return {
        "status": "online",
        "service": "DJI Reconocimiento Backend",
        "docs": "/docs",
        "health": "/api/health",
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


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

    detections = DETECTOR.detect(frame)

    abnormal = [d for d in detections if DETECTOR.is_abnormal(d["posture"])]

    alert_triggered = len(abnormal) > 0

    if alert_triggered:
        ts = req.timestamp or datetime.now(timezone.utc).isoformat()
        for d in abnormal:
            alert = {
                "type": "alert",
                "posture": d["posture"],
                "score": d["score"],
                "location": {"lat": req.lat, "lon": req.lon, "altitude": req.altitude},
                "device_id": req.device_id,
                "drone_model": req.drone_model,
                "timestamp": ts,
            }
            _emit_alert(alert)

    message = (
        f"Alerta: {len(abnormal)} persona(s) en posición anormal"
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

    last_seen = _alert_counter
    try:
        while True:
            with _alerts_condition:
                while last_seen >= _alert_counter:
                    _alerts_condition.wait(1.0)  # despierta al haber alerta nueva o cada 1s
                new_alerts = list(_latest_alerts)
                local_counter = _alert_counter
            # enviar sólo las nuevas desde last_seen
            to_send = new_alerts[-(local_counter - last_seen):]
            last_seen = local_counter
            for alert in to_send:
                await ws.send_json(alert)
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        pass