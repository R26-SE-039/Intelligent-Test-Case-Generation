.PHONY: up down logs restart build dev-frontend dev-backend install format

# --- Docker Commands ---
up:
	docker-compose up --build -d

down:
	docker-compose down

logs:
	docker-compose logs -f

restart:
	docker-compose down
	docker-compose up --build -d

build:
	docker-compose build

# --- Local Development Commands ---
dev-frontend:
	cd frontend && pnpm run dev

dev-backend:
	cd backend && ".venv/Scripts/python" -m uvicorn app.main:app --reload --port 8002

install:
	npm install
	cd frontend && pnpm install
	cd backend && python -m venv .venv && ".venv/Scripts/python" -m pip install -r requirements.txt

format:
	npx lint-staged
