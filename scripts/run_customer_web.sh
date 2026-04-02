#!/usr/bin/env zsh
# customer_web — Flask + SocketIO 고객 웹앱 (포트 8501)

set -e
ROS_WS="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$ROS_WS/services/customer_web"

echo "[customer_web] 기동 중... (http://localhost:8501)"
cd "$APP_DIR"
python app.py
