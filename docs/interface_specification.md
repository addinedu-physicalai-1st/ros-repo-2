# Interface Specification

> 모듈 간 통신 규칙 명세. 구현체 위치: `src/shoppinkki/shoppinkki_interfaces/`

---

## 1. 모듈 간 Python 인터페이스

### 의존 관계

```
shoppinkki_core (main_node)
    ├── DollDetectorInterface    ← shoppinkki_perception 구현 (커스텀 YOLO 인형 감지)
    ├── QRScannerInterface       ← shoppinkki_perception 구현
    ├── NavBTInterface           ← shoppinkki_nav 구현 (BTWaiting / BTGuiding / BTReturning)
    ├── BoundaryMonitorInterface ← shoppinkki_nav 구현
    └── RobotPublisherInterface  ← shoppinkki_core 내부 구현
```

---

### `protocols.py`

```python
from typing import Protocol, Optional
from dataclasses import dataclass

# ── 공유 데이터 타입 ─────────────────────────────────────────────

@dataclass
class Detection:
    cx: float           # bbox 중심 x (픽셀)
    area: float         # bbox 넓이 (px²) — 거리 추정용 (P-Control 선속도)
    confidence: float   # YOLO 감지 신뢰도 (0~1)
    reid_score: float   # ReID + 색상 유사도 (0~1) — 주인 인형 매칭 점수

@dataclass
class CartItem:
    item_id: int
    product_name: str
    price: int


# ── shoppinkki_perception 구현 ───────────────────────────────────

class DollDetectorInterface(Protocol):
    def register(self, frame) -> bool: ...
    # REGISTERING 단계: 현재 프레임에서 인형을 YOLO로 감지하고
    # ReID 특징 벡터 + 색상 히스토그램을 주인 인형 템플릿으로 저장.
    # 등록 성공(인형 감지됨) 시 True, 미감지 시 False.

    def run(self, frame) -> None: ...
    # TRACKING 단계: YOLO로 인형 클래스 감지 후 ReID + 색상 매칭으로
    # 주인 인형을 식별. 결과(Detection 또는 None)를 내부 버퍼에 저장.

    def get_latest(self) -> Optional[Detection]: ...
    # 가장 최근 프레임의 주인 인형 감지 결과.
    # 미감지 또는 ReID 매칭 임계값 미달 시 None.

    def is_ready(self) -> bool: ...
    # REGISTERING 완료 조건 — register() 성공 후 True.
    # SM이 REGISTERING → TRACKING 전환 판단에 사용.


class QRScannerInterface(Protocol):
    def start(self, on_scanned: callable, on_timeout: callable) -> None: ...
    # on_scanned(name: str, price: int) — 스캔 성공마다 호출, 타이머 리셋
    # on_timeout() — 마지막 스캔으로부터 30초 무활동시 호출

    def stop(self) -> None: ...


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
    # /robot_<id>/alarm 발행 (즉시). event_type: THEFT | BATTERY_LOW | TIMEOUT | PAYMENT_ERROR

    def publish_cart(self) -> None: ...
    # /robot_<id>/cart 발행. Control DB CART_ITEM 조회 → JSON

    def add_cart_item(self, product_name: str, price: int) -> None: ...
    # Control DB에 CART_ITEM 추가 후 publish_cart() 호출 (REST API 경유)

    def get_cart_items(self) -> list[CartItem]: ...

    def clear_cart(self) -> None: ...
    # Control DB CART_ITEM 전체 삭제 후 publish_cart() 호출 (REST API 경유)

    def terminate_session(self) -> None: ...
    # 1. CART_ITEM 전체 삭제 (REST API 경유)
    # 2. SESSION.is_active = False (REST API 경유)
    # 호출 직후 publish_status(mode="IDLE") 발행으로 control_service에 즉시 통보
```

---

## 2. 통신 채널 정의

> 채널 A~H 기준: `docs/system_architecture.md`

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
| web → 앱 | `{"type": "registering"}` — 인형 감지 대기 중 스피너 표시용 |
| web → 앱 | `{"type": "registration_done"}` — 등록 완료(인형 첫 감지 확인), UI 전환 신호 |

---

### 채널 B — Admin UI ↔ control_service (TCP)

> 별도 기기(또는 별도 프로세스)에서 TCP로 control_service에 연결하는 독립 클라이언트.

| 방향 | 메시지 | 설명 |
|---|---|---|
| admin → control | `{"cmd": "dismiss_alarm", "robot_id": 54}` | 알람 해제 |
| admin → control | `{"cmd": "force_terminate", "robot_id": 54}` | 세션 강제 종료 → Pi `{"cmd": "force_terminate"}` relay |
| admin → control | `{"cmd": "admin_goto", "robot_id": 54, "x": 1.2, "y": 0.8, "theta": 0.0}` | 위치 호출 → Pi relay. IDLE 상태 로봇만 수락 |
| control → admin | `{"type": "status", "robot_id": 54, "mode": "TRACKING", "pos_x": 1.2, "pos_y": 0.8, "battery": 72}` | 로봇 상태 실시간 Push (1~2Hz) |
| control → admin | `{"type": "alarm", "robot_id": 54, "event_type": "THEFT", "occurred_at": "..."}` | 알람 발생 |
| control → admin | `{"type": "alarm_dismissed", "robot_id": 54}` | 알람 해제 완료 |
| control → admin | `{"type": "offline", "robot_id": 54}` | 로봇 오프라인 감지 |
| control → admin | `{"type": "online", "robot_id": 54}` | 로봇 온라인 복귀 |
| control → admin | `{"type": "event", ...}` | 운용 이벤트 |

---

### 채널 C — customer_web ↔ control_service (TCP localhost:8080, JSON 개행 구분)

| 방향 | 메시지 |
|---|---|
| web → control | `{"cmd": "login", "robot_id": 54, "user_id": "...", "password": "..."}` |
| web → control | `{"cmd": "session_check", "robot_id": 54}` |
| web → control | `{"cmd": "mode", "robot_id": 54, "value": "WAITING"}` |
| web → control | `{"cmd": "navigate_to", "robot_id": 54, "zone_id": 6}` |
| web → control | `{"cmd": "delete_item", "robot_id": 54, "item_id": 3}` |
| web → control | `{"cmd": "process_payment", "robot_id": 54}` — 가상 결제 요청 |
| web → control | `{"cmd": "dismiss_alarm", "robot_id": 54, "pin": "1234"}` — 현장 PIN으로 알람 해제 |
| control → web | `{"type": "status", "my_robot": {...}, "other_robots": [...]}` — 1~2Hz push |
| control → web | `{"type": "cart", "robot_id": 54, "items": [...]}` |
| control → web | `{"type": "alarm", "robot_id": 54, "event": "THEFT"}` |
| control → web | `{"type": "arrived", "robot_id": 54, "zone_name": "음료"}` |
| control → web | `{"type": "find_product_result", "robot_id": 54, "zone_id": 6, "zone_name": "음료"}` |

---

### 채널 D — customer_web ↔ LLM (REST HTTP, 포트 8000)

> customer_web이 LLM Docker 서비스를 직접 호출. 자연어 상품 검색 전용.

| 메서드 | 경로 | 요청 | 응답 | 설명 |
|---|---|---|---|---|
| GET | `/query` | `?name=콜라` | `{"zone_id": 3, "zone_name": "음료 코너"}` | 자연어 상품명 검색 |

---

### 채널 E — control_service ↔ Control DB (TCP)

> Control DB가 독립 서비스로 분리. control_service가 TCP로 접근.
> SESSION / CART / CART_ITEM 포함 전체 테이블 관리.

---

### 채널 F — control_service ↔ YOLO (TCP + UDP 하이브리드)

> Pi에서 UDP로 수신한 원시 영상을 control_service가 YOLO로 전달. 인식 결과는 TCP로 반환.

| 방향 | 프로토콜 | 데이터 | 설명 |
|---|---|---|---|
| control → YOLO | **UDP** | 원시 영상 프레임 | 고용량 영상 → 지연 최소화를 위해 UDP |
| YOLO → control | **TCP** | `{"cx": 320, "area": 12000, "confidence": 0.92}` | 인식 결과 → 유실 불허이므로 TCP |

> **YOLO 모델:** 인형 전용 custom-trained YOLOv8. `services/ai_server/yolo/models/` 에 위치.

---

### 채널 G — control_service ↔ shoppinkki packages (ROS 2 DDS, `ROS_DOMAIN_ID=14`)

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
| control → Pi | `/robot_<id>/cmd` | `std_msgs/String` | `{"cmd": "force_terminate"}` — 관제 강제 종료 |
| control → Pi | `/robot_<id>/cmd` | `std_msgs/String` | `{"cmd": "admin_goto", "x": 1.2, "y": 0.8, "theta": 0.0}` — IDLE 상태에서 Nav2 직접 목표 전송 |

---

### 채널 H — control_service ↔ pinky_pro packages (ROS 2 + UDP)

| 방향 | 프로토콜 | 데이터 | 설명 |
|---|---|---|---|
| control → pinky | ROS 2 DDS | `/cmd_vel` (`geometry_msgs/Twist`) | 모터 속도 명령 |
| pinky → control | ROS 2 DDS | `/odom`, `/scan`, `/amcl_pose` | 오도메트리, LiDAR, AMCL 위치 |
| pinky → control | **UDP** | 원시 카메라 프레임 | 영상 스트리밍. 처리 후 채널 F로 YOLO 전달 |

---

## REST API (Pi → control_service, 포트 8080)

BTGuiding / BTReturning 및 Pi가 Control DB를 조회하는 내부 REST API.

| 메서드 | 경로 | 응답 | 설명 |
|---|---|---|---|
| GET | `/zone/<zone_id>/waypoint` | `{"x": 1.2, "y": 0.8, "theta": 0.0}` | zone_id의 Nav2 목표 좌표 조회 |
| GET | `/boundary` | `{"shop_boundary": {...}, "payment_zone": {...}}` | BOUNDARY_CONFIG 전체 조회 |
| GET | `/find_product?query=<str>` | `{"zone_id": 3, "zone_name": "음료 코너"}` | 상품명 검색 |
| GET | `/queue/assign?robot_id=<id>` | `{"zone_id": 140}` | 대기열 position 배정. zone 140(1번) / 141(2번) / 142(3번) 반환 |
| GET | `/events?robot_id=<id>&limit=<n>` | `[{"log_id":1, "event_type":"SESSION_START", ...}]` | EVENT_LOG 조회 |
| POST | `/session` | `{"session_id": "..."}` | 세션 생성 |
| GET | `/session/<session_id>` | `{"is_active": true, "expires_at": "..."}` | 세션 유효성 조회 |
| PATCH | `/session/<session_id>` | `{"ok": true}` | 세션 종료 (`is_active=false`) |
| POST | `/cart/<session_id>/item` | `{"item_id": 5}` | CART_ITEM 추가 |
| DELETE | `/cart/<session_id>/item/<item_id>` | `{"ok": true}` | CART_ITEM 삭제 |
| DELETE | `/cart/<session_id>/items` | `{"ok": true}` | CART_ITEM 전체 삭제 |
