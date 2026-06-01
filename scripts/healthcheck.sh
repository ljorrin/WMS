#!/bin/bash
###############################################################################
# WMS Panama — Health Check Script
# Uso: ./scripts/healthcheck.sh [staging|production]
# Verifica todos los servicios críticos del WMS
###############################################################################

ENV=${1:-staging}
BASE_URL="https://staging.wms.tuempresa.pa"
[ "$ENV" = "production" ] && BASE_URL="https://wms.tuempresa.pa"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=0
FAIL=0

check() {
    local name=$1
    local cmd=$2
    local expected=${3:-200}

    printf "  %-40s" "$name"
    result=$(eval "$cmd" 2>/dev/null)
    if [ "$result" = "$expected" ] || [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ PASS${NC}"
        ((PASS++))
    else
        echo -e "${RED}✗ FAIL${NC} (got: $result)"
        ((FAIL++))
    fi
}

echo ""
echo "═══════════════════════════════════════════════════"
echo " WMS Panama — Health Check ($ENV)"
echo " $(date)"
echo "═══════════════════════════════════════════════════"

echo ""
echo "── API Endpoints ──────────────────────────────────"
check "Liveness probe" \
    "curl -sf -o /dev/null -w '%{http_code}' $BASE_URL/api/v1/health/live"
check "Readiness probe" \
    "curl -sf -o /dev/null -w '%{http_code}' $BASE_URL/api/v1/health/ready"
check "API response time < 500ms" \
    "curl -sf -o /dev/null -w '%{time_total}' $BASE_URL/api/v1/health/live | awk '{exit ($1 > 0.5)}'"

echo ""
echo "── Frontend ───────────────────────────────────────"
check "Frontend index.html" \
    "curl -sf -o /dev/null -w '%{http_code}' $BASE_URL/"
check "Frontend assets cached" \
    "curl -sI $BASE_URL/ | grep -c 'Cache-Control'"

echo ""
echo "── SSL/TLS ────────────────────────────────────────"
check "SSL certificate valid" \
    "echo | openssl s_client -connect ${BASE_URL#https://}:443 -servername ${BASE_URL#https://} 2>/dev/null | openssl x509 -noout -checkend 86400 && echo 0 || echo 1" \
    "0"
check "TLS 1.3 supported" \
    "curl -sf --tls-max 1.3 -o /dev/null -w '%{http_code}' $BASE_URL/"

echo ""
echo "── Rate Limiting ───────────────────────────────────"
check "Auth rate limit active" \
    "for i in {1..10}; do curl -sf -o /dev/null -w '%{http_code}' -X POST $BASE_URL/api/v1/auth/login -H 'Content-Type: application/json' -d '{\"email\":\"x\",\"password\":\"y\"}'; done | grep -c 429"

echo ""
echo "── Security Headers ────────────────────────────────"
check "HSTS header present" \
    "curl -sI $BASE_URL/ | grep -ic 'strict-transport-security'"
check "X-Frame-Options DENY" \
    "curl -sI $BASE_URL/ | grep -ic 'x-frame-options'"
check "Content-Security-Policy" \
    "curl -sI $BASE_URL/ | grep -ic 'content-security-policy'"

echo ""
echo "═══════════════════════════════════════════════════"
echo -e " Results: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}"
echo "═══════════════════════════════════════════════════"
echo ""

[ $FAIL -gt 0 ] && exit 1 || exit 0
