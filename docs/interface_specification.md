# Interface Specification

> 위치: `src/shoppinkki/shoppinkki_interfaces/` (ROS2 패키지)
> 팀원 전원이 공유하는 계약서. 이 파일이 바뀌면 즉시 전원에게 공유.

---

## 왜 필요한가?

팀원 5명이 서로 다른 모듈을 병렬로 개발할 때 **의존성 문제**가 생긴다.

예를 들어 B(SM/BT)는 C(인식)의 `OwnerDetector`를 사용해야 한다. 그런데 C가 아직 구현을 안 끝냈다면 B는 개발을 못 한다.

이를 해결하는 방법이 **인터페이스 + Mock** 패턴이다.

```
인터페이스 = "이 클래스는 이런 함수를 가져야 한다"는 약속 (함수 목록만 정의)
Mock       = 인터페이스를 만족하는 가짜 구현체 (항상 고정된 값을 반환)
```

B는 C의 실제 코드 대신 Mock을 끼워넣고 개발한다. C가 완성되면 Mock을 실제 구현체로 교체한다.

```
Phase 1 (4/1~4/7):  main_node ─── MockOwnerDetector  ← C가 만들기 전
Phase 2 (4/8~):     main_node ─── OwnerDetector       ← C의 실제 구현체로 교체
```

---

## 의존 관계

누가 누구의 인터페이스를 사용하는지:

```
B (main_node) ──uses──► OwnerDetectorInterface   (C가 구현: OwnerDetector 또는 ArucoTracker)
                    ──► QRScannerInterface        (C가 구현)
                    ──► PoseScannerInterface      (C가 구현) ← FACE 모드 전용
                    ──► NavBTInterface            (A가 구현: BT3/4/5)
                    ──► BoundaryMonitorInterface  (A가 구현) ← ARUCO 모드 전용
                    ──► WebAppBridgeInterface     (D가 구현)
```

→ B가 가장 많은 인터페이스를 사용하므로, **B가 Mock을 가장 많이 필요로 한다.**

### 데모 모드별 인터페이스 사용 범위

| 인터페이스 | FACE 모드 (Demo 1) | ARUCO 모드 (Demo 2) |
|---|---|---|
| `OwnerDetectorInterface` | `OwnerDetector` (YOLO+ReID) | `ArucoTracker` (ArUco 마커) |
| `QRScannerInterface` | ✅ | ✅ |
| `PoseScannerInterface` | ✅ (4방향 포즈 스캔) | ❌ (바로 TRACKING 진입) |
| `NavBTInterface` (BT3/4/5) | ❌ (Nav2 없음) | ✅ |
| `BoundaryMonitorInterface` | ❌ | ✅ (결제 구역 감지) |
| `WebAppBridgeInterface` | ✅ | ✅ |

---

## `protocols.py` — 인터페이스 정의

각 인터페이스가 **어떤 함수를 제공해야 하는지**만 정의한다. 실제 동작은 담당자가 구현.

```python
from typing import Protocol, Optional
from dataclasses import dataclass

# ── 공유 데이터 타입 ─────────────────────────────────────────────

# B ↔ C 사이 데이터 타입
@dataclass
class Detection:
    bbox_center_x: float   # 화면에서 감지된 주인의 x 위치 (픽셀)
    bbox_center_y: float
    confidence: float      # ReID 유사도 점수 (0~1, 높을수록 주인일 가능성 높음)

# B ↔ D 사이 데이터 타입
@dataclass
class CartItem:
    item_id: int
    product_name: str
    price: int


# ── C가 구현 → B가 사용 ──────────────────────────────────────────

class OwnerDetectorInterface(Protocol):
    def load_pose_data(self, pose_data: list[dict]) -> None: ...
    # 포즈 스캔 데이터(HSV)를 받아 "이 사람이 주인"이라고 기억

    def get_latest(self) -> Optional[Detection]: ...
    # 가장 최근 프레임에서 주인이 감지됐으면 Detection, 없으면 None

    def run(self, frame, camera_mode: str) -> None: ...
    # 카메라 프레임을 받아서 YOLO 추론 실행. camera_mode != "YOLO"면 아무것도 안 함


class QRScannerInterface(Protocol):
    def start(self, on_scanned: callable, on_timeout: callable) -> None: ...
    # QR 인식 시작. 인식되면 on_scanned(name, price) 호출, 30초 내 실패시 on_timeout()

    def stop(self) -> None: ...


class PoseScannerInterface(Protocol):
    def scan(self, session_id: str, on_direction_done: callable) -> list[dict]: ...
    # 4방향 촬영. 각 방향 완료시 on_direction_done("front") 등 호출
    # 반환: [{session_id, direction, hsv_top_json, hsv_bottom_json}, ...]
    # ⚠️  FACE 모드(Demo 1)에서만 사용. ARUCO 모드에서는 호출되지 않음.


# ── A가 구현 → B가 사용 ──────────────────────────────────────────

class NavBTInterface(Protocol):
    """BT3 / BT4 / BT5가 공통으로 구현해야 하는 인터페이스."""
    def start(self, **kwargs) -> None: ...
    # BT4는 start(zone_id=6) 형태로 kwargs 전달받음

    def stop(self) -> None: ...

    def tick(self) -> str: ...
    # "RUNNING" | "SUCCESS" | "FAILURE"
    # BehaviorTreeRunner가 hz 주기로 반복 호출


class BoundaryMonitorInterface(Protocol):
    def set_callbacks(self, on_zone_out: callable, on_payment_zone: callable) -> None: ...
    # 경계 이탈시 on_zone_out(), 결제 구역 진입시 on_payment_zone() 호출
    # ⚠️  ARUCO 모드(Demo 2)에서만 사용. FACE 모드에서는 MockBoundaryMonitor 유지.

    def update_pose(self, x: float, y: float) -> None: ...
    # /amcl_pose 수신마다 호출. 내부에서 경계 조건 판단


# ── D가 구현 → B가 사용 ──────────────────────────────────────────

class WebAppBridgeInterface(Protocol):
    def broadcast_status(self, mode: str, pos_x: float, pos_y: float, battery: int) -> None: ...
    # 현재 로봇 상태를 웹앱에 연결된 브라우저에 WebSocket으로 전송

    def send_event(self, event_type: str, data: dict) -> None: ...
    # 알람, QR 완료 등 이벤트 발생시 브라우저에 전달

    def add_cart_item(self, product_name: str, price: int) -> None: ...
    # QR 스캔 완료 시 현재 세션의 장바구니에 상품 추가

    def get_cart_items(self) -> list[CartItem]: ...

    def clear_cart(self) -> None: ...

    def terminate_session(self) -> None: ...
    # 귀환 완료 또는 도난 해제 시 세션 만료 + POSE_DATA 삭제
```

---

## `mocks.py` — 가짜 구현체

인터페이스는 만족하지만, 실제 카메라/로봇/DB 없이도 동작하도록 고정값을 반환하는 가짜 클래스.

| Mock 클래스 | 실제 구현 담당 | 동작 |
|---|---|---|
| `MockOwnerDetector(always_detect=True)` | C | `True`면 항상 화면 중앙에서 주인 감지됐다고 반환 |
| `MockOwnerDetector(always_detect=False)` | C | 항상 None 반환 → owner_lost 테스트용 |
| `MockNavBT(result="SUCCESS")` | A | `tick()` 호출 시 즉시 해당 result 반환 |
| `MockNavBT(result="FAILURE")` | A | Nav2 이동 실패 상황 시뮬레이션 |
| `MockWebAppBridge()` | D | 모든 함수가 아무것도 안 함. 웹앱 없이 main_node 단독 테스트 가능 |
| `MockBoundaryMonitor()` | A | 콜백을 절대 호출하지 않음. FACE 모드에서는 Phase 2에도 그대로 유지 |

> `ArucoTracker`는 `OwnerDetectorInterface`를 구현하므로 별도 Mock 불필요.
> ARUCO 모드에서도 `MockOwnerDetector(always_detect=True/False)`로 동일하게 테스트 가능.

**사용 예시 (B의 main_node.py):**

```python
# Phase 1: 로봇 없이 노트북에서 SM 흐름만 테스트
from shoppinkki_interfaces.mocks import MockOwnerDetector, MockNavBT

self.owner_detector = MockOwnerDetector(always_detect=True)
self.bt4 = MockNavBT(result="SUCCESS")

# → BT1이 tick()하면 "주인 감지됨"으로 동작
# → BT4가 tick()하면 "목적지 도착"으로 즉시 동작

# Phase 2 (4/8): TRACKING_MODE에 따라 실제 구현체 선택
TRACKING_MODE = "FACE"  # "FACE" | "ARUCO"

if TRACKING_MODE == "FACE":
    # Demo 1 — 데스크탑: YOLO + ReID
    from shoppinkki_perception.owner_detector import OwnerDetector
    self.owner_detector = OwnerDetector(model_path="models/yolov8n.pt")
    # BT3/4/5, BoundaryMonitor → Mock 그대로 유지 (Nav2 없음)

elif TRACKING_MODE == "ARUCO":
    # Demo 2 — 실제 맵: ArUco 마커 추종
    from shoppinkki_perception.aruco_tracker import ArucoTracker
    self.owner_detector = ArucoTracker()
    # BT3/4/5, BoundaryMonitor → 실제 구현체로 교체
    from shoppinkki_nav.bt.bt4_guiding import BT4Guiding
    from shoppinkki_nav.boundary_monitor import BoundaryMonitor
    self.bt4 = BT4Guiding(nav2_client=..., central_server_url=...)
    self.boundary_monitor = BoundaryMonitor(central_server_url=...)
```

---

## 시스템 아키텍처 교차 검토

> `system_architecture.md` 기준으로 인터페이스 명세가 빠진 부분이나 불일치를 검토한다.

### ✅ 일치하는 항목

| 아키텍처 항목 | 인터페이스 반영 |
|---|---|
| BT1~BT5 공통 `tick()` → "RUNNING"/"SUCCESS"/"FAILURE" | `NavBTInterface.tick()` ✓ |
| BT4 진입 시 `zone_id` 전달 (`sm.trigger('to_guiding', zone_id=zone_id)`) | `NavBTInterface.start(**kwargs)` 로 수신 ✓ |
| `camera_mode = "YOLO"/"QR"/"POSE_SCAN"` SM이 직접 관리 | `OwnerDetectorInterface.run(frame, camera_mode)` ✓ |
| 결제 구역 진입 → 콜백 1회 | `BoundaryMonitorInterface.on_payment_zone` ✓ |
| 도난(THEFT) 해제 → `terminate_session()` | `WebAppBridgeInterface.terminate_session()` ✓ |
| 알람 발생 → 웹앱 브라우저에 전달 | `WebAppBridgeInterface.send_event("alarm", ...)` ✓ |
| heartbeat status → 브라우저 실시간 업데이트 | `WebAppBridgeInterface.broadcast_status(...)` ✓ |
| 포즈 스캔 4방향, 완료마다 부저 신호음 | `PoseScannerInterface.on_direction_done` 콜백 ✓ |

---

### 발견 및 해결된 이슈

#### ✅ 이슈 1: `WebAppBridgeInterface`에 `add_cart_item()` 누락 → **해결**

**문제:**
```
QR 스캔 성공 → on_scanned(name, price) 콜백 → main_node에서 장바구니 추가
```
B가 D의 `db.py`를 직접 import하면 패키지 간 결합이 생긴다.

**해결:** `WebAppBridgeInterface`에 `add_cart_item(product_name, price)` 추가. D가 구현, B가 호출.

---

#### ✅ 이슈 2: `camera_mode` — GUIDING/RETURNING/WAITING/ALARM에서 명시적 처리 → **해결**

**문제:** 해당 상태 진입 시 `camera_mode`를 변경하지 않으면 "YOLO"가 유지되어 불필요한 YOLO 추론이 계속 실행된다.

**해결:** 해당 상태 `on_enter_*`에서 `camera_mode = "NONE"` 명시적으로 설정. `OwnerDetectorInterface.run()`은 `camera_mode != "YOLO"`이면 즉시 return.

```python
# system_architecture.md 카메라 모드 테이블 업데이트
WAITING, GUIDING, RETURNING, ALARM → camera_mode = "NONE"
```

---

#### ✅ 이슈 3: `terminate_session()` 책임 범위 → **명시 완료**

**해결:** `terminate_session()`이 아래를 모두 담당함을 주석에 명시.
- `SESSION.is_active = False`
- `POSE_DATA` 전체 삭제
- 중앙 서버 세션 종료 이벤트 전송

---

#### ✅ 이슈 4: `BoundaryMonitorInterface`에 `load_config()` 없음 → **설계상 의도**

`load_config()`는 초기화 로직이므로 생성자에서 처리. 인터페이스에 포함 불필요.
A 구현 시 `BoundaryMonitor(central_server_url=...)` 생성자에서 반드시 호출.

---

#### ✅ 이슈 5: `find_product_result` 처리 위치 → **인터페이스 범위 밖**

`webapp/ws_handler.py`가 중앙 서버 REST API를 직접 호출하여 처리. `WebAppBridgeInterface`를 통하지 않고 webapp 내부에서 완결. 문제없음.
