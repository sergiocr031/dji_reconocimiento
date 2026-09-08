# Backend DJI Reconocimiento

Procesa frames del dron en tiempo real y emite alertas cuando detecta una
persona en posición anormal (acostada).

## Requisitos

- **Python 3.10 - 3.12** (obligatorio; `ultralytics`/torch NO soporta 3.13/3.14).
- Conexión a internet la primera vez para descargar el modelo `yolov8n-pose.pt`.

## Instalación

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

## Ejecutar

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

El servidor escucha en el puerto 8000. La app Android debe apuntar a la IP
de esta máquina (configurable en `NetworkApiClient` / preferencias `server_address`).

## Endpoints

| Método | Ruta               | Descripción                               |
|--------|--------------------|-------------------------------------------|
| GET    | `/api/health`      | Estado del servidor                       |
| POST   | `/api/frame`       | Recibe frame + ubicación y ejecuta YOLO   |
| GET    | `/api/alerts`      | Últimas alertas (REST)                    |
| GET    | `/api/alerts/recent` | Alertas recientes (con `limit`)         |
| WS     | `/ws/alerts`       | Stream de alertas en tiempo real          |

### Ejemplo de `POST /api/frame`

```json
{
  "image": "<base64 JPEG>",
  "lat": 4.6097,
  "lon": -74.0817,
  "altitude": 15.2,
  "device_id": "DRONE-01",
  "drone_model": "Mavic 3T",
  "timestamp": "2026-09-07T11:00:00"
}
```

### Respuesta

```json
{
  "success": true,
  "detections": [
    {"bbox": [x1, y1, x2, y2], "posture": "lying_down", "score": 0.92, "keypoints": [...]}
  ],
  "alert": true,
  "message": "Alerta: 1 persona(s) en posición anormal"
}
```

### Test rápido sin el dron

```bash
python test_client.py ruta/imagen.jpg
```

Envía una imagen local simulando un frame del dron con una ubicación de prueba.