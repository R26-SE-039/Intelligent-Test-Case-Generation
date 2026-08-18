FROM python:3.10-slim

WORKDIR /app

# Install system dependencies needed for Playwright and other libraries
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    libffi-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (chromium)
RUN playwright install chromium
RUN playwright install-deps chromium

COPY ./app ./app

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
