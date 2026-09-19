FROM python:3.11-slim

WORKDIR /app

# System deps some scientific wheels expect
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-pymol \
    pymol \
    python3-pil \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

CMD ["python", "-m", "src.bot"]
