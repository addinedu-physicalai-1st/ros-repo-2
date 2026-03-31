# 시나리오 15: 관제 — 세션 강제 종료 및 위치 호출

**SM 전환:** `ANY → IDLE` (강제 종료) / IDLE 유지 (위치 호출 — Nav2 직접)
**모드:** PERSON/ARUCO 공통
**관련 패키지:** admin_app, control_service, shoppinkki_core

---

## 개요

관제자가 특정 로봇의 세션을 강제 종료시켜 IDLE로 초기화하거나,
IDLE 상태 로봇을 맵에서 클릭한 위치로 이동 명령을 내린다.
두 기능은 독립적으로 사용하거나 순서대로 사용할 수 있다
(강제 종료 후 → 원하는 위치로 이동).

---

## 기능 체크리스트

| 완료 | 기능 |
|:---:|---|
| [ ] | admin_app: 로봇 카드에 [강제 종료] 버튼 표시 |
| [ ] | [강제 종료] → `control_service.force_terminate(robot_id)` 직접 호출 (채널 D) |
| [ ] | control_service → `/robot_<id>/cmd`: `{"cmd": "force_terminate"}` ROS publish |
| [ ] | Pi: `on_cmd force_terminate` → `terminate_session()` + `sm.trigger('admin_force_idle')` |
| [ ] | SM: `admin_force_idle` 트리거 — 모든 상태 → IDLE (와일드카드 전환) |
| [ ] | `terminate_session()`: CART_ITEM 삭제, POSE_DATA 삭제, SESSION.is_active=False |
| [ ] | 강제 종료 직후 `publish_status(mode="IDLE")` 발행 → control_service active_user_id=NULL |
| [ ] | admin_app: 맵 클릭 → 좌표 (x, y) 추출 |
| [ ] | admin_app: [이동 명령] 버튼 → `control_service.admin_goto(robot_id, x, y, theta=0.0)` (채널 D) |
| [ ] | control_service → `/robot_<id>/cmd`: `{"cmd": "admin_goto", "x": 1.2, "y": 0.8, "theta": 0.0}` |
| [ ] | Pi: `on_cmd admin_goto` — IDLE 상태에서만 수락. Nav2 ActionClient에 직접 목표 전송 |
| [ ] | Pi: Nav2 goal 성공/실패 시 결과를 `/robot_<id>/status`에 반영 |
| [ ] | admin_app: 위치 호출 진행 중 맵 오버레이에 목표 마커 표시 |
| [ ] | admin_app: 도착/실패 후 목표 마커 제거 |

---

## 전제조건

- admin_app + control_service 기동 중
- 강제 종료 시: 로봇이 IDLE 이외 임의 상태 (세션 있음)
- 위치 호출 시: 로봇이 IDLE 상태 (세션 없음)

---

## 흐름

```
────── 파트 1: 세션 강제 종료 ──────

admin_app: [강제 종료] 버튼 클릭 (robot_id)
    → control_service.force_terminate(robot_id)  직접 호출 (채널 D)
    ↓
control_service: force_terminate(robot_id)
    → ROS publish /robot_<id>/cmd: {"cmd": "force_terminate"}
    ↓
Pi: on_cmd("force_terminate")
    → bt_runner.stop()  ← 현재 BT 즉시 중단
    → terminate_session()
        1. CART_ITEM 전체 삭제 (cart_id 기준)
        2. POSE_DATA 전체 삭제 (session_id 기준)
        3. SESSION.is_active = False, expires_at = now
    → sm.trigger('admin_force_idle')  ← ANY → IDLE
    → publish_status(mode="IDLE")  ← 즉시 발행 (heartbeat 대기 없음)
    → current_alarm = None
    ↓
control_service: /robot_<id>/status 수신 (mode="IDLE")
    → ROBOT.current_mode = "IDLE", active_user_id = NULL
    ↓
admin_app: 로봇 카드 IDLE 표시 복구


────── 파트 2: 위치 호출 ──────

admin_app: 맵 이미지 클릭
    → 클릭 픽셀 (px, py) → world 좌표 (x, y) 역변환 (pixel_to_world)
    → 목표 마커 맵 오버레이에 표시
    ↓
admin_app: [이동 명령] 버튼 클릭 (robot_id, x, y)
    → control_service.admin_goto(robot_id, x, y, theta=0.0)  직접 호출 (채널 D)
    ↓
control_service: admin_goto(robot_id, x, y, theta)
    → ROBOT.current_mode == "IDLE" 확인 (아니면 거부)
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
    → publish_status(mode="IDLE")  ← 정상
    ↓
도착 실패:
    Pi: Nav2 result != SUCCEEDED
    → 정지, publish_status(mode="IDLE")
    → (선택) /robot_<id>/alarm publish: {"event": "TIMEOUT", "user_id": ""}
    ↓
admin_app: 목표 마커 제거 (status 갱신으로 도착 감지)
```

### 강제 종료 전환 테이블 (admin_force_idle)

| From | To | 비고 |
|---|---|---|
| IDLE | IDLE | 이미 IDLE이면 무시 (terminate_session만 호출 없이) |
| REGISTERING | IDLE | 포즈 스캔 스레드 중단 포함 |
| TRACKING | IDLE | bt_runner.stop() 포함 |
| SEARCHING | IDLE | bt_runner.stop() 포함 |
| WAITING | IDLE | bt_runner.stop() 포함 |
| ITEM_ADDING | IDLE | QR 스캔 중단 포함 |
| GUIDING | IDLE | Nav2 goal 취소 포함 |
| RETURNING | IDLE | Nav2 goal 취소 포함 |
| ALARM | IDLE | current_alarm=None 포함. ALARM_LOG resolved_at=now 갱신 |

---

## 예제 코드 및 모순 점검

### control_service: force_terminate + admin_goto

```python
# control_service/main_node.py
class ControlServiceNode(rclpy.node.Node):
    def force_terminate(self, robot_id: int) -> dict:
        self._ros_publish(robot_id, json.dumps({"cmd": "force_terminate"}))
        return {"status": "ok"}

    def admin_goto(self, robot_id: int, x: float, y: float, theta: float = 0.0) -> dict:
        # IDLE 상태 확인
        row = self.db.execute(
            "SELECT current_mode FROM robot WHERE robot_id=?", (robot_id,)
        ).fetchone()
        if not row or row[0] != "IDLE":
            return {"error": "robot_not_idle", "current_mode": row[0] if row else None}

        self._ros_publish(robot_id, json.dumps({
            "cmd": "admin_goto", "x": x, "y": y, "theta": theta
        }))
        return {"status": "ok"}
```

### Pi: force_terminate 및 admin_goto on_cmd 핸들러

```python
# shoppinkki_core/main_node.py
import rclpy.action
from nav2_msgs.action import NavigateToPose
from geometry_msgs.msg import PoseStamped
import math

class ShoppinkiMainNode(rclpy.node.Node):
    def on_cmd(self, msg):
        data = json.loads(msg.data)
        cmd = data.get('cmd')

        if cmd == 'force_terminate':
            self.bt_runner.stop()
            # ALARM 상태였으면 ALARM_LOG resolved_at 처리 요청
            if hasattr(self, 'current_alarm') and self.current_alarm:
                self.publish_alarm_resolved()  # 별도 토픽 또는 status로 전달
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

    def _admin_nav2_goal(self, x: float, y: float, theta: float):
        # ⚠️ 모순 #1: Nav2 ActionClient는 별도 초기화 필요
        # NavigateToPose action server가 준비됐는지 확인 필요
        if not self._nav_client.wait_for_server(timeout_sec=3.0):
            self.get_logger().error("Nav2 action server not available")
            return

        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = 'map'
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = x
        goal.pose.pose.position.y = y
        goal.pose.pose.orientation.z = math.sin(theta / 2)
        goal.pose.pose.orientation.w = math.cos(theta / 2)

        self._nav_client.send_goal_async(
            goal,
            feedback_callback=lambda fb: None
        ).add_done_callback(self._on_admin_nav_response)

    def _on_admin_nav_response(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warn("admin_goto goal rejected")
            return
        goal_handle.get_result_async().add_done_callback(self._on_admin_nav_result)

    def _on_admin_nav_result(self, future):
        status = future.result().status
        if status == 4:  # SUCCEEDED
            self.get_logger().info("admin_goto: arrived")
        else:
            self.get_logger().warn(f"admin_goto: nav failed (status={status})")
```

### admin_app: 맵 클릭 → 좌표 역변환

```python
# admin_app/map_widget.py (QLabel 또는 QGraphicsView 기반)

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

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.selected_pos:
            px, py = world_to_pixel(*self.selected_pos, self.pixmap().height())
            painter = QPainter(self)
            painter.setPen(QPen(Qt.blue, 3))
            painter.drawEllipse(px - 8, py - 8, 16, 16)
            painter.drawLine(px, py - 12, px, py + 12)  # 십자 마커
            painter.drawLine(px - 12, py, px + 12, py)
```

### 모순 및 검토 사항

| # | 항목 | 내용 | 처리 |
|---|---|---|---|
| 1 | **SM wildcard 전환** | `transitions` 라이브러리에서 모든 상태에서 하나의 trigger로 전환하려면 `source='*'` 사용. 단, IDLE → IDLE은 `ignore_invalid_triggers=True`로 무시 | `machine.add_transition('admin_force_idle', source='*', dest='IDLE')` |
| 2 | **ALARM 상태 강제 종료** | ALARM 중 force_terminate 시 ALARM_LOG.resolved_at 갱신 미정의 | force_terminate → Pi가 `publish_alarm_resolved` 신호를 보내거나, control_service가 force_terminate 호출 시 `ALARM_LOG` 자동 갱신 |
| 3 | **admin_goto IDLE 확인 타이밍** | control_service가 `admin_goto()` 호출 시 ROBOT.current_mode를 확인하지만, Pi는 이미 다른 상태일 수 있음 | Pi에서도 `sm.state != 'IDLE'`이면 무시하는 이중 체크 필수 |
| 4 | **Nav2 ActionClient 미초기화** | `shoppinkki_core/main_node.py`에 BTGuiding/BTReturning용 Nav2 client가 있지만, admin_goto용으로는 별도 초기화 필요 | 기존 BT 내 Nav2 client를 재사용하거나, main_node에서 직접 `_nav_client` 초기화 |
| 5 | **admin_goto 중 사용자 로그인** | 로봇이 admin_goto 이동 중(IDLE 상태)에 QR 스캔으로 로그인 시도 가능 | `session_check` 응답은 `available`이지만 로봇이 이동 중. `is_navigating` 플래그 관리 필요 또는 admin_goto 중 start_session cmd 무시 |
| 6 | **Channel D force_terminate 명세 누락** | 현재 `interface_specification.md` 채널 D에 `force_terminate`, `admin_goto`가 미정의 | interface_specification.md 채널 D 갱신 필요 |

---

## 기대 결과

| 상황 | 결과 |
|---|---|
| [강제 종료] 클릭 (TRACKING 중) | 로봇 정지 → IDLE, 세션 종료, active_user_id=NULL |
| [강제 종료] 클릭 (ALARM 중) | ALARM 해제 → IDLE, 세션 종료 (ALARM_LOG 갱신 포함) |
| [이동 명령] 클릭 (IDLE) | 로봇 Nav2 이동 시작, 맵 목표 마커 표시 |
| [이동 명령] 클릭 (IDLE 아님) | control_service 거부, admin_app 오류 메시지 |
| Nav2 이동 도착 | 목표 마커 제거, IDLE 유지 |

---

## UI 검토

| 요소 | 내용 |
|---|---|
| [강제 종료] 버튼 위치 | 로봇 카드 하단. IDLE 상태에서는 비활성화(dim) |
| 확인 다이얼로그 | "[강제 종료] 현재 세션이 삭제됩니다. 계속하시겠습니까?" — 실수 방지 |
| [이동 명령] 버튼 | 맵에서 클릭 후 활성화. IDLE 아니면 비활성화 |
| 맵 목표 마커 | 파란색 십자+원. 이동 완료 또는 실패 시 자동 제거 |
| 이동 중 상태 | 로봇 카드에 "이동 중" 뱃지 추가 (IDLE 모드지만 Nav2 이동 중임을 표시) — `is_navigating` 플래그 필요 |
| 강제 종료 후 | 로봇 카드 즉시 IDLE 뱃지로 전환. customer_web 세션 만료 처리 자동 진행 |

---

## 검증 방법

```bash
# 강제 종료 시뮬레이션
ros2 topic pub --once /robot_54/cmd std_msgs/String \
  '{"data": "{\"cmd\": \"force_terminate\"}"}'

# Pi SM 상태 확인 → IDLE
ros2 topic echo /robot_54/status

# 세션 종료 확인
sqlite3 src/shoppinkki/shoppinkki_core/data/pi.db \
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
