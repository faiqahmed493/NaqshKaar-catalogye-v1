# Naqshkaar Catalogue Studio — API and CPU worker image
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# libcairo2: SVG rasterising (CairoSVG). nodejs/npm: Khronos glTF-Validator. curl: health checks.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libcairo2 nodejs npm curl postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/gltf-validator
COPY tools/package.json tools/validate.mjs ./
RUN npm install --omit=dev --no-audit --no-fund

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
# Strip Windows line endings in case the repo was checked out with CRLF.
RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod +x docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
