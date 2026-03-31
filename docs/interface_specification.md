# Interface Specification

> 모듈 간 통신 규칙 명세. 구현체 위치: `src/shoppinkki/shoppinkki_interfaces/`

---

## 1. 모듈 간 Python 인터페이스

### 의존 관계

```
shoppinkki_core (main_node)
    ├── OwnerDetectorInterface  ← shoppinkki_perception 구현 (OwnerDetector 또는 ArucoTracker)
    ├── QRScannerInterface      ← shoppinkki_perception 구현
    ├── PoseScannerInterface    ← shoppinkki_perception 구현 (PERSON 모드 전용)
    ├── NavBTInterface          ← shoppinkki_nav 구현 (BTWaiting / BTGuiding / BTReturning)
    ├── BoundaryMonitorInterface ← shoppinkki_nav 구현 (ARUCO 모드 전용)
    └── RobotPublisherInterface ← shoppinkki_core 내부 구현
```

### 데모 모드별 사용 범위

| 인터페이스 | PERSON 모드 | ARUCO 모드 |
|---|---|---|
| `OwnerDetectorInterface` | `OwnerDetector` (YOLO+ReID) | `ArucoTracker` (ArUco 마커) |
| `QRScannerInterface` | ✅ | ✅ |
| `PoseScannerInterface` | ✅ | ❌ |
| `NavBTInterface` — BTWaiting | ✅ | ✅ |
| `NavBTInterface` — BTGuiding / BTReturning | ❌ | ✅ |
| `BoundaryMonitorInterface` | ❌ | ✅ |
| `RobotPublisherInterface` | ✅ | ✅ |

---

### `protocols.py`

```python
from typing import Protocol, Optional
from dataclasses import dataclass

# ── 공유 데이터 타입 ─────────────────────────────────────────────

@dataclass
class Detection:
    cx: float           # bbox 중심 x (픽셀)
    area: float         # bbox 넓이 (px²) — PERSON 모드 거리 추정용
    distance: float     # 실제 Z 거리 (m) — ARUCO 모드 거리 추정용
    confidence: float   # ReID 유사도 (0~1)

@dataclass
class CartItem:
    item_id: int
    product_name: str
    price: int


# ── shoppinkki_perception 구현 ───────────────────────────────────

class OwnerDetectorInterface(Protocol):
    def run(self, frame, camera_mode: str) -> None: ...
    # camera_mode: "YOLO" | "ARUCO" | "QR" | "POSE_SCAN" | "ARUCO_SCAN" | "NONE"
    # 해당 모드가 아니면 즉시 return (CPU 낭비 없음)

    def get_latest(self) -> Optional[Detection]: ...
    # 가장 최근 프레임의 감지 결과. 미감지시 None

    def register_target(self) -> None: ...
    # ARUCO 모드 전용. 마커 ID 1회 등록 (blocking). REGISTERING 상태에서 별도 스레드 호출


class QRScannerInterface(Protocol):
    def start(self, on_scanned: callable, on_timeout: callable) -> None: ...
    # on_scanned(name: str, price: int) — 스캔 성공마다 호출, 타이머 리셋
    # on_timeout() — 마지막 스캔으로부터 30초 무활동시 호출

    def stop(self) -> None: ...


class PoseScannerInterface(Protocol):
    def scan(self, session_id: str, on_direction_done: callable) -> list[dict]: ...
    # front → right → back → left 순서 촬영
    # on_direction_done(direction: str) — 각 방향 완료시 호출 (부저 신호음용)
    # 반환: [{session_id, direction, hsv_top_json, hsv_bottom_json}, ...]


# ── shoppinkki_nav 구현 ──────────────────────────────────────────

class NavBTInterface(Protocol):
    def start(self, **kwargs) -> None: ...
    # BTGuiding: start(zone_id=6) 형태로 zone_id 전달

    def stop(self) -> None: ...

    def tick(self) -> str: ...
    # 반환: "RUNNING" | "SUCCESS" | "FAILURE"
    # BehaviorTreeRunner가 주기적으로 호출


class BoundaryMonitorInterface(Protocol):
    def set_callbacks(self, on_zone_out: callable, on_payment_zone: callable) -> None: ...
    # on_zone_out() — shop_boundary 이탈시 → sm.trigger('zone_out')
    # on_payment_zone() — 결제 구역(ID 150) 진입시 1회만 호출

    def update_pose(self, x: float, y: float) -> None: ...
    # /amcl_pose 수신마다 호출


# ── shoppinkki_core 내부 구현 ────────────────────────────────────

class RobotPublisherInterface(Protocol):
    def publish_status(self, mode: str, pos_x: float, pos_y: float, battery: int) -> None: ...
    # /robot_<id>/status 발행 (1~2Hz heartbeat)

    def publish_alarm(self, event_type: str, user_id: str = "") -> None: ...
    # /robot_<id>/alarm 발행 (즉시). event_type: THEFT | BATTERY | TIMEOUT | PAYMENT_ERROR

    def publish_cart(self) -> None: ...
    # /robot_<id>/cart 발행. Pi DB CART_ITEM 전체 → JSON

    def add_cart_item(self, product_name: str, price: int) -> None: ...
    # Pi DB에 CART_ITEM 추가 후 publish_cart() 호출

    def get_cart_items(self) -> list[CartItem]: ...

    def clear_cart(self) -> None: ...
    # Pi DB CART_ITEM 전체 삭제 후 publish_cart() 호출

    def terminate_session(self) -> None: ...
    # 1. CART_ITEM 전체 삭제 (CART.session_id 기준)
    # 2. POSE_DATA 전체 삭제 (session_id 기준)
    # 3. SESSION.is_active = False, expires_at = now
    # 호출 직후 publish_status(mode="IDLE") 발행으로 control_service에 즉시 통보
    # (heartbeat 주기 대기 없이 active_user_id = NULL 처리 유도)
```

---

## 2. 통신 메시지 정의

### 채널 A — Customer UI ↔ customer_web (WebSocket)

| 방향 | 메시지 |
|---|---|
| 앱 → web | `{"cmd": "mode", "value": "WAITING"}` — 모드 전환. value: `WAITING` / `TRACKING` / `RETURNING` / `ITEM_ADDING` |
| 앱 → web | `{"cmd": "find_product", "product": "콜라"}` |
| 앱 → web | `{"cmd": "navigate_to", "zone_id": 6}` |
| 앱 → web | `{"cmd": "delete_item", "item_id": 3}` |
| web → 앱 | `{"type": "status", "mode": "TRACKING", "pos_x": 1.2, "pos_y": 0.8, "battery": 72, "my_robot": {...}, "other_robots": [...]}` |
| web → 앱 | `{"type": "cart", "items": [{"id": 1, "name": "콜라", "price": 1500}]}` |
| web → 앱 | `{"type": "find_product_result", "zone_id": 6, "zone_name": "음료"}` |
| web → 앱 | `{"type": "arrived", "zone_name": "음료"}` |
| web → 앱 | `{"type": "nav_failed"}` |
| web → 앱 | `{"type": "alarm", "event": "PAYMENT_ERROR"}` |
| web → 앱 | `{"type": "payment_done"}` |
| web → 앱 | `{"type": "registering", "mode": "ARUCO"}` — ARUCO 등록 대기 중 스피너 표시용 |
| web → 앱 | `{"type": "pose_scan_progress", "direction": "front"\|"right"\|"back"\|"left"}` — PERSON 포즈 스캔 진행 상태 |
| web → 앱 | `{"type": "registration_done"}` — 등록 완료, UI 전환 신호 |

---

### 채널 B — customer_web ↔ control_service (TCP localhost:8080, JSON 개행 구분)

| 방향 | 메시지 |
|---|---|
| web → control | `{"cmd": "login", "robot_id": 54, "user_id": "...", "password": "..."}` |
| web → control | `{"cmd": "session_check", "robot_id": 54}` |
| web → control | `{"cmd": "mode", "robot_id": 54, "value": "WAITING"}` |
| web → control | `{"cmd": "navigate_to", "robot_id": 54, "zone_id": 6}` |
| web → control | `{"cmd": "find_product", "robot_id": 54, "product": "콜라"}` |
| web → control | `{"cmd": "delete_item", "robot_id": 54, "item_id": 3}` |
| web → control | `{"cmd": "process_payment", "robot_id": 54}` — 가상 결제 요청 |
| web → control | `{"cmd": "dismiss_alarm", "robot_id": 54, "pin": "1234"}` — 현장 PIN으로 알람 해제 |
| control → web | `{"type": "status", "my_robot": {...}, "other_robots": [...]}` — 1~2Hz push |
| control → web | `{"type": "cart", "robot_id": 54, "items": [...]}` |
| control → web | `{"type": "alarm", "robot_id": 54, "event": "THEFT"}` |
| control → web | `{"type": "arrived", "robot_id": 54, "zone_name": "음료"}` |
| control → web | `{"type": "find_product_result", "robot_id": 54, "zone_id": 6, "zone_name": "음료"}` |

---

### 채널 C — Pi 5 ↔ control_service (ROS DDS, `ROS_DOMAIN_ID=14`)

| 방향 | 토픽 | 타입 | 페이로드 |
|---|---|---|---|
| Pi → control | `/robot_<id>/status` | `std_msgs/String` | `{"mode": "TRACKING", "pos_x": 1.2, "pos_y": 0.8, "battery": 72}` |
| Pi → control | `/robot_<id>/alarm` | `std_msgs/String` | `{"event": "THEFT", "user_id": "hong123"}` — event: `THEFT` \| `BATTERY_LOW` \| `TIMEOUT` \| `PAYMENT_ERROR` |
| Pi → control | `/robot_<id>/cart` | `std_msgs/String` | `{"items": [{"id": 1, "name": "콜라", "price": 1500}]}` |
| control → Pi | `/robot_<id>/cmd` | `std_msgs/String` | `{"cmd": "start_session", "user_id": "hong123"}` |
| control → Pi | `/robot_<id>/cmd` | `std_msgs/String` | `{"cmd": "mode", "value": "WAITING"}` |
| control → Pi | `/robot_<id>/cmd` | `std_msgs/String` | `{"cmd": "navigate_to", "zone_id": 6}` |
| control → Pi | `/robot_<id>/cmd` | `std_msgs/String` | `{"cmd": "dismiss_alarm"}` |
| control → Pi | `/robot_<id>/cmd` | `std_msgs/String` | `{"cmd": "payment_error"}` — 결제 실패 시 ALARM 전환 트리거 |
| control → Pi | `/robot_<id>/cmd` | `std_msgs/String` | `{"cmd": "delete_item", "item_id": 3}` |
| control → Pi | `/robot_<id>/cmd` | `std_msgs/String` | `{"cmd": "force_terminate"}` — 관제 강제 종료. Pi: `terminate_session()` + `sm.trigger('admin_force_idle')` |
| control → Pi | `/robot_<id>/cmd` | `std_msgs/String` | `{"cmd": "admin_goto", "x": 1.2, "y": 0.8, "theta": 0.0}` — IDLE 상태에서 Nav2 직접 목표 전송 |

---

### 채널 E — Pi 5 ↔ control_service (REST HTTP, 포트 8080)

BTGuiding / BTReturning이 Waypoint 좌표를 조회하는 내부 REST API.

| 메서드 | 경로 | 응답 | 설명 |
|---|---|---|---|
| GET | `/zone/<zone_id>/waypoint` | `{"x": 1.2, "y": 0.8, "theta": 0.0}` | zone_id의 Nav2 목표 좌표 조회 |
| GET | `/boundary` | `{"shop_boundary": {...}, "payment_zone": {...}}` | BOUNDARY_CONFIG 전체 조회 |
| GET | `/find_product?query=<str>` | `{"zone_id": 3, "zone_name": "음료 코너"}` | 상품명 검색 (테스트/디버그용) |
| GET | `/queue/assign?robot_id=<id>` | `{"zone_id": 140}` | 대기열 position 배정. BTReturning 시작 시 호출. zone 140(1번) 또는 141(2번) 반환 |
| GET | `/events?robot_id=<id>&limit=<n>` | `[{"log_id":1, "event_type":"SESSION_START", ...}]` | EVENT_LOG 조회. robot_id 생략 시 전체 로봇 이벤트 반환 |

---

### 채널 D — admin_app ↔ control_service (동일 서버 PC 내 직접 참조)

> `admin_app`과 `control_service`는 같은 프로세스(또는 동일 PC 내)에서 동작하므로 ROS DDS를 거치지 않고 직접 참조한다.

| 방향 | 데이터 | 용도 |
|---|---|---|
| control → admin | 로봇 상태 dict (mode, pos_x, pos_y, battery) | 로봇 위치·모드 실시간 표시 |
| control → admin | 알람 이벤트 dict (event_type, robot_id) | 알람 패널 표시 |
| control → admin | offline 이벤트 (robot_id) | 로봇 카드 회색 처리 |
| control → admin | online 복귀 이벤트 (robot_id) | 로봇 카드 정상 복구 |
| admin → control | `dismiss_alarm(robot_id)` | 알람 해제 |
| admin → control | `force_terminate(robot_id)` | 세션 강제 종료 → Pi `{"cmd": "force_terminate"}` relay |
| admin → control | `admin_goto(robot_id, x, y, theta)` | 위치 호출 → Pi `{"cmd": "admin_goto", "x":..., "y":..., "theta":...}` relay. IDLE 상태 로봇만 수락 |
