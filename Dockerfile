FROM python:3.13-slim AS base

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python package
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir .

# Copy dashboard build
COPY dashboard/dist/ dashboard/dist/

# Copy config
COPY sources.yaml .env* ./

# Create data directory
RUN mkdir -p data

EXPOSE 8080

CMD ["amon", "serve", "--host", "0.0.0.0", "--port", "8080"]
