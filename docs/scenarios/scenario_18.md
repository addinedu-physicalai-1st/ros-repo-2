# 시나리오 18: 로봇 복귀 대기열 (2대 동시)

**SM 전환:** `RETURNING → TOWARD_STANDBY_X → STANDBY_X → IDLE` (복귀) / `STANDBY_X → TOWARD_STANDBY_(X-1)` (대기열 전진)
**관련 패키지:** shoppinkki_core, shoppinkki_nav, control_service, admin_ui

---

## 개요

두 로봇이 동시에 복귀(RETURNING)할 경우 QueueManager가 대기열 위치(zone 140/141/142)를 배정한다.
1번 위치 로봇이 새 세션을 시작(REGISTERING)하면 QueueManager가 뒤에 있는 로봇에게 `queue_advance` 명령을 전송하고,
로봇은 앞 대기열 위치로 이동한다. 데모는 2대(최대 2번 위치까지)를 전제로 한다.

---

## 기능 체크리스트

| 완료 | 기능 |
|:---:|---|
| [ ] | `ZONE` 테이블: ID 140 (STANDBY_1), 141 (STANDBY_2), 142 (STANDBY_3) Waypoint 설정 |
| [ ] | control_service: `QueueManager` — in-memory 대기열 관리 |
| [ ] | BTReturning: 출발 전 `GET /queue/assign?robot_id=<id>` 호출 → 배정 zone_id 수신 |
| [ ] | BTReturning: `sm.trigger('to_toward_standby_X')` → TOWARD_STANDBY_X |
| [ ] | BTReturning: `GET /zone/<zone_id>/waypoint` → Nav2 이동 |
| [ ] | Nav2 SUCCEEDED → `sm.trigger('standby_arrived')` → STANDBY_X |
| [ ] | control_service: `QueueManager.robot_arrived(robot_id, zone_id)` — 대기열 등록 |
| [ ] | control_service: `/robot_<id>/status` mode=`REGISTERING` 수신 → `QueueManager.robot_left(robot_id)` |
| [ ] | QueueManager: 앞 위치 비워지면 뒤 로봇에게 `queue_advance` cmd 전송: `/robot_<id>/cmd: {"cmd": "queue_advance"}` |
| [ ] | Pi: `queue_advance` cmd 수신 → STANDBY_X 상태에서 `sm.trigger('queue_advance')` → TOWARD_STANDBY_(X-1) |
| [ ] | TOWARD_STANDBY_(X-1): BT가 앞 대기열 Waypoint로 Nav2 이동 → `standby_arrived` → STANDBY_(X-1) |
| [ ] | admin_ui: 대기열 상태 표시 (1번/2번 위치에 어떤 로봇이 있는지) |
| [ ] | 대기열 전진 시 EVENT_LOG에 `QUEUE_ADVANCE` 기록 (scenario_17 연계) |

---

## 전제조건

- 두 로봇(#54, #18) 모두 RETURNING 상태 또는 한 로봇이 이미 STANDBY에서 대기 중
- `ZONE` 테이블: ID 140 (STANDBY_1), 141 (STANDBY_2) Waypoint 설정됨
- Nav2 스택 동작 중

---

## 대기열 구역 정의

| ID | 구역명 | 설명 |
|---|---|---|
| 140 | STANDBY_1 (대기열 1번) | 대기열 맨 앞. 사용자 QR 스캔 위치 |
| 141 | STANDBY_2 (대기열 2번) | 1번 바로 뒤. 대기 중 2번째 로봇 위치 |
| 142 | STANDBY_3 (대기열 3번) | 2번 바로 뒤. 3대 확장 시 사용 (데모 미사용) |

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
BTReturning:
    → zone_id=140 → sm.trigger('to_toward_standby_1') → TOWARD_STANDBY_1
    → GET /zone/140/waypoint → Nav2 이동
    → Nav2 SUCCEEDED → sm.trigger('standby_arrived') → STANDBY_1
    → control_service: QueueManager.robot_arrived(54, 140)


────── 두 번째 로봇 복귀 시 ──────

BTReturning 시작 (robot_id=18)
    → REST GET /queue/assign?robot_id=18
    ↓
control_service: QueueManager.assign(robot_id=18)
    → queue = [54] → 18을 position 1에 배정 → zone_id = 141
    → queue = [54, 18]
    ↓
BTReturning:
    → zone_id=141 → sm.trigger('to_toward_standby_2') → TOWARD_STANDBY_2
    → GET /zone/141/waypoint → Nav2 이동
    → Nav2 SUCCEEDED → sm.trigger('standby_arrived') → STANDBY_2
    → control_service: QueueManager.robot_arrived(18, 141)


────── 대기열 전진 (1번 로봇이 새 세션 시작) ──────

Robot #54: QR 스캔 → 로그인 → start_session 발행 → SM: STANDBY_1 → IDLE → REGISTERING
    ↓
control_service: /robot_54/status 수신 (mode=REGISTERING)
    → QueueManager.robot_left(robot_id=54)
        → queue = [54, 18] → 54 제거 → queue = [18]
        → 18에게 전진 명령:
          /robot_18/cmd: {"cmd": "queue_advance"}
    ↓
Pi #18: on_cmd("queue_advance")
    → STANDBY_2 상태에서 sm.trigger('queue_advance') → TOWARD_STANDBY_1
    → BTReturning (또는 전용 BT): GET /zone/140/waypoint → Nav2 이동
    → Nav2 SUCCEEDED → sm.trigger('standby_arrived') → STANDBY_1
    ↓
EVENT_LOG: QUEUE_ADVANCE {"robot_id": 18, "from_zone": 141, "to_zone": 140}
```

### 대기열 상태 전이

```
초기         robot_54 복귀         robot_18 복귀         robot_54 출발 → 18 전진
──────────   ──────────────────   ──────────────────   ──────────────────────────
[]           [54]                 [54, 18]             [18]
             (STANDBY_1, z140)   (54=z140, 18=z141)   (STANDBY_1, z140)
```

---

## 예제 코드 및 모순 점검

### control_service: QueueManager

```python
# control_service/queue_manager.py
import threading
from dataclasses import dataclass, field

QUEUE_ZONES = [140, 141, 142]  # position 0=front, 1=middle, 2=back (데모: 2대 → 141까지 사용)

@dataclass
class QueueManager:
    control_service: object
    queue: list[int] = field(default_factory=list)  # [robot_id, ...] front to back
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def assign(self, robot_id: int) -> int:
        """BTReturning 시작 시 호출. 배정된 zone_id 반환."""
        with self._lock:
            if robot_id in self.queue:
                pos = self.queue.index(robot_id)
            else:
                pos = len(self.queue)
                if pos >= len(QUEUE_ZONES):
                    raise ValueError(f"Queue full: max {len(QUEUE_ZONES)} robots")
                self.queue.append(robot_id)
            return QUEUE_ZONES[pos]

    def robot_arrived(self, robot_id: int, zone_id: int):
        """STANDBY_X 도착 확인. 현재는 logging 용도."""
        pass

    def robot_left(self, robot_id: int):
        """로봇이 REGISTERING으로 1번 위치를 떠날 때."""
        with self._lock:
            if robot_id not in self.queue:
                return

            left_pos = self.queue.index(robot_id)
            self.queue.pop(left_pos)

            if left_pos != 0:
                # 1번이 아닌 위치에서 이탈 → 단순 제거, 전진 없음
                return

            # 1번 로봇 이탈 → 남은 로봇들이 한 칸씩 전진
            for next_robot_id in self.queue:
                # 각 로봇에게 queue_advance 명령 전송
                self.control_service._ros_publish(
                    next_robot_id, json.dumps({"cmd": "queue_advance"})
                )
                self.control_service.log_event(
                    'QUEUE_ADVANCE', robot_id=next_robot_id,
                    detail={'from_zone': QUEUE_ZONES[self.queue.index(next_robot_id) + 1],
                            'to_zone': QUEUE_ZONES[self.queue.index(next_robot_id)]}
                )
```

### Pi: queue_advance cmd 처리

```python
# shoppinkki_core/main_node.py
def on_cmd(self, msg):
    data = json.loads(msg.data)
    if data.get('cmd') == 'queue_advance':
        # STANDBY_X 상태에서만 처리
        if self.sm.state.startswith('STANDBY_'):
            self.sm.trigger('queue_advance')
            # BTReturning이 현재 위치보다 앞 zone_id로 이동

# SM 전환 정의 (transitions 라이브러리)
# STANDBY_2 → TOWARD_STANDBY_1 (queue_advance 트리거)
# STANDBY_3 → TOWARD_STANDBY_2 (queue_advance 트리거)
# TOWARD_STANDBY_(X-1) → STANDBY_(X-1) (standby_arrived 트리거)
```

### BTReturning: queue_advance 시 zone 결정

```python
# shoppinkki_nav/bt_returning.py
def on_queue_advance(self):
    """queue_advance 수신 시 현재 zone에서 한 칸 앞 zone으로 이동"""
    # zone_id를 현재 STANDBY_X 상태에서 추론
    current_state = self.sm.state  # "STANDBY_2" → position=1 → zone=141
    # STANDBY_X → position X-1 → QUEUE_ZONES[X-2]가 앞 위치
    self._zone_id = QUEUE_ZONES[QUEUE_ZONES.index(self._zone_id) - 1]
    self._nav2_send_goal()
```

### control_service: /queue/assign REST 엔드포인트

```python
@app.route('/queue/assign')
def queue_assign():
    robot_id = int(request.args.get('robot_id'))
    try:
        zone_id = queue_manager.assign(robot_id)
        return jsonify({'zone_id': zone_id})
    except ValueError as e:
        return jsonify({'error': str(e)}), 409  # Conflict: queue full
```

### admin_ui: 대기열 상태 표시

```python
# admin_ui/main_window.py
class AdminMainWindow(QMainWindow):
    queue_update_signal = pyqtSignal(list)  # [robot_id | None, ...]

    def _on_tcp_message(self, msg: dict):
        if msg.get('type') == 'queue_update':
            self.queue_update_signal.emit(msg['queue'])

    def _update_queue_display(self, queue: list[int]):
        for i, slot_label in enumerate(self.queue_slots):  # 슬롯: 1번, 2번
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
| 1 | **queue_advance와 SM 상태** | queue_advance는 STANDBY_X 상태에서만 의미 있음. TOWARD_STANDBY 중에 수신 시 무시 필요 | Pi: `sm.state.startswith('STANDBY_')` 확인 후 처리 |
| 2 | **2번 위치 로봇 세션 시작** | 2번 로봇(zone 141)이 사용자 QR 스캔으로 먼저 세션 시작 가능 | 2번 이탈 시 단순 queue 제거. 1번(zone 140)은 그대로. 데모 운용상 안내 필요 |
| 3 | **/queue/assign 실패 fallback** | 서버 미응답 시 BTReturning이 zone_id를 모름 | zone 140으로 폴백. 두 로봇 동시 이동 시 Nav2 충돌 주의 |
| 4 | **REGISTERING 감지 타이밍** | control_service는 1~2Hz status로 mode 변화를 감지. 최대 1~2초 지연 후 queue_advance | 데모 용도로 허용 |
| 5 | **robot_arrived 미구현** | 도착 확인 logging은 선택적. assign에서 이미 position 배정됨 | 필요 시 logging 추가 |

---

## 기대 결과

| 상황 | 결과 |
|---|---|
| 로봇 1대 복귀 | zone 140(STANDBY_1) 도착, IDLE 대기 |
| 로봇 2대 동시 복귀 | 먼저 요청한 로봇이 zone 140, 나중이 zone 141 |
| 1번 로봇 세션 시작 | 2번 로봇에게 queue_advance 전송 → STANDBY_2→TOWARD_STANDBY_1→STANDBY_1 |
| 2번만 남은 상태 | 2번 로봇이 zone 140(STANDBY_1)에 도착, IDLE 대기 |

---

## UI 검토

| 요소 | 내용 |
|---|---|
| 대기열 패널 위치 | admin_ui 하단 또는 맵 오버레이 내 카트 출구 근처 |
| 슬롯 표시 | `[1번: Robot#54]` `[2번: Robot#18]` — 비어있으면 점선 박스 |
| 대기열 전진 | 2번 슬롯 → 1번으로 이동. 이벤트 로그 패널에 QUEUE_ADVANCE 행 표시 |
| 맵 오버레이 연계 | 대기열 로봇은 맵에서 zone 140/141 위치에 표시됨 (scenario_13 UI와 동일 아이콘) |

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

# Robot #18 queue_advance 명령 수신 확인
ros2 topic echo /robot_18/cmd   # → {"cmd": "queue_advance"}

# SM 전환 확인 (STANDBY_2 → TOWARD_STANDBY_1 → STANDBY_1)
ros2 topic echo /robot_18/status

# QUEUE_ADVANCE 이벤트 확인
sqlite3 src/control_center/control_service/data/control.db \
  "SELECT * FROM event_log WHERE event_type='QUEUE_ADVANCE' ORDER BY occurred_at DESC LIMIT 3;"
```
