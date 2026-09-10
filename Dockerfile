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

# Copiar el código
COPY . .

# Render/Railway/Fly inyectan la variable PORT
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]