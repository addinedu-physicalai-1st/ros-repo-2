# 시나리오 16: 관제 — 로봇 Offline 감지

**SM 전환:** 없음 (control_service 측 감지)
**관련 패키지:** admin_ui, control_service

---

## 개요

로봇이 재시작되거나 네트워크 연결이 끊기면 `/robot_<id>/status` 토픽 발행이 중단된다.
control_service의 cleanup 스레드가 `last_seen` 기준 `ROBOT_TIMEOUT_SEC(30s)` 초과를 감지하고
`active_user_id = NULL` 처리 및 admin_ui에 TCP push로 offline 상태를 전달한다.
로봇이 재연결되면 자동으로 online 복귀 처리한다.

> **아키텍처:** admin_ui은 control_service와 **별도 프로세스**. **채널 B(TCP)**로 연결된다.
> control_service가 offline/online 이벤트 발생 시 admin_ui에 TCP push.

---

## 기능 체크리스트

| 완료 | 기능 |
|:---:|---|
| [ ] | control_service: cleanup 스레드 (10s 주기) 실행 |
| [ ] | cleanup 스레드: `last_seen < now - ROBOT_TIMEOUT_SEC(30s)` → offline 감지 |
| [ ] | offline 시: `ROBOT.active_user_id = NULL` 갱신 |
| [ ] | offline 시: `ROBOT.current_mode = "OFFLINE"` 갱신 |
| [ ] | control_service → admin_ui TCP push (채널 B): `{"type": "offline", "robot_id": <id>}` |
| [ ] | admin_ui: 해당 로봇 카드 회색 처리 + "오프라인" 뱃지 표시 |
| [ ] | admin_ui: 맵 오버레이 로봇 아이콘 × 표시 (마지막 알려진 위치 유지) |
| [ ] | 재연결 시: `/robot_<id>/status` 재수신 → `last_seen` 갱신 → online 복귀 |
| [ ] | control_service → admin_ui TCP push: `{"type": "online", "robot_id": <id>}` |
| [ ] | admin_ui: 로봇 카드 정상 상태로 복구 (회색 해제, 뱃지 제거) |
| [ ] | 로봇이 offline 중 세션 있었으면: 재연결 후 Pi SM 상태 확인 필요 (IDLE 복귀 여부) |

---

## 전제조건

- admin_ui + control_service 기동 중, admin_ui이 control_service에 TCP 연결됨 (채널 B)
- 로봇이 기동 중이었다가 재시작 또는 네트워크 연결 끊김 발생
- `ROBOT_TIMEOUT_SEC = 30` 설정

---

## 흐름

```
────── Offline 감지 ──────

Pi: /robot_<id>/status 발행 중단 (재시작 or 네트워크 끊김)
    ↓
control_service cleanup 스레드 (10s 주기):
    SELECT robot_id, last_seen, active_user_id FROM robot
    → last_seen < now - 30s
    → ROBOT.current_mode = "OFFLINE"
    → ROBOT.active_user_id = NULL
    → TCP push → admin_ui (채널 B): {"type": "offline", "robot_id": <id>}
    ↓
admin_ui: "offline" TCP 수신 → offline_signal.emit(robot_id) → Qt 메인 스레드
    → 로봇 카드 회색 처리
    → "오프라인" 뱃지 표시
    → 맵 오버레이: 로봇 아이콘 × 표시 (마지막 위치 그대로)

────── Reconnect (재연결) ──────

Pi: 재기동 후 /robot_<id>/status 재발행
    ↓
control_service: _on_status() 수신
    → ROBOT.last_seen = now 갱신
    → ROBOT.current_mode = status['mode']  (Pi 측 현재 상태)
    ※ Pi 재기동 시 SM은 IDLE에서 재시작 (shoppinkki_core 초기화)
    → ROBOT.active_user_id = NULL (Pi 재기동 → 세션 없음)
    → TCP push → admin_ui (채널 B): {"type": "online", "robot_id": <id>}
    → TCP push → admin_ui: {"type": "status", "robot_id": <id>, ...}
    ↓
admin_ui: 로봇 카드 정상 표시 복구 (회색 해제, 뱃지 제거)
    → 맵 오버레이 아이콘 정상 복구
```

### Timeout 파라미터

| 파라미터 | 값 | 설명 |
|---|---|---|
| `ROBOT_TIMEOUT_SEC` | 30s | 마지막 status 수신 후 offline 판정까지 시간 |
| cleanup 스레드 주기 | 10s | offline 감지 최대 지연: ROBOT_TIMEOUT_SEC + 10s = 40s |

---

## 예제 코드 및 모순 점검

### control_service: cleanup 스레드

```python
# control_service/main_node.py
import threading
from datetime import datetime, timedelta

ROBOT_TIMEOUT_SEC = 30
CLEANUP_INTERVAL_SEC = 10

class ControlServiceNode(rclpy.node.Node):
    def __init__(self):
        super().__init__('control_service')
        self._offline_robots: set[int] = set()
        self._stop_event = threading.Event()

        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop, daemon=True
        )
        self._cleanup_thread.start()

    def _cleanup_loop(self):
        while not self._stop_event.is_set():
            self._stop_event.wait(CLEANUP_INTERVAL_SEC)
            if not self._stop_event.is_set():
                self._run_cleanup()

    def _run_cleanup(self):
        threshold = (datetime.now() - timedelta(seconds=ROBOT_TIMEOUT_SEC)).isoformat()
        with self._db_lock:
            rows = self.db.execute(
                "SELECT robot_id, current_mode FROM robot WHERE last_seen < ?",
                (threshold,)
            ).fetchall()

        for robot_id, current_mode in rows:
            if current_mode == "OFFLINE":
                continue  # 이미 offline 처리됨

            self.get_logger().warn(f"Robot {robot_id} offline (last_seen < {threshold})")
            with self._db_lock:
                self.db.execute("""
                    UPDATE robot SET current_mode='OFFLINE', active_user_id=NULL
                    WHERE robot_id=?
                """, (robot_id,))
            self._offline_robots.add(robot_id)

            # 채널 B: admin_ui TCP push
            self._tcp_push_admin({"type": "offline", "robot_id": robot_id})

    def _on_status(self, robot_id: int, msg):
        data = json.loads(msg.data)
        now = datetime.now().isoformat()
        was_offline = robot_id in self._offline_robots

        with self._db_lock:
            self.db.execute("""
                UPDATE robot
                SET current_mode=?, pos_x=?, pos_y=?, battery_level=?, last_seen=?
                WHERE robot_id=?
            """, (data['mode'], data['pos_x'], data['pos_y'], data['battery'], now, robot_id))

        if was_offline:
            self._offline_robots.discard(robot_id)
            # 채널 B: admin_ui TCP push
            self._tcp_push_admin({"type": "online", "robot_id": robot_id})

        # 채널 B: 상태 갱신 push (scenario_13과 동일)
        self._tcp_push_admin({
            "type": "status", "robot_id": robot_id,
            "mode": data['mode'], "pos_x": data['pos_x'], "pos_y": data['pos_y'],
            "battery": data['battery'], "last_seen": now
        })
```

### admin_ui: Offline/Online TCP 메시지 처리

```python
# admin_ui/main_window.py
class AdminMainWindow(QMainWindow):
    robot_offline_signal = pyqtSignal(int)   # (robot_id,)
    robot_online_signal = pyqtSignal(int)    # (robot_id,)

    def __init__(self):
        super().__init__()
        self.robot_offline_signal.connect(self._show_offline)
        self.robot_online_signal.connect(self._show_online)

    def _on_tcp_message(self, msg: dict):
        """채널 B TCP 수신 메시지 라우팅"""
        t = msg.get('type')
        if t == 'offline':
            self.robot_offline_signal.emit(msg['robot_id'])
        elif t == 'online':
            self.robot_online_signal.emit(msg['robot_id'])
        elif t == 'status':
            self.status_signal.emit(msg)

    def _show_offline(self, robot_id: int):
        card = self.robot_cards[robot_id]
        card.setStyleSheet("background-color: #888; color: #555;")
        card.status_badge.setText("오프라인")
        card.status_badge.setStyleSheet("background: gray;")
        self.map_widget.set_robot_offline(robot_id)

    def _show_online(self, robot_id: int):
        card = self.robot_cards[robot_id]
        card.setStyleSheet("")
        card.status_badge.setText("온라인")
        self.map_widget.set_robot_online(robot_id)
```

### 모순 및 검토 사항

| # | 항목 | 내용 | 처리 |
|---|---|---|---|
| 1 | **cleanup 스레드 종료** | `threading.Event().wait()` 매번 새 Event 생성 → 종료 신호 없음 | `self._stop_event = threading.Event()` 사용. `stop_event.wait(timeout=10)`, 종료 시 `stop_event.set()` |
| 2 | **DB 동시 접근** | cleanup 스레드 + ROS 콜백 스레드가 동시에 DB 갱신 | `threading.Lock()` (`self._db_lock`) 으로 보호 |
| 3 | **재연결 시 active_user_id** | Pi 재기동 시 이전 세션이 중앙 DB에 `is_active=True`로 남아있을 수 있음 | 재연결 시 control_service가 해당 robot_id의 활성 세션을 자동으로 종료 처리 |
| 4 | **OFFLINE current_mode** | "OFFLINE" 문자열이 SM 상태값과 같은 컬럼 사용 | 데모 간소화를 위해 "OFFLINE" 문자열 혼용 허용 |
| 5 | **`_offline_robots` 초기화** | control_service 시작 시 DB에 이미 `current_mode='OFFLINE'`인 로봇이 있을 수 있음 | 초기화 시 `SELECT robot_id FROM robot WHERE current_mode='OFFLINE'`으로 `_offline_robots` 프리로드 |

---

## 기대 결과

| 상황 | admin_ui | ROBOT 테이블 |
|---|---|---|
| Pi 정상 기동 중 | 로봇 카드 정상, 위치 갱신 | current_mode=Pi모드, last_seen 갱신 |
| 30s 이상 미수신 | 로봇 카드 회색 + "오프라인" | current_mode="OFFLINE", active_user_id=NULL |
| Pi 재기동 후 status 재수신 | 로봇 카드 정상 복구 | current_mode=IDLE, last_seen 갱신 |
| offline 중 신규 로그인 시도 | — | `current_mode == "OFFLINE"`이면 `session_check` 시 `{"status": "offline"}` 반환 → blocked.html |

---

## UI 검토

| 요소 | 내용 |
|---|---|
| 오프라인 카드 스타일 | 전체 회색 배경, 텍스트 반투명. "오프라인" 뱃지 (회색 pill) |
| 맵 오버레이 오프라인 | 로봇 아이콘 위에 × 또는 빨간 선 겹침. 마지막 알려진 위치에 유지 |
| 재연결 복구 | 즉시 정상 색상 복구. 별도 알림 없음 (카드 갱신으로 충분) |

---

## 검증 방법

```bash
# [방법 A] last_seen 수동 조작 (DB 직접)
sqlite3 src/control_center/control_service/data/control.db \
  "UPDATE robot SET last_seen='2020-01-01 00:00:00' WHERE robot_id=54;"
# → 다음 cleanup 주기(10s)에서 offline 감지 확인

# ROBOT 테이블 상태 확인
sqlite3 src/control_center/control_service/data/control.db \
  "SELECT robot_id, current_mode, active_user_id, last_seen FROM robot;"
# → current_mode='OFFLINE', active_user_id=NULL 확인

# 재연결 시뮬레이션
ros2 topic pub --once /robot_54/status std_msgs/String \
  '{"data": "{\"mode\": \"IDLE\", \"pos_x\": 0.0, \"pos_y\": 0.0, \"battery\": 80}"}'
# → admin_ui 카드 정상 복구 확인
```
