#!/usr/bin/env bash
# ai_server — Docker Compose (YOLO TCP:5005 + LLM REST:8000)

set -e
ROS_WS="$(cd "$(dirname "$0")/.." && pwd)"
AI_DIR="$ROS_WS/server/ai_service"

# Docker 실행 여부 확인
if ! docker info > /dev/null 2>&1; then
    echo "[ai_server] ❌ Docker가 실행 중이지 않습니다. Docker Desktop을 먼저 실행하세요."
    exit 1
fi

CONTAINERS=("shoppinkki_yolo" "shoppinkki_llm")
all_running=1
for c in "${CONTAINERS[@]}"; do
    r=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -c "^${c}$" || true)
    [ "$r" -eq 1 ] || all_running=0
done

if [ "$all_running" -eq 1 ]; then
    echo "[ai_server] YOLO, LLM 컨테이너 이미 실행중 — 스킵"
else
    echo "[ai_server] Docker 이미지 빌드 및 기동 중..."
    echo "  YOLO  → TCP:5005"
    echo "  LLM   → REST:8000 (Ollama는 호스트의 11434 사용)"
    cd "$AI_DIR"
    docker compose up --build -d
fi

# 호스트 Ollama 체크
if ! curl -sf -o /dev/null http://127.0.0.1:11434/api/tags 2>/dev/null; then
    echo "[ai_server] ⚠️  호스트에 Ollama가 안 떠 있습니다."
    echo "           LLM 검색 시 키워드 추출이 실패하고 벡터 매칭만 동작합니다."
    echo "           해결: ollama serve & && ollama pull qwen2.5:3b"
fi

# 로그 출력
echo "[ai_server] 로그 출력 중... (Ctrl+C로 종료)"
cd "$AI_DIR"
docker compose logs -f
