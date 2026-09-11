# Dockerfile para desplegar el backend en Railway / Fly.io
# Fija Python 3.12, instala torch CPU y arranca uvicorn.

FROM python:3.12-slim

WORKDIR /app

# Variables para evitar descargar CUDA
ENV PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

# Copiar dependencias primero (mejor cacheo de capas)
COPY requirements.txt ./

# Instalar torch/torchvision CPU desde el índice oficial, luego el resto
RUN pip install --upgrade pip \
    && pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision \
    && pip install -r requirements.txt

# Descargar el modelo de pose de YOLO dentro de la imagen, para que el
# servidor arranque rápido y sin depender de internet en runtime.
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n-pose.pt')"

# Copiar el código
COPY . .

# Render/Railway/Fly inyectan la variable PORT (por defecto 8000 si no existe)
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]