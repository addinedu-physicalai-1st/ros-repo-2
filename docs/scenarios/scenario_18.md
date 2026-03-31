# 시나리오 18: 로봇 복귀 대기열

**SM 전환:** RETURNING → IDLE (기존), IDLE 유지 (대기열 전진 — Nav2 직접)
**모드:** ARUCO 전용 (Nav2 필요)
**관련 패키지:** shoppinkki_core, shoppinkki_nav, control_service, admin_app

---

## 개요

로봇이 복귀(RETURNING) 완료 후 카트 출구 구역(ID 140)에서 사용자를 기다린다.
두 로봇이 동시에 복귀할 경우, 한 로봇이 ID 140 (1번 위치)에, 다른 로봇은
ID 141 (2번 위치 — ID 140 바로 뒤)에 대기한다.
1번 위치 로봇이 새 세션을 시작(REGISTERING)하면 2번 로봇이 1번 위치로 전진한다.

---

## 기능 체크리스트

| 완료 | 기능 |
|:---:|---|
| [ ] | `ZONE` 테이블에 ID 141 (대기열 2번 위치) 추가 |
| [ ] | control_service: `QueueManager` — in-memory 대기열 관리 |
| [ ] | BTReturning: 출발 전 `GET /queue/assign?robot_id=<id>` 호출 → 배정 zone_id 수신 |
| [ ] | BTReturning: 배정된 zone_id(140 또는 141)로 Nav2 이동 |
| [ ] | 도착 후 `sm.trigger('session_ended')` → IDLE (기존 동작 유지) |
| [ ] | control_service: `QueueManager.robot_arrived(robot_id)` — 대기열 등록 |
| [ ] | control_service: `/robot_<id>/status` mode=`REGISTERING` 수신 → `QueueManager.robot_left(robot_id)` |
| [ ] | QueueManager: 1번 로봇 이탈 → 2번 로봇에게 `admin_goto` (zone 140 좌표) 전송 |
| [ ] | Pi: `admin_goto` cmd 수신 → (IDLE 확인 후) Nav2 goal 전송 (scenario_15 구현 재사용) |
| [ ] | admin_app: 대기열 상태 표시 (1번/2번 위치에 어떤 로봇이 있는지) |
| [ ] | 대기열 전진 시 EVENT_LOG에 `QUEUE_ADVANCE` 기록 (scenario_17 연계) |

---

## 전제조건

- ARUCO 모드, Nav2 스택 동작 중
- 두 로봇(#54, #18) 모두 RETURNING 상태 또는 한 로봇이 이미 ID 140에서 대기 중
- `ZONE` 테이블: ID 140 (카트 출구 1번), ID 141 (카트 출구 2번) Waypoint 설정됨

---

## 신규 구역 정의

| ID | 구역명 | 설명 | 비고 |
|---|---|---|---|
| 140 | 카트 출구 (1번 위치) | 대기열 맨 앞. 사용자 QR 스캔 위치. 기존 RETURNING 목적지 | 기존 |
| 141 | 카트 출구 (2번 위치) | ID 140 바로 뒤. 대기 중 2번째 로봇 위치 | **신규** |

> 3대 이상 확장 시: ID 142, 143 등으로 연장. 데모는 2대이므로 141까지만 정의.

---

## 흐름

```
────── 대기열 배정 (BTReturning 진입 시) ──────

BTReturning 시작 (on_enter_RETURNING → bt_runner.start())
    → REST GET /queue/assign?robot_id=54
    ↓
control_service: QueueManager.assign(robot_id=54)
    → queue = [] → 54를 position 0에 배정 → zone_id = 140
    → queue = [54]
    ↓
BTReturning: zone_id=140 → Waypoint 조회 → Nav2 이동
    ↓
도착 → sm.trigger('session_ended') → IDLE
    → control_service: QueueManager.robot_arrived(54)


────── 두 번째 로봇 복귀 시 ──────

BTReturning 시작 (robot_id=18)
    → REST GET /queue/assign?robot_id=18
    ↓
control_service: QueueManager.assign(robot_id=18)
    → queue = [54] → 18을 position 1에 배정 → zone_id = 141
    → queue = [54, 18]
    ↓
BTReturning: zone_id=141 → Waypoint 조회 → Nav2 이동
    ↓
도착 → sm.trigger('session_ended') → IDLE
    → control_service: QueueManager.robot_arrived(18)


────── 대기열 전진 (1번 로봇이 새 세션 시작) ──────

Robot #54: QR 스캔 → 로그인 → start_session 발행 → SM: IDLE → REGISTERING
    ↓
control_service: /robot_54/status 수신 (mode=REGISTERING)
    → QueueManager.robot_left(robot_id=54)
        → queue = [54, 18] → 54 제거 → queue = [18]
        → 18에게 전진 명령: admin_goto(robot_id=18, zone_id=140)
    ↓
admin_goto: /robot_18/cmd: {"cmd": "admin_goto", "x": 140의 Waypoint x, "y": 140의 Waypoint y}
    ↓
Pi #18: on_cmd admin_goto → Nav2 goal 전송 (IDLE 상태 유지)
    → 이동 완료 → publish_status(mode="IDLE", pos=zone140 좌표)
    ↓
QueueManager: robot_18이 zone 140 도착 감지 (position 갱신)
    → EVENT_LOG: QUEUE_ADVANCE {"robot_id": 18, "from_pos": 1, "to_pos": 0}
```

### 대기열 상태 전이

```
초기         robot_54 복귀      robot_18 복귀     robot_54 출발 → 18 전진
──────────   ───────────────   ───────────────   ──────────────────────────
[]           [54]              [54, 18]          [18]
             (zone 140)         (54=140, 18=141)  (18=140)
```

---

## 예제 코드 및 모순 점검

### control_service: QueueManager

```python
# control_service/queue_manager.py
import threading
from dataclasses import dataclass, field
from typing import Optional

QUEUE_ZONES = [140, 141]  # position 0=front, 1=behind

@dataclass
class QueueManager:
    control_service: object              # ControlServiceNode 참조
    queue: list[int] = field(default_factory=list)  # [robot_id, ...] front to back
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def assign(self, robot_id: int) -> int:
        """BTReturning 시작 시 호출. 배정된 zone_id 반환."""
        with self._lock:
            if robot_id in self.queue:
                # 이미 등록됨 (중복 호출) → 현재 position의 zone_id 반환
                pos = self.queue.index(robot_id)
            else:
                pos = len(self.queue)
                if pos >= len(QUEUE_ZONES):
                    # ⚠️ 모순 #1: 로봇이 2대를 초과하는 경우 zone_id 없음
                    # 데모에서는 2대 고정이므로 발생하지 않아야 함
                    raise ValueError(f"Queue full: max {len(QUEUE_ZONES)} robots")
                self.queue.append(robot_id)

            zone_id = QUEUE_ZONES[pos]
            return zone_id

    def robot_arrived(self, robot_id: int):
        """BTReturning 도착 확인 (session_ended 발생 시)."""
        # 도착 확인은 현재 별도 처리 없음. queue는 assign에서 이미 관리됨.
        pass

    def robot_left(self, robot_id: int):
        """로봇이 새 세션 시작(REGISTERING)으로 1번 위치를 떠날 때."""
        with self._lock:
            if robot_id not in self.queue:
                return

            left_pos = self.queue.index(robot_id)
            if left_pos != 0:
                # ⚠️ 모순 #2: 1번 아닌 위치 로봇이 세션 시작 가능
                # 예: 2번 로봇이 사용자 QR 스캔 → 세션 시작됨
                # 2번 위치에서 세션 시작 자체는 막을 수 없음 (Pi 측에서 QR 스캔 허용)
                # → 2번 로봇 이탈 시 단순 제거만 수행
                self.queue.pop(left_pos)
                return

            # 1번 로봇 이탈 → 나머지 전진
            self.queue.pop(0)

            # 2번 로봇(이제 position 0이 되어야 함) 전진 명령
            if self.queue:
                next_robot_id = self.queue[0]
                next_zone_id = QUEUE_ZONES[0]  # zone 140

                # zone 140 Waypoint 조회
                waypoint = self.control_service.db.execute(
                    "SELECT waypoint_x, waypoint_y, waypoint_theta FROM zone WHERE zone_id=?",
                    (next_zone_id,)
                ).fetchone()

                if waypoint:
                    self.control_service.admin_goto(
                        next_robot_id, waypoint[0], waypoint[1], waypoint[2]
                    )
                    self.control_service.log_event(
                        'QUEUE_ADVANCE', robot_id=next_robot_id,
                        detail={'from_pos': 1, 'to_pos': 0}
                    )
```

### BTReturning: queue/assign 연동

```python
# shoppinkki_nav/bt_returning.py
import requests

class BTReturning(NavBTInterface):
    def __init__(self, control_service_url: str, robot_id: int):
        self._url = control_service_url  # e.g. "http://localhost:8080"
        self._robot_id = robot_id
        self._zone_id = None  # assign 후 결정

    def start(self, **kwargs):
        # ① 대기열 position 배정
        try:
            resp = requests.get(
                f"{self._url}/queue/assign",
                params={'robot_id': self._robot_id},
                timeout=3.0
            )
            self._zone_id = resp.json()['zone_id']
        except Exception as e:
            # ⚠️ 모순 #3: /queue/assign 실패 시 fallback 필요
            # 서버 미응답 시 기본값 zone 140으로 폴백
            self._zone_id = 140

    def tick(self) -> str:
        if self._zone_id is None:
            return "FAILURE"

        # ② zone_id로 Waypoint 조회 (기존 BT4/BT5 방식 동일)
        try:
            resp = requests.get(
                f"{self._url}/zone/{self._zone_id}/waypoint",
                timeout=3.0
            )
            wp = resp.json()
        except Exception:
            return "FAILURE"

        # ③ Nav2 goal 전송 (생략 — 기존 BTReturning 로직 재사용)
        ...
        return "RUNNING"
```

### control_service: /queue/assign REST 엔드포인트

```python
# control_service/rest_server.py (또는 main_node.py의 Flask 통합)
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/queue/assign')
def queue_assign():
    robot_id = int(request.args.get('robot_id'))
    try:
        zone_id = queue_manager.assign(robot_id)
        return jsonify({'zone_id': zone_id})
    except ValueError as e:
        return jsonify({'error': str(e)}), 409  # Conflict: queue full
```

### admin_app: 대기열 상태 표시

```python
# admin_app/main_window.py
class AdminMainWindow(QMainWindow):
    queue_update_signal = pyqtSignal(list)  # [robot_id | None, robot_id | None]

    def _update_queue_display(self, queue: list[int]):
        """queue = [front_robot_id, behind_robot_id] (없으면 None)"""
        for i, slot_label in enumerate(self.queue_slots):
            robot_id = queue[i] if i < len(queue) else None
            if robot_id:
                slot_label.setText(f"Robot #{robot_id}")
                slot_label.setStyleSheet("background: #cce5ff; border: 2px solid #004085;")
            else:
                slot_label.setText("비어있음")
                slot_label.setStyleSheet("background: #f8f9fa; border: 1px dashed gray;")
```

### 모순 및 검토 사항

| # | 항목 | 내용 | 처리 |
|---|---|---|---|
| 1 | **2대 초과 시 zone 없음** | QUEUE_ZONES = [140, 141]로 2대 고정. 3대 이상이면 ValueError | 데모 2대 고정이므로 허용. 경고 로그 + fallback(가장 뒤 zone 재사용) 옵션 |
| 2 | **2번 위치 로봇 세션 시작** | 2번 로봇(zone 141)이 사용자 QR 스캔으로 먼저 세션 시작 가능 (Pi는 IDLE이므로 QR 허용) | 2번 이탈 시 단순 queue 제거. 1번(zone 140)은 그대로. 데모 운용상 안내 필요 |
| 3 | **/queue/assign 실패 fallback** | 서버 미응답 시 BTReturning이 zone_id를 모름 | zone 140으로 폴백. 두 로봇이 동시에 zone 140으로 이동하면 Nav2 충돌 가능 → Pi에서 도착 확인 후 자리 여부 체크 (추가 구현 필요) |
| 4 | **REGISTERING 감지 타이밍** | control_service는 `/robot_<id>/status` (1~2Hz)로 mode 변화를 감지. 최대 1~2초 지연 후 queue_advance | 데모 용도로 허용. 즉시 감지가 필요하면 별도 `{"event": "session_started"}` 토픽 추가 고려 |
| 5 | **robot_arrived 미구현** | QueueManager.robot_arrived()는 현재 pass — 도착 확인을 별도로 하지 않음 | assign에서 이미 position 배정. arrived는 선택적 logging 용도로만 사용 가능 |
| 6 | **BTReturning이 REST 의존** | BTReturning이 control_service REST에 HTTP 요청함. 서버 PC 네트워크 필요 | Pi ↔ 서버 PC 동일 서브넷 전제. 기존 BT4/BT5의 waypoint 조회 REST와 동일 채널 (채널 E) |
| 7 | **대기열 전진 중 충돌** | admin_goto로 18번이 zone 140으로 이동하는 중에 54번도 아직 zone 140 부근에 있을 수 있음 | 54번이 REGISTERING 후 TRACKING으로 전환되면 즉시 이동 시작. zone 140은 카트 출구이므로 54번은 곧 마트 안으로 이동. 데모 맵 크기(180×140cm)에서 물리적 충돌 가능성 낮음. 필요 시 전진 명령을 2~3초 지연 |

---

## 기대 결과

| 상황 | 결과 |
|---|---|
| 로봇 1대 복귀 | zone 140에 도착, IDLE 대기 |
| 로봇 2대 동시 복귀 | 먼저 요청한 로봇이 zone 140, 나중이 zone 141 |
| 1번 로봇 세션 시작 | 2번 로봇에게 admin_goto zone 140 전송, QUEUE_ADVANCE 이벤트 기록 |
| 2번만 남은 상태 | 2번 로봇이 zone 140에 도착, IDLE 대기 |

---

## UI 검토

| 요소 | 내용 |
|---|---|
| 대기열 패널 위치 | admin_app 하단 또는 맵 오버레이 내 카트 출구 근처 |
| 슬롯 표시 | `[1번 위치: Robot#54]` `[2번 위치: Robot#18]` — 비어있으면 점선 박스 |
| 대기열 전진 애니메이션 | 2번 슬롯이 1번으로 이동하는 짧은 애니메이션 (QPropertyAnimation) |
| 맵 오버레이 연계 | 대기열 로봇은 맵에서 zone 140/141 위치에 표시됨 (scenario_13 UI와 동일 아이콘) |
| 전진 알림 | 이벤트 로그 패널에 QUEUE_ADVANCE 행 표시 (scenario_17 연계) |

---

## 검증 방법

```bash
# 두 로봇 RETURNING 시뮬레이션
# Robot #54: assign → zone 140 배정 확인
curl "http://localhost:8080/queue/assign?robot_id=54"
# → {"zone_id": 140}

# Robot #18: assign → zone 141 배정 확인
curl "http://localhost:8080/queue/assign?robot_id=18"
# → {"zone_id": 141}

# Robot #54 REGISTERING 시뮬레이션 (대기열 이탈)
ros2 topic pub --once /robot_54/cmd std_msgs/String \
  '{"data": "{\"cmd\": \"start_session\", \"user_id\": \"test\"}"}'

# Robot #18 admin_goto zone 140 명령 수신 확인
ros2 topic echo /robot_18/cmd   # → {"cmd": "admin_goto", "x": ..., "y": ...}

# QUEUE_ADVANCE 이벤트 확인
sqlite3 src/control_center/control_service/data/control.db \
  "SELECT * FROM event_log WHERE event_type='QUEUE_ADVANCE' ORDER BY occurred_at DESC LIMIT 3;"
```
