#!/usr/bin/env zsh
# admin_app — PyQt6 관제 대시보드 (control_service 포함, 동일 프로세스)

set -e
ROS_WS="$(cd "$(dirname "$0")/.." && pwd)"

# ROS2 환경 소싱
if [ -f "$ROS_WS/install/setup.bash" ]; then
    source "$ROS_WS/install/setup.bash"
elif [ -f /opt/ros/jazzy/setup.bash ]; then
    source /opt/ros/jazzy/setup.bash
else
    echo "[admin_app] ⚠️  ROS2 환경을 찾을 수 없습니다. 수동으로 source 후 실행하세요."
    exit 1
fi

export ROS_DOMAIN_ID=14

echo "[admin_app] 관제 앱 기동 중..."
cd "$ROS_WS"
ros2 run admin_app admin_app
