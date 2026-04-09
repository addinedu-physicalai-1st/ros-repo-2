#!/usr/bin/env bash
# ShopPinkki — DB 시딩 스크립트 (Docker PostgreSQL)
# 실행 위치: ros_ws 루트에서  ./scripts/seed.sh

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONTAINER="shoppinkki_pg"
DB="shoppinkki"
USER="shoppinkki"
PASS="shoppinkki"
SCHEMA="$ROOT/scripts/db/schema.sql"
SEED="$ROOT/scripts/db/seed_data.sql"
PYTHON_BIN="${PYTHON_BIN:-python3}"

# ── PostgreSQL 실행 헬퍼 ─────────────────────────────
run_sql() {
    docker exec -i -e PGPASSWORD="$PASS" "$CONTAINER" \
        psql -U "$USER" -d "$DB" "$@"
}

pick_python() {
    if "$PYTHON_BIN" -c "import psycopg2" >/dev/null 2>&1; then
        echo "$PYTHON_BIN"
        return 0
    fi
    if command -v python >/dev/null 2>&1 && python -c "import psycopg2" >/dev/null 2>&1; then
        echo "python"
        return 0
    fi
    return 1
}

# ── 컨테이너 상태 확인 ──────────────────────────
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    echo "⚠️  PostgreSQL 컨테이너가 실행 중이지 않습니다."
    echo "    다음 명령으로 먼저 시작하세요:"
    echo ""
    echo "    cd $ROOT && docker compose up -d pg"
    echo ""
    exit 1
fi

echo ""
echo "┌─────────────────────────────────────────────┐"
echo "│    ShopPinkki  DB  시딩                      │"
echo "├─────────────────────────────────────────────┤"
echo "│  1) reset   DB 초기화 후 재시딩              │"
echo "│             (스키마 변경 시 사용)             │"
echo "│  2) replace 기존 행 덮어쓰기                 │"
echo "│             (데이터 값 변경 시 사용)          │"
echo "│  3) (기본)  새 행만 추가                     │"
echo "│  4) embed   상품 설명 임베딩 채우기           │"
echo "└─────────────────────────────────────────────┘"
echo ""
read -r -p "선택 [1/2/3/4]: " choice

case "$choice" in
    1)
        echo "[seed.sh] DB 초기화 후 재시딩 ..."
        docker exec -i -e PGPASSWORD="$PASS" "$CONTAINER" psql -U "$USER" -d postgres <<EOF
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = '$DB' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS $DB;
CREATE DATABASE $DB OWNER $USER ENCODING 'UTF8';
EOF
        run_sql < "$SCHEMA"
        run_sql < "$SEED"
        echo "✅ 완료 (reset)"
        ;;
    2)
        echo "[seed.sh] 기존 행 덮어쓰기 ..."
        run_sql < "$SEED"
        echo "✅ 완료 (replace — ON CONFLICT DO UPDATE 적용)"
        ;;
    3|"")
        echo "[seed.sh] 새 행만 추가 ..."
        run_sql < "$SEED"
        echo "✅ 완료"
        ;;
    4)
        echo "[seed.sh] 상품 설명 임베딩 채우기 ..."
        if ! PY="$(pick_python)"; then
            echo "⚠️  Python에 psycopg2가 설치되어 있지 않습니다."
            echo "    pip install psycopg2-binary 또는 pip install -r requirements.txt"
            exit 1
        fi
        "$PY" "$ROOT/scripts/db/fill_product_embeddings.py"
        echo "✅ 완료 (embed)"
        ;;
    *)
        echo "올바른 번호를 입력하세요 (1, 2, 3, 4)."
        exit 1
        ;;
esac
