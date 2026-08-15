.PHONY: up down logs restart build dev-backend install format

BACKEND_PORT ?= 8002

# --- Docker Commands (backend only) ---
up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f

restart:
	docker compose down
	docker compose up --build -d

build:
	docker compose build

# --- Local Development Commands ---
dev-backend:
	cd backend && ".venv/Scripts/python" -m uvicorn app.main:app --reload --reload-dir app --port $(BACKEND_PORT)

install:
	npm install
	cd backend && python -m venv .venv && ".venv/Scripts/python" -m pip install --upgrade pip setuptools wheel && ".venv/Scripts/python" -m pip install -r requirements.txt

format:
	npx lint-staged
