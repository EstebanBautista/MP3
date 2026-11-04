# Builds the three engines and starts the web interface on port 8000.
#   docker compose up --build      then open http://localhost:8000
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends g++ cmake ninja-build \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Example worlds may arrive with Windows line endings from a Windows checkout.
RUN sed -i 's/\r$//' ecosystem_examples/* \
 && cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DECO_STATIC=OFF \
 && cmake --build build

EXPOSE 8000
CMD ["python", "web/server.py", "--host", "0.0.0.0", "--port", "8000"]
