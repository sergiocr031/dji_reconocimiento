"""Simulador de vuelo autónomo y detección de emergencias para dron DJI.

Permite probar el sistema completo (Mapa, Telemetría, YOLOv8-pose, Sirena y Logs)
sin necesidad de encender ni conectar el dron físico.

Uso:
    python simulate_flight.py [ruta_imagen_opcional]
"""

import base64
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: Requiere la librería 'requests'. Instálala o usa el entorno venv.")
    sys.exit(1)

SERVER_URL = "http://127.0.0.1:8000"
DEFAULT_IMAGE = Path(r"C:\Users\Usuario\Downloads\prueba.jpg")


def check_server() -> bool:
    try:
        r = requests.get(f"{SERVER_URL}/api/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 60)
    print(" 🚁 SIMULADOR DE PATRULLAJE Y DETECCIÓN - DRON DJI ")
    print("=" * 60)

    # 1. Comprobar servidor
    if not check_server():
        print("❌ ERROR: El servidor backend no está respondiendo en:")
        print(f"   {SERVER_URL}")
        print("\nPara iniciarlo, abre otra consola y ejecuta:")
        print(r"   cd C:\Users\Usuario\AndroidStudioProjects\DJI_Reconocimiento\backend")
        print(r"   .\venv\Scripts\python.exe -m uvicorn main:app --reload")
        sys.exit(1)

    print("✅ Servidor backend en línea y respondiendo.")
    print("💡 Asegúrate de tener abierta la web en tu navegador:")
    print("   👉 http://localhost:8000\n")

    # 2. Obtener imagen de prueba
    img_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IMAGE
    if not img_path.exists():
        print(f"⚠️ Imagen no encontrada en: {img_path}")
        print("Por favor especifica una imagen válida: python simulate_flight.py ruta/a/foto.jpg")
        sys.exit(1)

    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    # Ruta de vuelo simulada (Coordenadas de patrullaje)
    base_lat = 4.60970
    base_lon = -74.08170

    flight_path = [
        {"lat": base_lat + 0.0000, "lon": base_lon + 0.0000, "alt": 10.5, "spd": 8.0,  "bat": 99, "action": "Despegue e inicio de patrullaje"},
        {"lat": base_lat + 0.0005, "lon": base_lon + 0.0004, "alt": 18.2, "spd": 15.4, "bat": 98, "action": "Navegación por zona alfa"},
        {"lat": base_lat + 0.0010, "lon": base_lon + 0.0008, "alt": 24.5, "spd": 16.1, "bat": 97, "action": "Escaneo térmico y óptico"},
        {"lat": base_lat + 0.0015, "lon": base_lon + 0.0012, "alt": 22.0, "spd": 5.2,  "bat": 96, "action": "🚨 OBJETIVO VISUAL DETECTADO (Enviando Frame para IA)"},
        {"lat": base_lat + 0.0018, "lon": base_lon + 0.0015, "alt": 20.0, "spd": 6.8,  "bat": 95, "action": "Manteniendo vigilancia sobre el objetivo"},
        {"lat": base_lat + 0.0022, "lon": base_lon + 0.0018, "alt": 22.5, "spd": 12.0, "bat": 94, "action": "Transmisión de telemetría continua"},
    ]

    print(f"Iniciando simulación de vuelo con {len(flight_path)} waypoints...\n")

    for i, step in enumerate(flight_path, 1):
        lat = step["lat"]
        lon = step["lon"]
        alt = step["alt"]
        spd = step["spd"]
        bat = step["bat"]
        action = step["action"]

        print(f"[{i}/{len(flight_path)}] Waypoint: Lat={lat:.5f}, Lon={lon:.5f} | Alt={alt}m | Bat={bat}%")
        print(f"     ➜ Estado: {action}")

        # En el paso 4, enviamos el frame con la persona para que YOLO procese y active la alerta
        if i == 4:
            payload = {
                "image": img_b64,
                "lat": lat,
                "lon": lon,
                "altitude": alt,
                "speed": spd,
                "battery": bat,
                "device_id": "DJI-MAVIC3T-SIM",
                "drone_model": "DJI Mavic 3 Enterprise",
            }
            res = requests.post(f"{SERVER_URL}/api/frame", json=payload, timeout=30)
            if res.status_code == 200:
                data = res.json()
                print(f"     🎯 Resultado IA: {data.get('message')}")
                if data.get("alert"):
                    print("     🚨 ¡ALERTA DISPARADA! (Verifica la sirena y el mapa en el navegador)")
            else:
                print(f"     ⚠️ Error al procesar frame: HTTP {res.status_code}")
        else:
            # Enviar telemetría ligera
            payload = {
                "lat": lat,
                "lon": lon,
                "altitude": alt,
                "speed": spd,
                "battery": bat,
                "device_id": "DJI-MAVIC3T-SIM",
                "drone_model": "DJI Mavic 3 Enterprise",
            }
            try:
                requests.post(f"{SERVER_URL}/api/telemetry", json=payload, timeout=5)
            except Exception as e:
                print(f"     ⚠️ Telemetría: {e}")

        time.sleep(2.0)

    print("\n" + "=" * 60)
    print("🎉 SIMULACIÓN COMPLETADA CON ÉXITO")
    print("Revisa tu navegador en http://localhost:8000 para verificar:")
    print(" - El marcador del dron en movimiento")
    print(" - La alerta con sirena, coordenadas y captura anotada con YOLOv8-pose")
    print(" - La terminal de eventos en el panel derecho")
    print("=" * 60)


if __name__ == "__main__":
    main()
