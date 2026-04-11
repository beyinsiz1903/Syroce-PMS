# ── Syroce Hotel PMS — Makefile ────────────────────────────────────
.PHONY: dev test lint build compose-up compose-down seed worker backup clean

# ── Development ──
dev:
	docker compose up --build

dev-backend:
	cd backend && uvicorn server:app --host 0.0.0.0 --port 8001 --reload

dev-frontend:
	cd frontend && yarn start

dev-worker:
	cd backend && celery -A celery_app worker --loglevel=info -Q default,ml,analytics,messaging,pipeline,backup

dev-beat:
	cd backend && celery -A celery_app beat --loglevel=info

# ── Testing ──
test:
	cd backend && python -m pytest tests/ -v --tb=short

test-unit:
	cd backend && python -m pytest tests/ -v -k "not api" --tb=short

test-api:
	cd backend && python -m pytest tests/ -v -k "api" --tb=short

test-frontend:
	cd frontend && yarn test --watchAll=false

# ── Linting ──
lint:
	cd backend && ruff check . --fix
	cd frontend && npx eslint src/ --fix

lint-backend:
	cd backend && ruff check . --fix

lint-frontend:
	cd frontend && npx eslint src/ --fix

# ── Build ──
build:
	docker compose -f docker-compose.prod.yml build

build-backend:
	docker build -t syroce-backend:latest ./backend

build-frontend:
	docker build -t syroce-frontend:latest ./frontend

build-worker:
	docker build -t syroce-worker:latest -f ./worker/Dockerfile .

# ── Docker Compose ──
compose-up:
	docker compose up -d

compose-down:
	docker compose down

compose-logs:
	docker compose logs -f --tail=100

compose-prod:
	docker compose -f docker-compose.prod.yml up -d

compose-prod-down:
	docker compose -f docker-compose.prod.yml down

# ── Database ──
seed:
	cd backend && python seed_demo_data.py

backup:
	cd backend && python -c "from infra.backup_manager import run_backup; import asyncio; asyncio.run(run_backup())"

# ── Worker Management ──
worker:
	cd backend && celery -A celery_app worker --loglevel=info -Q default,ml,analytics,messaging,pipeline,backup --concurrency=4

worker-status:
	cd backend && celery -A celery_app inspect active

worker-stats:
	cd backend && celery -A celery_app inspect stats

# ── Utilities ──
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	docker compose down -v --remove-orphans 2>/dev/null || true

shell:
	cd backend && python -c "from core.database import db; import asyncio; print('DB connected')"

health:
	curl -s http://localhost:8001/api/health/ | python3 -m json.tool
