FROM python:3.11-slim

WORKDIR /app

# Minimal libs OpenCV often needs
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libsm6 libxext6 libxrender1 && \
    rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Install deps in one layer (pin if you can)
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    python-multipart \
    mediapipe \
    opencv-python-headless \
    h5py

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
