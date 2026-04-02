#!/usr/bin/env zsh
# ShopPinkki — control_service 시드 스크립트 선택 실행기
# 실행 위치: ros_ws 루트 어디서든 가능

SEED_PY="$(cd "$(dirname "$0")/.." && pwd)/src/control_center/control_service/control_service/seeds/seed_data.py"

echo ""
echo "┌─────────────────────────────────────────────┐"
echo "│    ShopPinkki  control_service  시딩         │"
echo "├─────────────────────────────────────────────┤"
echo "│  1) --reset    DB 초기화 후 재시딩           │"
echo "│               (스키마 변경 시 사용)           │"
echo "│  2) --replace  기존 행 덮어쓰기              │"
echo "│               (데이터 값 변경 시 사용)        │"
echo "│  3) (기본)     새 행만 추가                  │"
echo "│               (기존 행 유지)                  │"
echo "└─────────────────────────────────────────────┘"
echo ""
read -rp "선택 [1/2/3]: " choice

case "$choice" in
    1)
        echo "[seed.sh] DB 초기화 후 재시딩 (--reset) ..."
        python "$SEED_PY" --reset
        ;;
    2)
        echo "[seed.sh] 기존 행 덮어쓰기 (--replace) ..."
        python "$SEED_PY" --replace
        ;;
    3|"")
        echo "[seed.sh] 새 행만 추가 ..."
        python "$SEED_PY"
        ;;
    *)
        echo "[seed.sh] 올바른 번호를 입력하세요 (1, 2, 3)."
        exit 1
        ;;
esac
