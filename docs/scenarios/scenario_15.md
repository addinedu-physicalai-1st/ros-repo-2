# 시나리오 15: 관제 — 세션 강제 종료 및 위치 호출

**SM 전환:** `ANY → IDLE` (강제 종료) / IDLE 유지 (위치 호출 — Nav2 직접)
**관련 패키지:** admin_ui, control_service, shoppinkki_core

---

## 개요

관제자가 특정 로봇의 세션을 강제 종료시켜 IDLE로 초기화하거나,
IDLE 상태 로봇을 맵에서 클릭한 위치로 이동 명령을 내린다.
두 기능은 독립적으로 사용하거나 순서대로 사용할 수 있다
(강제 종료 후 → 원하는 위치로 이동).

> **아키텍처:** admin_ui은 control_service와 **별도 프로세스**. **채널 B(TCP)**로 연결된다.
> admin_ui은 TCP 명령으로 force_terminate/admin_goto를 요청하고, control_service가 ROS publish로 Pi에 전달한다.

---

## 기능 체크리스트

| 완료 | 기능 |
|:---:|---|
| [ ] | admin_ui: 로봇 카드에 [강제 종료] 버튼 표시 |
| [ ] | [강제 종료] → admin_ui TCP → control_service: `{"cmd": "force_terminate", "robot_id": <id>}` |
| [ ] | control_service → `/robot_<id>/cmd`: `{"cmd": "force_terminate"}` ROS publish |
| [ ] | Pi: `on_cmd force_terminate` → `bt_runner.stop()` + `terminate_session()` + `sm.trigger('admin_force_idle')` |
| [ ] | SM: `admin_force_idle` 트리거 — 모든 상태 → IDLE (와일드카드 전환) |
| [ ] | `terminate_session()`: REST API — SESSION `is_active=False`, CART_ITEM 삭제 |
| [ ] | 강제 종료 직후 `publish_status(mode="IDLE")` 발행 → control_service `active_user_id=NULL` |
| [ ] | admin_ui: 맵 클릭 → 좌표 (x, y) 추출 |
| [ ] | admin_ui: [이동 명령] 버튼 → TCP → control_service: `{"cmd": "admin_goto", "robot_id": <id>, "x": 1.2, "y": 0.8, "theta": 0.0}` |
| [ ] | control_service → `/robot_<id>/cmd`: `{"cmd": "admin_goto", "x": 1.2, "y": 0.8, "theta": 0.0}` |
| [ ] | Pi: `on_cmd admin_goto` — IDLE 상태에서만 수락. Nav2 ActionClient에 직접 목표 전송 |
| [ ] | Pi: Nav2 goal 성공/실패 시 결과를 `/robot_<id>/status`에 반영 |
| [ ] | admin_ui: 위치 호출 진행 중 맵 오버레이에 목표 마커 표시 |
| [ ] | admin_ui: 도착/실패 후 목표 마커 제거 |

---

## 전제조건

- admin_ui + control_service 기동 중, admin_ui이 control_service에 TCP 연결됨 (채널 B)
- 강제 종료 시: 로봇이 IDLE 이외 임의 상태 (세션 있음)
- 위치 호출 시: 로봇이 IDLE 상태 (세션 없음)

---

## 흐름

```
────── 파트 1: 세션 강제 종료 ──────

admin_ui: [강제 종료] 버튼 클릭 (robot_id)
    → TCP → control_service: {"cmd": "force_terminate", "robot_id": <id>}
    ↓
control_service: force_terminate 처리
    → ROS publish /robot_<id>/cmd: {"cmd": "force_terminate"}
    ↓
Pi: on_cmd("force_terminate")
    → bt_runner.stop()  ← 현재 BT 즉시 중단
    → terminate_session()
        1. REST API: CART_ITEM 전체 삭제 (session_id 기준)
        2. REST API: SESSION.is_active = False, expires_at = now
    → sm.trigger('admin_force_idle')  ← ANY → IDLE
    → publish_status(mode="IDLE")  ← 즉시 발행 (heartbeat 대기 없음)
    → current_alarm = None
    ↓
control_service: /robot_<id>/status 수신 (mode="IDLE")
    → ROBOT.current_mode = "IDLE", active_user_id = NULL
    ↓
admin_ui: 로봇 카드 IDLE 표시 복구 (status TCP push 수신 시)


────── 파트 2: 위치 호출 ──────

admin_ui: 맵 이미지 클릭
    → 클릭 픽셀 (px, py) → world 좌표 (x, y) 역변환 (pixel_to_world)
    → 목표 마커 맵 오버레이에 표시
    ↓
admin_ui: [이동 명령] 버튼 클릭 (robot_id, x, y)
    → TCP → control_service: {"cmd": "admin_goto", "robot_id": <id>, "x": x, "y": y, "theta": 0.0}
    ↓
control_service: admin_goto 처리
    → ROBOT.current_mode == "IDLE" 확인 (아니면 거부 응답)
    → ROS publish /robot_<id>/cmd: {"cmd": "admin_goto", "x": x, "y": y, "theta": theta}
    ↓
Pi: on_cmd("admin_goto")
    → sm.state != "IDLE"이면 무시 (안전 체크)
    → Nav2 ActionClient로 직접 goal 전송 (SM 상태 변경 없음)
      ※ 활성 세션 없으므로 BT 불필요. NavigateToPose action 직접 사용
    → 이동 중: publish_status(mode="IDLE", pos_x=..., pos_y=...)  ← 위치는 계속 갱신
    ↓
도착 성공:
    Pi: Nav2 result == SUCCEEDED
    → 정지 (cmd_vel = 0)
    → publish_status(mode="IDLE")
    ↓
도착 실패:
    Pi: Nav2 result != SUCCEEDED
    → 정지, publish_status(mode="IDLE")
    ↓
admin_ui: 목표 마커 제거 (status TCP push 수신으로 도착 감지)
```

### 강제 종료 전환 테이블 (admin_force_idle)

| From | To | 비고 |
|---|---|---|
| IDLE | IDLE | 이미 IDLE이면 terminate_session 호출 없이 무시 |
| REGISTERING | IDLE | 등록 루프 스레드 중단 포함 |
| TRACKING | IDLE | bt_runner.stop() 포함 |
| SEARCHING | IDLE | bt_runner.stop() 포함 |
| WAITING | IDLE | bt_runner.stop() 포함 |
| ITEM_ADDING | IDLE | QR 스캔 중단 포함 |
| GUIDING | IDLE | Nav2 goal 취소 포함 |
| RETURNING | IDLE | Nav2 goal 취소 포함 |
| ALARM | IDLE | current_alarm=None 포함. ALARM_LOG resolved_at=now 갱신 |

---

## 예제 코드 및 모순 점검

### control_service: admin 명령 처리

```python
# control_service/main_node.py
class ControlServiceNode(rclpy.node.Node):
    def _handle_admin_cmd(self, cmd: dict):
        """채널 B: admin_ui TCP 명령 처리"""
        op = cmd.get('cmd')
        robot_id = cmd.get('robot_id')

        if op == 'force_terminate':
            self._ros_publish(robot_id, json.dumps({"cmd": "force_terminate"}))

        elif op == 'admin_goto':
            row = self.db.execute(
                "SELECT current_mode FROM robot WHERE robot_id=?", (robot_id,)
            ).fetchone()
            if not row or row[0] != "IDLE":
                # admin_ui에 거부 응답
                self._tcp_push_admin({
                    "type": "admin_goto_rejected",
                    "robot_id": robot_id, "reason": "not_idle"
                })
                return
            self._ros_publish(robot_id, json.dumps({
                "cmd": "admin_goto",
                "x": cmd['x'], "y": cmd['y'], "theta": cmd.get('theta', 0.0)
            }))
```

### Pi: force_terminate 및 admin_goto on_cmd 핸들러

```python
# shoppinkki_core/main_node.py
class ShoppinkiMainNode(rclpy.node.Node):
    def on_cmd(self, msg):
        data = json.loads(msg.data)
        cmd = data.get('cmd')

        if cmd == 'force_terminate':
            self.bt_runner.stop()
            if self.current_alarm:
                # ALARM_LOG resolved_at 처리를 위해 status에 포함 또는 별도 토픽 전송
                pass
            self.terminate_session()
            self.sm.trigger('admin_force_idle')
            self.current_alarm = None
            self.publish_status(mode="IDLE", pos_x=self._pos_x, pos_y=self._pos_y,
                                battery=self._battery)

        elif cmd == 'admin_goto':
            if self.sm.state != 'IDLE':
                self.get_logger().warn(f"admin_goto ignored: state={self.sm.state}")
                return
            x, y, theta = data['x'], data['y'], data.get('theta', 0.0)
            self._admin_nav2_goal(x, y, theta)
```

### admin_ui: 맵 클릭 → 좌표 역변환

```python
# admin_ui/map_widget.py

def pixel_to_world(px: int, py: int, img_height: int) -> tuple[float, float]:
    """픽셀 좌표 → 월드 좌표 역변환"""
    x = px * MAP_RESOLUTION + MAP_ORIGIN_X
    y = (img_height - py) * MAP_RESOLUTION + MAP_ORIGIN_Y  # y축 반전 복원
    return x, y

class MapWidget(QLabel):
    def mousePressEvent(self, event):
        px, py = event.x(), event.y()
        x, y = pixel_to_world(px, py, self.pixmap().height())
        self.selected_pos = (x, y)
        self.update()  # 목표 마커 재그리기

    def _on_goto_clicked(self, robot_id: int):
        if self.selected_pos:
            x, y = self.selected_pos
            # TCP → control_service (채널 B)
            self._tcp_send({
                "cmd": "admin_goto",
                "robot_id": robot_id, "x": x, "y": y, "theta": 0.0
            })
```

### 모순 및 검토 사항

| # | 항목 | 내용 | 처리 |
|---|---|---|---|
| 1 | **SM wildcard 전환** | 모든 상태에서 하나의 trigger로 전환: `source='*'` 사용. IDLE → IDLE은 `ignore_invalid_triggers=True`로 무시 | `machine.add_transition('admin_force_idle', source='*', dest='IDLE')` |
| 2 | **ALARM 상태 강제 종료** | ALARM 중 force_terminate 시 ALARM_LOG.resolved_at 갱신 필요 | control_service가 IDLE status 수신 시 미해결 ALARM_LOG를 자동 갱신 |
| 3 | **admin_goto IDLE 확인 타이밍** | control_service가 ROBOT.current_mode를 확인하지만 Pi와 타이밍 불일치 가능 | Pi에서도 `sm.state != 'IDLE'`이면 무시하는 이중 체크 필수 |
| 4 | **admin_goto 중 사용자 로그인** | 로봇이 admin_goto 이동 중(IDLE 상태)에 QR 스캔으로 로그인 시도 가능 | `session_check` 시 `is_navigating` 플래그 관리 또는 admin_goto 중 start_session cmd 무시 |

---

## 기대 결과

| 상황 | 결과 |
|---|---|
| [강제 종료] 클릭 (TRACKING 중) | 로봇 정지 → IDLE, 세션 종료, active_user_id=NULL |
| [강제 종료] 클릭 (ALARM 중) | ALARM 해제 → IDLE, 세션 종료 |
| [이동 명령] 클릭 (IDLE) | 로봇 Nav2 이동 시작, 맵 목표 마커 표시 |
| [이동 명령] 클릭 (IDLE 아님) | control_service 거부, admin_ui 오류 메시지 |
| Nav2 이동 도착 | 목표 마커 제거, IDLE 유지 |

---

## UI 검토

| 요소 | 내용 |
|---|---|
| [강제 종료] 버튼 위치 | 로봇 카드 하단. IDLE 상태에서는 비활성화(dim) |
| 확인 다이얼로그 | "[강제 종료] 현재 세션이 삭제됩니다. 계속하시겠습니까?" — 실수 방지 |
| [이동 명령] 버튼 | 맵에서 클릭 후 활성화. IDLE 아니면 비활성화 |
| 맵 목표 마커 | 파란색 십자+원. 이동 완료 또는 실패 시 자동 제거 |
| 이동 중 상태 | 로봇 카드에 "이동 중" 뱃지 추가 (IDLE 모드지만 Nav2 이동 중임을 표시) |
| 강제 종료 후 | 로봇 카드 즉시 IDLE 뱃지로 전환. customer_web 세션 만료 처리 자동 진행 |

---

## 검증 방법

```bash
# 강제 종료 시뮬레이션
ros2 topic pub --once /robot_54/cmd std_msgs/String \
  '{"data": "{\"cmd\": \"force_terminate\"}"}'

# Pi SM 상태 확인 → IDLE
ros2 topic echo /robot_54/status

# 세션 종료 확인 (중앙 DB)
sqlite3 src/control_center/control_service/data/control.db \
  "SELECT is_active, expires_at FROM session ORDER BY created_at DESC LIMIT 1;"
# → is_active = 0

# control_service active_user_id 확인
sqlite3 src/control_center/control_service/data/control.db \
  "SELECT robot_id, current_mode, active_user_id FROM robot;"
# → active_user_id = NULL

# 위치 호출 시뮬레이션
ros2 topic pub --once /robot_54/cmd std_msgs/String \
  '{"data": "{\"cmd\": \"admin_goto\", \"x\": 0.5, \"y\": 0.3, \"theta\": 0.0}"}'

# Nav2 이동 확인
ros2 topic echo /robot_54/status   # pos_x, pos_y 변화 확인
```
