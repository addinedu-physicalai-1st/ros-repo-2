#!/usr/bin/env zsh
# 쑈삥끼 서버 PC 통합 실행기
#
# tmux가 설치되어 있으면 하나의 세션에 4개 pane을 분할해 동시 실행.
# tmux가 없으면 각 스크립트를 개별 터미널에서 실행하는 방법을 안내.
#
# 사용법:
#   ./scripts/run_server.sh          # 전체 실행 (admin + customer_web + ai)
#   ./scripts/run_server.sh --no-ai  # AI 서버 제외 (Docker 없을 때 유용)

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
SESSION="shoppinkki"
NO_AI=false

for arg in "$@"; do
    [ "$arg" = "--no-ai" ] && NO_AI=true
done

# ── tmux 없을 때 안내 ──────────────────────────────────────────────────────────
if ! command -v tmux &> /dev/null; then
    echo ""
    echo "┌─────────────────────────────────────────────────────┐"
    echo "│  tmux가 설치되지 않아 통합 실행을 할 수 없습니다.     │"
    echo "│  터미널 4개를 열고 아래 명령어를 각각 실행하세요.      │"
    echo "└─────────────────────────────────────────────────────┘"
    echo ""
    echo "  [1] 관제 앱    :  $SCRIPTS_DIR/run_admin.sh"
    echo "  [2] 고객 웹앱  :  $SCRIPTS_DIR/run_customer_web.sh"
    if [ "$NO_AI" = false ]; then
    echo "  [3] AI 서버    :  $SCRIPTS_DIR/run_ai.sh"
    fi
    echo ""
    echo "  tmux 설치 방법:"
    echo "    macOS  → brew install tmux"
    echo "    Ubuntu → sudo apt install tmux"
    echo ""
    exit 0
fi

# ── 기존 세션 정리 ─────────────────────────────────────────────────────────────
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "[run_server] 기존 '$SESSION' 세션을 종료합니다..."
    tmux kill-session -t "$SESSION"
fi

# ── tmux 세션 생성 ─────────────────────────────────────────────────────────────
echo "[run_server] tmux 세션 '$SESSION' 생성 중..."

# 창 1: admin_app (관제 앱)
tmux new-session  -d -s "$SESSION" -n "admin"        \
    "bash $SCRIPTS_DIR/run_admin.sh; read -p '[종료됨] Enter를 누르면 닫힙니다.'"

# 창 2: customer_web
tmux new-window   -t "$SESSION" -n "customer_web"    \
    "bash $SCRIPTS_DIR/run_customer_web.sh; read -p '[종료됨] Enter를 누르면 닫힙니다.'"

# 창 3: AI 서버 (--no-ai 옵션 없을 때만)
if [ "$NO_AI" = false ]; then
    tmux new-window -t "$SESSION" -n "ai_server"     \
        "bash $SCRIPTS_DIR/run_ai.sh; read -p '[종료됨] Enter를 누르면 닫힙니다.'"
fi

# 창 4: 로그/쉘 (빈 창 — 디버깅용)
tmux new-window   -t "$SESSION" -n "shell"           \
    "cd $(dirname "$SCRIPTS_DIR") && exec bash"

# 첫 번째 창(admin)으로 포커스
tmux select-window -t "$SESSION:admin"

# ── 안내 출력 후 attach ────────────────────────────────────────────────────────
echo ""
echo "┌─────────────────────────────────────────────────────┐"
echo "│         쑈삥끼 서버 스택 기동 완료                   │"
echo "├─────────────────────────────────────────────────────┤"
echo "│  창 전환  : Ctrl+b  →  숫자키 (1~4) 또는 n/p        │"
echo "│  세션 분리: Ctrl+b  →  d                            │"
echo "│  재접속   : tmux attach -t $SESSION                  │"
echo "│  전체 종료: tmux kill-session -t $SESSION            │"
echo "└─────────────────────────────────────────────────────┘"
echo ""
echo "  [1] admin       — 관제 앱 (control_service 포함)"
echo "  [2] customer_web— 고객 웹앱 http://localhost:8501"
if [ "$NO_AI" = false ]; then
echo "  [3] ai_server   — YOLO TCP:5005 / LLM REST:8000"
fi
echo "  [4] shell       — 디버깅용 빈 쉘"
echo ""

tmux attach-session -t "$SESSION"
