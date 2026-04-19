#!/usr/bin/env bash
# 쑈삥끼 시뮬레이션 — 노트북 실행 (Gazebo + shoppinkki_core)
#
# 포함: Gazebo + Nav2 x2 + shoppinkki_core (로봇 54, 18)
# 제외: control_service, admin_ui, customer_web → run_server.sh / run_ui.sh 별도 실행
#
# 전체 개발 워크플로우 (시뮬):
#   터미널 A: bash scripts/run_server.sh
#   터미널 B: bash scripts/run_ui.sh
#   터미널 C: bash scripts/run_sim.sh          ← 이 스크립트
#
# 사용법:
#   ./scripts/run_sim.sh

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
ROS_WS="$(dirname "$SCRIPTS_DIR")"
SESSION="sp_sim"

source "$SCRIPTS_DIR/_ros_env.sh"

ROS_ENV="$TMUX_ROS_ENV"

# ── 환경 확인 ──────────────────────────────────────────────────────────────────
if ! command -v tmux &>/dev/null; then
    echo "tmux 필요: brew install tmux  또는  sudo apt install tmux"
    exit 1
fi

# ── 기존 세션 및 좀비 프로세스 정리 ───────────────────────────────────────────
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "[run_sim] 기존 '$SESSION' 세션 종료..."
    tmux kill-session -t "$SESSION"
fi

# Gazebo 및 관련 프로세스 전부 정리 (이전 run이 tmux 밖에서 띄운 것도 포함).
# 순서: SIGTERM → 잠시 대기 → SIGKILL → 최종 대기 (shm/UDP 포트 해제 시간 포함).
echo "[run_sim] Gazebo/Nav2/core 잔존 프로세스 정리..."
_PATTERNS=(
    "gz sim"
    "gz_sim"
    "ruby.*gz sim"
    "parameter_bridge"
    "robot_state_publisher"
    "nav2_lifecycle_manager"
    "nav2_"
    "lifecycle_manager"
    "ros_gz_bridge"
    "ros_gz_sim"
    "shoppinkki_core"
    "shoppinkki_main"
    "ros2 launch shoppinkki_nav"
)
for pat in "${_PATTERNS[@]}"; do
    pkill -f "$pat" 2>/dev/null || true
done
sleep 2
for pat in "${_PATTERNS[@]}"; do
    pkill -9 -f "$pat" 2>/dev/null || true
done

# Gazebo SHM / 임시파일 잔존 정리 (macOS + fastrtps/cyclonedds SHM)
rm -f /dev/shm/fastrtps_* /tmp/gz-* 2>/dev/null || true
rm -rf /tmp/fastrtps_* 2>/dev/null || true

# 포트 해제 & 프로세스 소멸 대기
sleep 3

# 실제 남아있는지 확인
_leftover=$(pgrep -fl "gz sim|nav2_|shoppinkki_core" 2>/dev/null || true)
if [ -n "$_leftover" ]; then
    echo "[run_sim] ⚠️  여전히 잔존 프로세스 있음:"
    echo "$_leftover"
    echo "[run_sim] 수동 확인 필요: pkill -9 -f 'gz sim' 후 재실행"
fi

echo "[run_sim] tmux 세션 '$SESSION' 생성 중..."
tmux set-option -g mouse on 2>/dev/null || true

# ── 창 생성 ────────────────────────────────────────────────────────────────────

# 창 0: Gazebo server + Nav2 (GUI 제외)
tmux new-session -d -s "$SESSION" -n "gz"
tmux send-keys -t "${SESSION}:gz" \
    "$TMUX_SRC && $ROS_ENV && cd $ROS_WS && ros2 launch shoppinkki_nav gz_multi_robot.launch.py" Enter

# 창 "gz_gui": macOS에서는 GUI를 interactive shell에서 직접 띄운다
# (launch 내 ExecuteProcess 환경 전달 불안정 회피). 서버 로딩 대기 후 실행.
if [ "$(uname)" = "Darwin" ]; then
    tmux new-window -t "${SESSION}" -n "gz_gui"
    # 15초 대기 후 resource path 명시 export 하고 gz sim -g 기동.
    # 에러 시 5초 후 재시작 루프로 자동 복구.
    _GZ_GUI_CMD='until [ -n "$(pgrep -f "gz sim -s")" ]; do sleep 1; done; sleep 10; \
        P=$(ros2 pkg prefix pinky_description)/share; \
        G=$(ros2 pkg prefix pinky_gz_sim)/share/pinky_gz_sim/models; \
        export GZ_SIM_RESOURCE_PATH="$P:$G:$HOME/.gazebo/models"; \
        echo "[gz_gui] GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH"; \
        while true; do gz sim -g -v4; echo "[gz_gui] exited, restart in 5s..."; sleep 5; done'
    tmux send-keys -t "${SESSION}:gz_gui" \
        "$TMUX_SRC && $ROS_ENV && $_GZ_GUI_CMD" Enter
fi

# 창 1–2: shoppinkki_core
# macOS SIP 가 /usr/bin/env 경유 시 DYLD_LIBRARY_PATH 를 제거하므로 python3 직접 호출
_SHOP_CORE_MAIN="$ROS_WS/install/shoppinkki_core/lib/shoppinkki_core/main_node"

# 창 1: shoppinkki_core 로봇 54
tmux new-window -t "${SESSION}" -n "core54"
tmux send-keys -t "${SESSION}:core54" \
    "$TMUX_SRC && $ROS_ENV && ROBOT_ID=54 python3 $_SHOP_CORE_MAIN --ros-args -p use_sim_time:=true" Enter

# 창 2: shoppinkki_core 로봇 18
tmux new-window -t "${SESSION}" -n "core18"
tmux send-keys -t "${SESSION}:core18" \
    "$TMUX_SRC && $ROS_ENV && ROBOT_ID=18 python3 $_SHOP_CORE_MAIN --ros-args -p use_sim_time:=true" Enter

tmux select-window -t "${SESSION}:gz"

# ── 안내 ───────────────────────────────────────────────────────────────────────
echo ""
echo "┌──────────────────────────────────────────────────────────────┐"
echo "│         쑈삥끼 시뮬레이션 기동                               │"
echo "├──────────────────────────────────────────────────────────────┤"
echo "│  gz       — Gazebo server + Nav2                            │"
echo "│  gz_gui   — Gazebo GUI (macOS 전용, 자동 재시작)             │"
echo "│  core54   — shoppinkki_core 로봇 54                          │"
echo "│  core18   — shoppinkki_core 로봇 18                          │"
echo "├──────────────────────────────────────────────────────────────┤"
echo "├──────────────────────────────────────────────────────────────┤"
echo "│  실행 순서:                                                   │"
echo "│  ① gz 창 — Gazebo 로딩 대기 (~60초)                         │"
echo "│  ② admin_ui — 각 로봇 [위치 초기화] 버튼 클릭               │"
echo "│  ③ customer_web (?robot_id=54/18) 로그인 → IDLE 전환        │"
echo "│  ④ [시뮬레이션 모드] 버튼으로 추종 없이 쇼핑 테스트          │"
echo "├──────────────────────────────────────────────────────────────┤"
echo "│  서버: bash scripts/run_server.sh                            │"
echo "│  UI  : bash scripts/run_ui.sh                                │"
echo "│  세션 종료: tmux kill-session -t $SESSION                    │"
echo "└──────────────────────────────────────────────────────────────┘"
echo ""

tmux attach-session -t "$SESSION"