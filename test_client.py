"""Cliente de prueba: envía una imagen local como si fuera un frame del dron.

Uso:
    python test_client.py ruta/imagen.jpg [lat] [lon]
"""

import base64
import sys

import requests


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python test_client.py ruta/imagen.jpg [lat] [lon]")
        sys.exit(1)

    image_path = sys.argv[1]
    lat = float(sys.argv[2]) if len(sys.argv) > 2 else 4.6097
    lon = float(sys.argv[3]) if len(sys.argv) > 3 else -74.0817

    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "image": b64,
        "lat": lat,
        "lon": lon,
        "altitude": 15.0,
        "device_id": "DRONE-01",
        "drone_model": "test",
    }

    # health check
    r = requests.get("http://127.0.0.1:8000/api/health", timeout=10)
    print("Health:", r.status_code, r.json())

    r = requests.post("http://127.0.0.1:8000/api/frame", json=payload, timeout=60)
    print("Frame:", r.status_code)
    print(r.json())


if __name__ == "__main__":
    main()