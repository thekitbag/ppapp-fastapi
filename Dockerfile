# Dockerfile
FROM python:3.11-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# System deps for psycopg/uvicorn/etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
  && rm -rf /var/lib/apt/lists/*

# venv (optional)
RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

# Make pip capable of pulling manylinux wheels
RUN pip install --upgrade pip setuptools wheel

# Install deps early for layer cache
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy app
COPY . .

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]