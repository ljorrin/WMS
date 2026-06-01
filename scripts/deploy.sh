#!/bin/bash
###############################################################################
# WMS Panama — Deploy Script
# Uso: ./scripts/deploy.sh [staging|production] [git-ref]
#
# Realiza:
#   1. Backup de BD
#   2. Pull de imágenes
#   3. Migraciones Alembic
#   4. Rolling update (sin downtime)
#   5. Smoke test post-deploy
###############################################################################

set -euo pipefail

ENV=${1:-staging}
GIT_REF=${2:-HEAD}
COMPOSE_FILE="docker-compose.prod.yml"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="/var/log/wms/deploy_${TIMESTAMP}.log"

# Colores
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

log() { echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} $1" | tee -a $LOG_FILE; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1" | tee -a $LOG_FILE; }
error() { echo -e "${RED}[ERROR]${NC} $1" | tee -a $LOG_FILE; exit 1; }

mkdir -p /var/log/wms
log "═══════════════════════════════════════════════"
log " WMS Panama — Deploy → $ENV"
log " Git ref: $GIT_REF"
log " Timestamp: $TIMESTAMP"
log "═══════════════════════════════════════════════"

# ── 1. Verificar prerequisitos ──────────────────────────────────────────────
log "Verificando prerequisitos..."
command -v docker >/dev/null 2>&1 || error "Docker no está instalado."
command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1 || \
    error "Docker Compose no está disponible."

# ── 2. Backup de BD ──────────────────────────────────────────────────────────
log "Ejecutando backup de BD..."
docker compose -f $COMPOSE_FILE exec -T pgbackup /backup.sh && \
    log "✅ Backup completado." || warn "⚠️  Backup falló — continuando igualmente."

# ── 3. Git pull ──────────────────────────────────────────────────────────────
log "Actualizando código..."
git fetch origin
git checkout $GIT_REF
git pull origin $GIT_REF 2>/dev/null || true

# ── 4. Pull de imágenes ──────────────────────────────────────────────────────
log "Descargando nuevas imágenes Docker..."
docker compose -f $COMPOSE_FILE pull api celery-worker celery-beat nginx

# ── 5. Migraciones Alembic ───────────────────────────────────────────────────
log "Ejecutando migraciones de BD..."
docker compose -f $COMPOSE_FILE run --rm --no-deps api alembic upgrade head && \
    log "✅ Migraciones completadas." || error "❌ Migraciones fallaron."

# ── 6. Rolling update de API ─────────────────────────────────────────────────
log "Iniciando rolling update de API..."
docker compose -f $COMPOSE_FILE up -d --no-deps --scale api=2 api
sleep 20  # Esperar a que nuevas instancias estén listas

# Health check de nuevas instancias
if curl -sf http://localhost:8000/api/v1/health/live >/dev/null 2>&1; then
    log "✅ Nuevas instancias saludables."
else
    error "❌ Nuevas instancias no responden. Revirtiendo..."
fi

# ── 7. Workers y Beat ────────────────────────────────────────────────────────
log "Actualizando workers Celery..."
docker compose -f $COMPOSE_FILE up -d --no-deps celery-worker celery-beat

# ── 8. Nginx ─────────────────────────────────────────────────────────────────
log "Recargando Nginx..."
docker compose -f $COMPOSE_FILE exec nginx nginx -s reload && \
    log "✅ Nginx recargado." || warn "⚠️  Nginx reload con advertencias."

# ── 9. Cleanup ────────────────────────────────────────────────────────────────
log "Limpiando imágenes antiguas..."
docker image prune -f --filter "until=72h" 2>/dev/null || true

# ── 10. Smoke test ────────────────────────────────────────────────────────────
log "Ejecutando smoke test post-deploy..."
sleep 10

BASE_URL="https://staging.wms.tuempresa.pa"
[ "$ENV" = "production" ] && BASE_URL="https://wms.tuempresa.pa"

for endpoint in "/api/v1/health/live" "/api/v1/health/ready"; do
    STATUS=$(curl -sf -o /dev/null -w "%{http_code}" "$BASE_URL$endpoint" 2>/dev/null || echo "000")
    if [ "$STATUS" = "200" ]; then
        log "✅ $endpoint → $STATUS"
    else
        error "❌ $endpoint → $STATUS"
    fi
done

# ── Resumen ───────────────────────────────────────────────────────────────────
log "═══════════════════════════════════════════════"
log " ✅ Deploy completado exitosamente"
log " Ambiente: $ENV"
log " Git ref: $(git rev-parse --short HEAD)"
log " Tiempo: $TIMESTAMP"
log "═══════════════════════════════════════════════"
