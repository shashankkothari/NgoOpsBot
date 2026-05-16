#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# smoke_test.sh — Smoke test the running NgoOpsBot backend.
#
# Usage:
#   ./scripts/smoke_test.sh [BASE_URL]
#
# Environment:
#   ADMIN_API_KEY  — admin key (defaults to the test key below)
#   BASE_URL       — defaults to http://localhost:8000
#
# Exit codes:
#   0 — all checks passed
#   1 — one or more checks failed
# ---------------------------------------------------------------------------

set -euo pipefail

BASE_URL="${1:-${BASE_URL:-http://localhost:8000}}"
ADMIN_API_KEY="${ADMIN_API_KEY:-df0fe3ac8602e4f262d71bedbb6c52f1f2cc83107f2243efbed5fc9631eea33f}"

# Colours
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Colour

PASS=0
FAIL=0
CREATED_NGO_ID=""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASS++)) || true
}

fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAIL++)) || true
}

info() {
    echo -e "${YELLOW}[INFO]${NC} $1"
}

http_get() {
    local url="$1"
    shift
    curl -s -o /tmp/smoke_resp.json -w "%{http_code}" "$@" "$url"
}

http_post() {
    local url="$1"
    local body="$2"
    shift 2
    curl -s -o /tmp/smoke_resp.json -w "%{http_code}" \
        -X POST -H "Content-Type: application/json" -d "$body" "$@" "$url"
}

http_delete() {
    local url="$1"
    shift
    curl -s -o /tmp/smoke_resp.json -w "%{http_code}" -X DELETE "$@" "$url"
}

print_response() {
    if command -v jq &>/dev/null; then
        jq . /tmp/smoke_resp.json 2>/dev/null || cat /tmp/smoke_resp.json
    else
        cat /tmp/smoke_resp.json
    fi
}

# ---------------------------------------------------------------------------
# Step 1: Health check — liveness probe
# ---------------------------------------------------------------------------

info "Step 1: Health check (GET /health)"
CODE=$(http_get "${BASE_URL}/health")
if [[ "$CODE" == "200" ]]; then
    pass "GET /health returned 200"
else
    fail "GET /health returned ${CODE} (expected 200)"
fi

# ---------------------------------------------------------------------------
# Step 2: Admin auth with correct key
# ---------------------------------------------------------------------------

info "Step 2: Admin auth — correct key"
CODE=$(http_get "${BASE_URL}/api/v1/admin/ngos" \
    -H "X-Admin-API-Key: ${ADMIN_API_KEY}")
if [[ "$CODE" == "200" ]]; then
    pass "GET /api/v1/admin/ngos with correct key returned 200"
else
    fail "GET /api/v1/admin/ngos with correct key returned ${CODE} (expected 200)"
    info "Response body:"
    print_response
fi

# ---------------------------------------------------------------------------
# Step 3: Admin auth with wrong key → 401
# ---------------------------------------------------------------------------

info "Step 3: Admin auth — wrong key should return 401"
CODE=$(http_get "${BASE_URL}/api/v1/admin/ngos" \
    -H "X-Admin-API-Key: definitely-wrong-key-zzz")
if [[ "$CODE" == "401" ]]; then
    pass "GET /api/v1/admin/ngos with wrong key returned 401"
else
    fail "GET /api/v1/admin/ngos with wrong key returned ${CODE} (expected 401)"
fi

# ---------------------------------------------------------------------------
# Step 4: List NGOs
# ---------------------------------------------------------------------------

info "Step 4: List NGOs"
CODE=$(http_get "${BASE_URL}/api/v1/admin/ngos" \
    -H "X-Admin-API-Key: ${ADMIN_API_KEY}")
if [[ "$CODE" == "200" ]]; then
    TOTAL=$(jq '.total // 0' /tmp/smoke_resp.json 2>/dev/null || echo "unknown")
    pass "GET /api/v1/admin/ngos returned 200 (total NGOs: ${TOTAL})"
else
    fail "GET /api/v1/admin/ngos returned ${CODE} (expected 200)"
fi

# ---------------------------------------------------------------------------
# Step 5: Create a test NGO
# ---------------------------------------------------------------------------

info "Step 5: Create test NGO"
UNIQUE_SUFFIX="$(date +%s)"
CREATE_PAYLOAD="{
  \"name\": \"Smoke Test NGO ${UNIQUE_SUFFIX}\",
  \"telegram_bot_token\": \"${UNIQUE_SUFFIX}:AAbbCCddEEffGGhhIIjjKKllMMnnOOppQQ\",
  \"anthropic_api_key\": \"sk-ant-smoke-test-key\",
  \"timezone\": \"UTC\",
  \"language\": \"en\"
}"

CODE=$(http_post "${BASE_URL}/api/v1/admin/ngos" "${CREATE_PAYLOAD}" \
    -H "X-Admin-API-Key: ${ADMIN_API_KEY}")

if [[ "$CODE" == "201" ]]; then
    CREATED_NGO_ID=$(jq -r '.id // ""' /tmp/smoke_resp.json 2>/dev/null || echo "")
    CREATED_SLUG=$(jq -r '.slug // ""' /tmp/smoke_resp.json 2>/dev/null || echo "")
    pass "POST /api/v1/admin/ngos returned 201 (id=${CREATED_NGO_ID}, slug=${CREATED_SLUG})"
else
    fail "POST /api/v1/admin/ngos returned ${CODE} (expected 201)"
    info "Response body:"
    print_response
fi

# ---------------------------------------------------------------------------
# Step 6: Get the created NGO by id
# ---------------------------------------------------------------------------

if [[ -n "$CREATED_NGO_ID" ]]; then
    info "Step 6: Fetch created NGO by id"
    CODE=$(http_get "${BASE_URL}/api/v1/admin/ngos/${CREATED_NGO_ID}" \
        -H "X-Admin-API-Key: ${ADMIN_API_KEY}")
    if [[ "$CODE" == "200" ]]; then
        FETCHED_ID=$(jq -r '.id // ""' /tmp/smoke_resp.json 2>/dev/null || echo "")
        if [[ "$FETCHED_ID" == "$CREATED_NGO_ID" ]]; then
            pass "GET /api/v1/admin/ngos/${CREATED_NGO_ID} returned correct NGO"
        else
            fail "GET /api/v1/admin/ngos/${CREATED_NGO_ID} returned wrong id: ${FETCHED_ID}"
        fi
    else
        fail "GET /api/v1/admin/ngos/${CREATED_NGO_ID} returned ${CODE} (expected 200)"
    fi
else
    info "Step 6: Skipped (no NGO id — creation failed)"
fi

# ---------------------------------------------------------------------------
# Step 7: Update (PATCH) the created NGO
# ---------------------------------------------------------------------------

if [[ -n "$CREATED_NGO_ID" ]]; then
    info "Step 7: Update NGO timezone"
    CODE=$(curl -s -o /tmp/smoke_resp.json -w "%{http_code}" \
        -X PATCH \
        -H "Content-Type: application/json" \
        -H "X-Admin-API-Key: ${ADMIN_API_KEY}" \
        -d '{"timezone": "America/New_York"}' \
        "${BASE_URL}/api/v1/admin/ngos/${CREATED_NGO_ID}")
    if [[ "$CODE" == "200" ]]; then
        TZ=$(jq -r '.timezone // ""' /tmp/smoke_resp.json 2>/dev/null || echo "")
        if [[ "$TZ" == "America/New_York" ]]; then
            pass "PATCH /api/v1/admin/ngos/${CREATED_NGO_ID} updated timezone"
        else
            fail "PATCH returned wrong timezone: ${TZ}"
        fi
    else
        fail "PATCH /api/v1/admin/ngos/${CREATED_NGO_ID} returned ${CODE} (expected 200)"
    fi
else
    info "Step 7: Skipped"
fi

# ---------------------------------------------------------------------------
# Step 8: Get NGO stats
# ---------------------------------------------------------------------------

if [[ -n "$CREATED_NGO_ID" ]]; then
    info "Step 8: NGO stats"
    CODE=$(http_get "${BASE_URL}/api/v1/admin/ngos/${CREATED_NGO_ID}/stats" \
        -H "X-Admin-API-Key: ${ADMIN_API_KEY}")
    if [[ "$CODE" == "200" ]]; then
        pass "GET /api/v1/admin/ngos/${CREATED_NGO_ID}/stats returned 200"
    else
        fail "GET /api/v1/admin/ngos/${CREATED_NGO_ID}/stats returned ${CODE} (expected 200)"
    fi
else
    info "Step 8: Skipped"
fi

# ---------------------------------------------------------------------------
# Step 9: Soft-delete (DELETE) the test NGO
# ---------------------------------------------------------------------------

if [[ -n "$CREATED_NGO_ID" ]]; then
    info "Step 9: Soft-delete test NGO"
    CODE=$(http_delete "${BASE_URL}/api/v1/admin/ngos/${CREATED_NGO_ID}" \
        -H "X-Admin-API-Key: ${ADMIN_API_KEY}")
    if [[ "$CODE" == "204" ]]; then
        pass "DELETE /api/v1/admin/ngos/${CREATED_NGO_ID} returned 204"

        # Verify is_active=false
        CODE=$(http_get "${BASE_URL}/api/v1/admin/ngos/${CREATED_NGO_ID}" \
            -H "X-Admin-API-Key: ${ADMIN_API_KEY}")
        IS_ACTIVE=$(jq -r '.is_active // "unknown"' /tmp/smoke_resp.json 2>/dev/null || echo "unknown")
        if [[ "$IS_ACTIVE" == "false" ]]; then
            pass "Soft-delete confirmed: is_active=false"
        else
            fail "Soft-delete: is_active=${IS_ACTIVE} (expected false)"
        fi
    else
        fail "DELETE /api/v1/admin/ngos/${CREATED_NGO_ID} returned ${CODE} (expected 204)"
    fi
else
    info "Step 9: Skipped"
fi

# ---------------------------------------------------------------------------
# Step 10: Admin support list
# ---------------------------------------------------------------------------

info "Step 10: Admin support ticket list"
CODE=$(http_get "${BASE_URL}/api/v1/admin/support" \
    -H "X-Admin-API-Key: ${ADMIN_API_KEY}")
if [[ "$CODE" == "200" ]]; then
    pass "GET /api/v1/admin/support returned 200"
else
    fail "GET /api/v1/admin/support returned ${CODE} (expected 200)"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "========================================"
echo "Smoke test summary"
echo "========================================"
echo -e "${GREEN}PASS: ${PASS}${NC}"
echo -e "${RED}FAIL: ${FAIL}${NC}"
echo "========================================"

if [[ "$FAIL" -gt 0 ]]; then
    echo -e "${RED}RESULT: FAIL${NC}"
    exit 1
else
    echo -e "${GREEN}RESULT: PASS${NC}"
    exit 0
fi
