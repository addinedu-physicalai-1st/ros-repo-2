#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel)"
cd "$ROOT_DIR"

staged_files="$(git diff --cached --name-only --diff-filter=ACMR)"
if [[ -z "${staged_files}" ]]; then
  exit 0
fi

touch_control=0
touch_customer=0

while IFS= read -r file; do
  case "$file" in
    server/control_service/*)
      touch_control=1
      ;;
    server/customer_web/*)
      touch_customer=1
      ;;
  esac
done <<< "$staged_files"

if [[ $touch_control -eq 0 && $touch_customer -eq 0 ]]; then
  exit 0
fi

echo "[pre-commit] session/login regression gate start"

run_test() {
  local title="$1"
  shift
  echo "[pre-commit] running: $title"
  if ! "$@"; then
    echo "[pre-commit] FAILED: $title"
    echo "[pre-commit] hint: session reset on startup / active_user_id sync / mode gate / auth route"
    exit 1
  fi
}

run_test \
  "control_service:test_robot_manager.py" \
  bash -lc "cd server/control_service && PYTHONPATH=.:$ROOT_DIR/device/shoppinkki/shoppinkki_core python3 -m pytest test/test_robot_manager.py -q"

run_test \
  "control_service:test_rest_api_session.py" \
  bash -lc "cd server/control_service && PYTHONPATH=.:$ROOT_DIR/device/shoppinkki/shoppinkki_core python3 -m pytest test/test_rest_api_session.py -q"

if [[ $touch_customer -eq 1 ]]; then
  run_test \
    "customer_web:test_auth_flow.py" \
    bash -lc "cd server/customer_web && python3 -m pytest tests/test_auth_flow.py -q"
fi

echo "[pre-commit] session/login regression gate passed"
