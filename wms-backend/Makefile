# ─── WMS Panama — Makefile ─────────────────────────────────────────────────────
# Comandos de desarrollo para el equipo.
# Uso: make <comando>
# ──────────────────────────────────────────────────────────────────────────────

.PHONY: help up down build logs db-upgrade db-downgrade db-migrate db-reset \
        seed test test-cov lint format typecheck clean shell

# Colores para la consola
GREEN  := \033[0;32m
YELLOW := \033[0;33m
RESET  := \033[0m

help: ## 📖 Muestra esta ayuda
	@echo ""
	@echo "  $(GREEN)WMS Panama — Comandos de Desarrollo$(RESET)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""

# ── Docker ────────────────────────────────────────────────────────────────────

up: ## 🚀 Levantar todos los servicios (detached)
	docker compose up -d
	@echo "$(GREEN)Servicios corriendo:$(RESET)"
	@echo "  API:         http://localhost:8000"
	@echo "  Docs:        http://localhost:8000/api/docs"
	@echo "  MailHog:     http://localhost:8025"
	@echo "  Meilisearch: http://localhost:7700"

down: ## 🛑 Detener todos los servicios
	docker compose down

build: ## 🔨 Rebuild de imágenes Docker
	docker compose build --no-cache

logs: ## 📋 Ver logs de la API en tiempo real
	docker compose logs -f api

logs-all: ## 📋 Ver logs de todos los servicios
	docker compose logs -f

restart-api: ## 🔄 Reiniciar solo el API
	docker compose restart api

# ── Base de Datos / Migraciones ───────────────────────────────────────────────

db-upgrade: ## ⬆️  Aplicar migraciones pendientes (upgrade head)
	docker compose exec api alembic upgrade head

db-downgrade: ## ⬇️  Revertir última migración
	docker compose exec api alembic downgrade -1

db-migrate: ## 📝 Crear nueva migración (usar: make db-migrate MSG="descripcion")
	docker compose exec api alembic revision --autogenerate -m "$(MSG)"

db-history: ## 📚 Ver historial de migraciones
	docker compose exec api alembic history --verbose

db-current: ## 🔍 Ver migración actual
	docker compose exec api alembic current

db-reset: ## ⚠️  RESET COMPLETO de la BD (desarrollo solamente)
	@echo "$(YELLOW)⚠️  ADVERTENCIA: Esto borrará todos los datos.$(RESET)"
	@read -p "¿Estás seguro? [s/N] " CONFIRM && [ "$$CONFIRM" = "s" ] || exit 1
	docker compose exec api alembic downgrade base
	docker compose exec api alembic upgrade head
	$(MAKE) seed

db-shell: ## 🐘 Shell de PostgreSQL
	docker compose exec postgres psql -U $${POSTGRES_USER:-wms_user} -d $${POSTGRES_DB:-wms_db}

# ── Seeds ─────────────────────────────────────────────────────────────────────

seed: ## 🌱 Cargar datos iniciales (tenant demo, superadmin, permisos)
	docker compose exec api python -m seeds.run_all

seed-demo: ## 🌱 Cargar datos de demostración completos
	docker compose exec api python -m seeds.demo_data

# ── Testing ───────────────────────────────────────────────────────────────────

test: ## 🧪 Ejecutar tests
	docker compose exec api pytest tests/ -v --tb=short

test-cov: ## 🧪 Tests con reporte de cobertura
	docker compose exec api pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=html

test-unit: ## 🧪 Solo tests unitarios
	docker compose exec api pytest tests/unit/ -v

test-integration: ## 🧪 Solo tests de integración
	docker compose exec api pytest tests/integration/ -v

test-watch: ## 🧪 Tests en modo watch (requiere pytest-watch)
	docker compose exec api ptw tests/ -- -v

# ── Calidad de Código ─────────────────────────────────────────────────────────

lint: ## 🔍 Verificar estilo de código
	docker compose exec api flake8 app/ tests/

format: ## 🎨 Formatear código automáticamente
	docker compose exec api black app/ tests/ seeds/
	docker compose exec api isort app/ tests/ seeds/

typecheck: ## 🔎 Verificar tipos con mypy
	docker compose exec api mypy app/ --ignore-missing-imports

check: lint typecheck ## ✅ Lint + typecheck (pre-commit)

# ── Desarrollo local (sin Docker) ─────────────────────────────────────────────

install: ## 📦 Instalar dependencias localmente (sin Docker)
	pip install -r requirements.txt

run: ## 🏃 Correr API localmente (sin Docker)
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

run-prod: ## 🏭 Correr API en modo producción (sin Docker)
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# ── Utilidades ────────────────────────────────────────────────────────────────

shell: ## 🐚 Shell en el container de la API
	docker compose exec api bash

shell-python: ## 🐍 Python REPL con contexto del app
	docker compose exec api python -c "from app.core.config import settings; import IPython; IPython.start_ipython()"

secret-key: ## 🔑 Generar una SECRET_KEY segura
	@python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))"

clean: ## 🧹 Limpiar archivos temporales
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null; true
	find . -type f -name ".coverage" -delete 2>/dev/null; true

# ── Seguridad ──────────────────────────────────────────────────────────────────

security-check: ## 🔒 Verificar vulnerabilidades en dependencias
	docker compose exec api pip install safety -q && safety check -r requirements.txt

# ── CI/CD Shortcuts ───────────────────────────────────────────────────────────

ci: ## 🤖 Pipeline completo de CI (lint + test + typecheck)
	$(MAKE) lint
	$(MAKE) typecheck
	$(MAKE) test-cov
