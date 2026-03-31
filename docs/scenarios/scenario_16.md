# 시나리오 16: 관제 — 로봇 Offline 감지

**SM 전환:** 없음 (control_service 측 감지)
**모드:** PERSON/ARUCO 공통
**관련 패키지:** admin_app, control_service

---

## 개요

로봇이 재시작되거나 네트워크 연결이 끊기면 `/robot_<id>/status` 토픽 발행이 중단된다.
control_service의 cleanup 스레드가 `last_seen` 기준 `ROBOT_TIMEOUT_SEC(30s)` 초과를 감지하고
`active_user_id = NULL` 처리 및 admin_app에 offline 상태를 전달한다.
로봇이 재연결되면 자동으로 online 복귀 처리한다.

---

## 기능 체크리스트

| 완료 | 기능 |
|:---:|---|
| [ ] | control_service: cleanup 스레드 (10s 주기) 실행 |
| [ ] | cleanup 스레드: `last_seen < now - ROBOT_TIMEOUT_SEC(30s)` → offline 감지 |
| [ ] | offline 시: `ROBOT.active_user_id = NULL` 갱신 |
| [ ] | offline 시: `ROBOT.current_mode = "OFFLINE"` 갱신 |
| [ ] | admin_app에 offline 이벤트 전달 (채널 D) |
| [ ] | admin_app: 해당 로봇 카드 회색 처리 + "오프라인" 뱃지 표시 |
| [ ] | admin_app: 맵 오버레이 로봇 아이콘 × 표시 (마지막 알려진 위치 유지) |
| [ ] | 재연결 시: `/robot_<id>/status` 재수신 → `last_seen` 갱신 → online 복귀 |
| [ ] | admin_app: 로봇 카드 정상 상태로 복구 (회색 해제, 뱃지 제거) |
| [ ] | 로봇이 offline 중 세션 있었으면: 재연결 후 Pi SM 상태 확인 필요 (IDLE 복귀 여부) |

---

## 전제조건

- admin_app + control_service 기동 중
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
    → admin_app.on_robot_offline(robot_id) 직접 호출 (채널 D)
    ↓
admin_app:
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
    → admin_app.on_robot_status_update(robot_id, ...) 호출
    ↓
admin_app:
    → 로봇 카드 정상 표시 복구 (회색 해제, 뱃지 제거)
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
    def __init__(self, admin_app=None):
        super().__init__('control_service')
        self.admin_app = admin_app
        self._offline_robots: set[int] = set()  # 현재 offline 상태 robot_id 집합

        # cleanup 스레드 시작
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop, daemon=True
        )
        self._cleanup_thread.start()

    def _cleanup_loop(self):
        while rclpy.ok():
            threading.Event().wait(CLEANUP_INTERVAL_SEC)
            self._run_cleanup()

    def _run_cleanup(self):
        threshold = (datetime.now() - timedelta(seconds=ROBOT_TIMEOUT_SEC)).isoformat()
        rows = self.db.execute(
            "SELECT robot_id, current_mode FROM robot WHERE last_seen < ?",
            (threshold,)
        ).fetchall()

        for robot_id, current_mode in rows:
            if current_mode == "OFFLINE":
                continue  # 이미 offline 처리됨

            self.get_logger().warn(f"Robot {robot_id} offline (last_seen < {threshold})")
            self.db.execute("""
                UPDATE robot SET current_mode='OFFLINE', active_user_id=NULL
                WHERE robot_id=?
            """, (robot_id,))
            self._offline_robots.add(robot_id)

            # Channel D: admin_app 갱신 (Signal 필수 — thread safety)
            if self.admin_app:
                self.admin_app.on_robot_offline(robot_id)

    def _on_status(self, robot_id: int, msg):
        data = json.loads(msg.data)
        now = datetime.now().isoformat()
        was_offline = robot_id in self._offline_robots

        self.db.execute("""
            UPDATE robot
            SET current_mode=?, pos_x=?, pos_y=?, battery_level=?, last_seen=?,
                active_user_id=CASE WHEN current_mode='OFFLINE' THEN NULL ELSE active_user_id END
            WHERE robot_id=?
        """, (data['mode'], data['pos_x'], data['pos_y'], data['battery'], now, robot_id))

        if was_offline:
            self._offline_robots.discard(robot_id)
            if self.admin_app:
                self.admin_app.on_robot_online(robot_id)

        if self.admin_app:
            self.admin_app.on_robot_status_update(robot_id, {
                'mode': data['mode'],
                'pos_x': data['pos_x'], 'pos_y': data['pos_y'],
                'battery': data['battery'], 'last_seen': now
            })
```

### admin_app: Offline/Online Signal 처리

```python
# admin_app/main_window.py
class AdminMainWindow(QMainWindow):
    robot_offline_signal = pyqtSignal(int)   # (robot_id,)
    robot_online_signal = pyqtSignal(int)    # (robot_id,)

    def __init__(self, control_service):
        super().__init__()
        self.robot_offline_signal.connect(self._show_offline)
        self.robot_online_signal.connect(self._show_online)

    def on_robot_offline(self, robot_id: int):
        # cleanup 스레드 → Qt 메인 스레드
        self.robot_offline_signal.emit(robot_id)

    def on_robot_online(self, robot_id: int):
        # ROS 스레드 → Qt 메인 스레드
        self.robot_online_signal.emit(robot_id)

    def _show_offline(self, robot_id: int):
        card = self.robot_cards[robot_id]
        card.setStyleSheet("background-color: #888; color: #555;")  # 전체 회색
        card.status_badge.setText("오프라인")
        card.status_badge.setStyleSheet("background: gray;")
        # 맵 오버레이: × 아이콘으로 교체 (마지막 위치 유지)
        self.map_widget.set_robot_offline(robot_id)

    def _show_online(self, robot_id: int):
        card = self.robot_cards[robot_id]
        card.setStyleSheet("")  # 회색 해제
        card.status_badge.setText("온라인")
        self.map_widget.set_robot_online(robot_id)
```

### 모순 및 검토 사항

| # | 항목 | 내용 | 처리 |
|---|---|---|---|
| 1 | **cleanup 스레드 sleep 방식** | `threading.Event().wait()` 매번 새 Event 생성 → 종료 신호 없음 | `self._stop_event = threading.Event()` 사용: `stop_event.wait(timeout=10)`, 종료 시 `stop_event.set()` |
| 2 | **DB 동시 접근** | cleanup 스레드 + ROS 콜백 스레드가 동시에 DB 갱신 — SQLite는 기본 `check_same_thread=True` | `connect(check_same_thread=False)` + `threading.Lock()` 으로 보호 필요 |
| 3 | **재연결 시 active_user_id** | Pi 재기동 시 SM은 IDLE이지만, 재기동 전 세션이 있었다면 Pi DB에 is_active=True 세션이 남아있을 수 있음 | Pi 기동 시 `terminate_all_sessions()` 호출로 이전 세션 정리 필요 (초기화 루틴) |
| 4 | **OFFLINE current_mode 예외** | ROBOT.current_mode에 "OFFLINE" 문자열 삽입. 이 값이 IDLE/TRACKING 등 SM 상태값과 다른 범주인데 같은 컬럼 사용 | 별도 `is_online` BOOL 컬럼 추가가 더 깔끔하나, 데모 간소화를 위해 "OFFLINE" 문자열 혼용 허용 |
| 5 | **`_offline_robots` 집합 초기화** | control_service 시작 시 DB에 이미 `current_mode='OFFLINE'`인 로봇이 있을 수 있음 | 초기화 시 `SELECT robot_id FROM robot WHERE current_mode='OFFLINE'`으로 `_offline_robots` 프리로드 |
| 6 | **admin_app 미연결 시** | `if self.admin_app:` 체크로 None 처리는 되지만, admin_app 없이도 DB 갱신은 진행 | 현재 설계 유지 (admin_app은 선택적 UI 레이어) |

---

## 기대 결과

| 상황 | admin_app | ROBOT 테이블 |
|---|---|---|
| Pi 정상 기동 중 | 로봇 카드 정상, 위치 갱신 | current_mode=Pi모드, last_seen 갱신 |
| 30s 이상 미수신 | 로봇 카드 회색 + "오프라인" | current_mode="OFFLINE", active_user_id=NULL |
| Pi 재기동 후 status 재수신 | 로봇 카드 정상 복구 | current_mode=IDLE, last_seen 갱신 |
| offline 중 신규 로그인 시도 | — | active_user_id=NULL이므로 로그인 가능하나 Pi가 응답 없음 |

> **주의:** offline 중 로그인은 control_service 측에서는 허용되나,
> Pi가 `/robot_<id>/cmd: start_session`을 수신 못 함 → 실질적으로 로봇이 응답하지 않음.
> 추가 방어: `session_check` 시 `current_mode == "OFFLINE"`이면 `{"status": "offline"}` 반환 → blocked.html 표시.

---

## UI 검토

| 요소 | 내용 |
|---|---|
| 오프라인 카드 스타일 | 전체 회색 배경, 텍스트 반투명. "오프라인" 뱃지 (회색 pill) |
| 맵 오버레이 오프라인 | 로봇 아이콘 위에 × 또는 빨간 선 겹침. 마지막 알려진 위치에 유지 |
| 재연결 복구 | 즉시 정상 색상 복구. 별도 알림 없음 (카드 갱신으로 충분) |
| 오프라인 지속 알림 | 30초 초과 후에도 계속 offline이면 알림음 또는 팝업 (선택적, 데모 목적) |
| 세션 있었던 로봇 offline | "오프라인 (세션 있음)" 뱃지로 구분 가능 — `active_user_id` NULL 처리 전 상태 구분용 |

---

## 검증 방법

```bash
# [방법 A] 직접 status 발행 중단
# Pi 재시작: ssh pi54 "sudo systemctl restart shoppinkki_core"
# → 30s 후 admin_app에서 로봇 카드 회색 처리 확인

# [방법 B] last_seen 수동 조작 (DB 직접)
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
# → admin_app 카드 정상 복구 확인
```
