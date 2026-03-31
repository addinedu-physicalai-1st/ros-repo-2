# 시스템 아키텍처 (System Architecture)

> **프로젝트:** 쑈삥끼 (ShopPinkki)
> **팀:** 삥끼랩 | 에드인에듀 자율주행 프로젝트 2팀

모든 UR/SR 시나리오를 검증하여 도출한 시스템 아키텍처입니다.

---

## 데모 모드

> 로봇이 작아 실제 맵에서 사람 얼굴을 인식하기 어렵기 때문에, 데모를 두 가지로 나눈다.

| | Demo 1 — 데스크탑 | Demo 2 — 실제 맵 |
|---|---|---|
| **로봇 위치** | 책상 위 (카메라가 사람 얼굴/몸 높이) | 마트 바닥 |
| **추종 방식** | YOLO + ReID (얼굴 + 옷 인식) | ArUco 마커 인형 추종 |
| **포즈 스캔** | ✅ 필요 (옷 HSV 등록) | ❌ 불필요 |
| **QR 스캔 / 장바구니** | ✅ | ✅ |
| **Nav2 / AMCL / 맵** | ❌ (P-Control만) | ✅ |
| **결제 구역** | ❌ | ✅ |
| **설정값** | `TRACKING_MODE = "FACE"` | `TRACKING_MODE = "ARUCO"` |

### 두 모드의 공통점

- `BT1Tracking`은 동일하게 사용. FACE 모드는 `OwnerDetector`가, ARUCO 모드는 `ArucoTracker`가 `Detection`을 반환하며 둘 다 같은 `OwnerDetectorInterface`를 구현한다.
- BT2(탐색), QR 스캔, 장바구니, WebSocket 흐름 동일.

### 세션 시작 흐름 차이

```
FACE 모드:  IDLE → [포즈 스캔 4방향] → pose_scan_done → TRACKING
ARUCO 모드: IDLE → [ArUco 트래킹 바로 시작] → pose_scan_done → TRACKING
            (포즈 스캔 단계 없음. 앱에서 "시작" 버튼 누르면 즉시 진입)
```

---

## 전체 구성 개요

```
┌─────────────────────────────────────┐        ┌──────────────────────────────┐
│              Pi 5 (Pinky Pro)        │        │        중앙 서버 (노트북)      │
│                                     │        │                              │
│  ┌─────────────────────────────┐    │  WS    │  ┌────────────────────────┐  │
│  │   shoppinkki_main_node      │◄───┼────────┼─►│   Flask 서버           │  │
│  │   (SM + BT 통합)            │    │        │  │   WebSocket 서버       │  │
│  └──────────┬──────────────────┘    │  REST  │  │   REST API             │  │
│             │ ROS2 topics           │◄───────┼──│                        │  │
│  ┌──────────▼──────────────────┐    │        │  └───────────┬────────────┘  │
│  │   Nav2 스택                 │    │        │              │               │
│  │   (AMCL, Planner, BT Nav)  │    │        │  ┌───────────▼────────────┐  │
│  └─────────────────────────────┘    │        │  │   DB                  │  │
│                                     │        │  │   USER, CARD, ZONE    │  │
│  ┌─────────────────────────────┐    │        │  │   PRODUCT, BOUNDARY   │  │
│  │   Flask 웹 서버 (사용자용)   │    │        │  │   ROBOT, ALARM_LOG    │  │
│  │   WebSocket 서버            │    │        │  └────────────────────────┘  │
│  │   로컬 SQLite               │    │        │                              │
│  │   SESSION, POSE_DATA        │    │        │  ┌────────────────────────┐  │
│  │   CART, CART_ITEM           │    │        │  │   관제 대시보드 (웹 UI)  │  │
│  └─────────────────────────────┘    │  WS    │  │   맵 오버레이 + 알람    │  │
│                                     │◄───────┼─►│                        │  │
└─────────────────────────────────────┘        └──────────────────────────────┘
          ▲  WebSocket
          │
    스마트폰 (사용자 웹앱)
```

---

## Pi 5 컴포넌트 상세

### 1. `shoppinkki_main_node` (핵심 노드)

SM과 BT를 하나의 ROS2 노드에 통합합니다. SM `on_enter_*` 콜백에서 BT를 직접 시작/중단하고, BT Action 노드가 `sm.trigger()`를 함수 호출로 직접 실행합니다. ROS 서비스 오버헤드 없음.

```
ShoppinkiMainNode (rclpy.Node)
├── ShoppinkiStateMachine (transitions.Machine)
│   ├── states: [IDLE, TRACKING, SEARCHING, WAITING,
│   │            ITEM_ADDING, GUIDING, RETURNING, ALARM]
│   ├── current_alarm: str  ← 알람 종류 저장 (THEFT/BATTERY/TIMEOUT/PAYMENT_ERROR)
│   └── on_enter_* / on_exit_* 콜백
│
├── BehaviorTreeRunner (py_trees)
│   ├── start(tree) / stop()
│   └── BT1~BT5 인스턴스
│
├── camera_mode: "YOLO" | "QR" | "POSE_SCAN"
│   └── 상태 진입/이탈 시 SM이 직접 전환
│
├── [구독] /amcl_pose  → boundary_monitor 콜백
│         → shop_boundary 초과: sm.trigger('zone_out')
│         → 결제 구역(ID 150) 진입: 가상 결제 실행
│
├── [구독] /scan (RPLiDAR)  → BT3 WAITING에서 사용
│
├── [발행] /cmd_vel  → 단일 퍼블리셔 (BT1 P-Control + 장애물 보정)
│
├── [발행] /pinky/mode (std_msgs/String)  → on_enter_* 에서 퍼블리시
│
└── pinkylib polling  → battery_level ≤ 임계값: sm.trigger('battery_low')
```

#### BT별 역할 및 SM 트리거

| BT | 적용 상태 | 동작 | SM 트리거 |
|---|---|---|---|
| BT1 | TRACKING | P-Control 추종 + RPLiDAR 장애물 보정 (30Hz) | `owner_lost` |
| BT2 | SEARCHING | 45° × 8스텝 제자리 회전 탐색 | `owner_found`, `search_failed` |
| BT3 | WAITING | RPLiDAR 통행자 감지 → Nav2 측방 회피 (10Hz) | 없음 (SM 이벤트로만 종료) |
| BT4 | GUIDING | 중앙 서버 Waypoint 조회 → Nav2 이동 | `arrived`, `nav_failed` |
| BT5 | RETURNING | Nav2 카트 출구(ID 140) 복귀 → 세션 종료 | `session_ended`, `nav_failed` |

#### 카메라 모드 전환

카메라(Pi 5 단일)는 상태에 따라 모드가 전환됩니다. SM이 `on_enter_*` / `on_exit_*` 에서 직접 관리합니다.

| 상태 | camera_mode | 처리 로직 |
|---|---|---|
| IDLE | `POSE_SCAN` | 4방향 HSV 특징 추출 |
| TRACKING, SEARCHING | `YOLO` | YOLOv8n 추론 + ReID |
| ITEM_ADDING | `QR` | OpenCV QRCodeDetector |
| WAITING, GUIDING, RETURNING, ALARM | `NONE` | 카메라 루프는 동작하나 `run()`에서 즉시 return. CPU 낭비 없음 |

#### 알람 처리

알람 진입 시 `current_alarm`에 종류를 저장하고, 해제 시 분기합니다.

```python
def on_enter_ALARM(self, event_type, **kwargs):
    self.current_alarm = event_type  # "THEFT" / "BATTERY" / "TIMEOUT" / "PAYMENT_ERROR"
    # BT 중단, /cmd_vel 정지, LED 빨간 점멸, LCD 알람 표시
    # 중앙 서버 WebSocket으로 즉시 알람 전송

def on_dismiss(self):
    if self.current_alarm == "THEFT":
        self.sm.trigger('dismiss_to_idle')   # 세션 강제 종료 + IDLE
    else:
        self.sm.trigger('dismiss_to_waiting')  # WAITING 복귀
```

#### zone_id 전달 (GUIDING 진입 시)

```python
# WebSocket 콜백
zone_id = msg["zone_id"]
self.sm.trigger('to_guiding', zone_id=zone_id)

# SM on_enter
def on_enter_GUIDING(self, zone_id, **kwargs):
    self.bt_runner.start(BT4_Guiding(zone_id=zone_id))
```

---

### 2. Nav2 스택

| 컴포넌트 | 역할 |
|---|---|
| AMCL | 맵 기반 위치 추정 → `/amcl_pose` 발행 |
| nav2_bt_navigator | BT4(GUIDING), BT5(RETURNING) Nav2 Goal 수신 |
| RPLiDAR C1 드라이버 | `/scan` 발행 |

---

### 3. Flask 웹 서버 (사용자용, Pi 5 호스팅)

```
Flask (Pi 5)
├── HTTP Routes
│   ├── GET  /          → QR 접속 진입점. 세션/사용중 분기
│   ├── POST /login     → 중앙 서버 POST /auth/login 프록시
│   ├── POST /register  → 중앙 서버 POST /auth/register 프록시
│   └── GET  /app       → 메인 웹앱 HTML
│
├── WebSocket (사용자 앱 ↔ Pi 5)
│   ├── 수신: mode 전환 명령, find_product, navigate_to, delete_item
│   └── 송신: status(1~2Hz), alarm, arrived, nav_failed, find_product_result
│
└── 로컬 SQLite
    └── SESSION, POSE_DATA, CART, CART_ITEM
```

QR 코드는 Pi 5 시작 시 현재 IP를 동적으로 읽어 생성합니다. 하드코딩 금지. (SR-51)

---

### 4. LCD / LED / 부저

| 컴포넌트 | 구현 | 역할 |
|---|---|---|
| lcd_node | `/pinky/mode` 구독 | 현재 모드 텍스트 + QR 코드 항상 표시 |
| led_node | `/pinky/mode` 구독 | 모드별 LED 색상 제어 |
| buzzer | shoppinkki_main_node 직접 호출 | 포즈 스캔 각 방향 완료 시 알림 |

#### LED 색상표

| 모드 | LED |
|---|---|
| IDLE, WAITING | 파란색 |
| TRACKING | 초록색 |
| SEARCHING | 주황색 |
| ITEM_ADDING | 하늘색(cyan) |
| GUIDING | 노란색 |
| RETURNING | 보라색 |
| ALARM | 빨간색 점멸 |

---

## 중앙 서버 컴포넌트 상세

### Flask 서버

```
Flask (중앙 서버)
├── REST API (Pi 5에서 호출)
│   ├── POST /auth/login
│   ├── POST /auth/register          ← USER + CARD 저장
│   ├── GET  /product?name=<상품명>  ← PRODUCT 테이블 조회 → zone_id, zone_name 응답
│   ├── GET  /zone/<zone_id>/waypoint ← ZONE 테이블 조회 → Waypoint 좌표 응답
│   └── GET  /boundary               ← BOUNDARY_CONFIG 조회 → shop_boundary, payment_zone
│
└── WebSocket 서버
    ├── Pi 5 연결 수신
    │   ├── 수신: heartbeat (1~2Hz) → ROBOT 테이블 갱신
    │   ├── 수신: alarm (즉시) → ALARM_LOG 기록 + 대시보드 전파
    │   └── 송신: dismiss_alarm → 해당 Pi 5로 전송
    │
    └── 관제 대시보드 연결 수신
        ├── 송신: 전체 로봇 상태 (ROBOT 테이블 기반)
        └── 수신: dismiss_alarm 요청 → 해당 Pi 5 WebSocket으로 전달
```

---

## 통신 메시지 정의

### 채널 A: 사용자 앱 ↔ Pi 5 WebSocket

| 방향 | 메시지 | 설명 |
|---|---|---|
| Pi5 → 앱 | `{"type": "status", "mode": "TRACKING", "pos_x": 1.2, "pos_y": 0.8, "battery": 72}` | 1~2Hz 주기 상태 전송 |
| 앱 → Pi5 | `{"cmd": "mode", "value": "WAITING"}` | 모드 전환 (WAITING/TRACKING/RETURNING/ITEM_ADDING) |
| 앱 → Pi5 | `{"cmd": "find_product", "product": "콜라"}` | 물건 찾기 요청 |
| Pi5 → 앱 | `{"type": "find_product_result", "zone_id": 6, "zone_name": "음료"}` | 물건 위치 응답 |
| 앱 → Pi5 | `{"cmd": "navigate_to", "zone_id": 6}` | 안내 요청 |
| 앱 → Pi5 | `{"cmd": "delete_item", "item_id": 3}` | 장바구니 삭제 |
| Pi5 → 앱 | `{"type": "arrived", "zone_name": "음료"}` | 목적지 도착 알림 |
| Pi5 → 앱 | `{"type": "nav_failed"}` | 안내 실패 알림 |
| Pi5 → 앱 | `{"type": "alarm", "event": "PAYMENT_ERROR"}` | 알람 발생 알림 |
| Pi5 → 앱 | `{"type": "payment_done"}` | 결제 완료 알림 |

### 채널 B: Pi 5 ↔ 중앙 서버 WebSocket

| 방향 | 메시지 | 설명 |
|---|---|---|
| Pi5 → 서버 | `{"type": "heartbeat", "robot_id": 54, "mode": "TRACKING", "pos_x": 1.2, "pos_y": 0.8, "battery": 72}` | 1~2Hz 주기. 연결 끊김 시 자동 재연결 |
| Pi5 → 서버 | `{"type": "alarm", "robot_id": 54, "event": "THEFT", "user_id": "hong123"}` | 알람 즉시 전송 |
| 서버 → Pi5 | `{"type": "dismiss_alarm", "event": "THEFT"}` | 관제 대시보드 해제 명령 |

---

## 세션 흐름

```
[QR 스캔] → GET http://<Pi_IP>:<PORT>/
    ↓
[SESSION.is_active == True?]
    Yes → "현재 사용 중" 페이지 반환 (UR-21)
    No  ↓
[세션 쿠키 유효? expires_at > now]
    Yes → 메인화면 (UR-04)
    No  ↓
[로그인 / 회원가입]
    → Pi5 → POST /auth/login or /auth/register → 중앙 서버
    → Pi5 로컬 SESSION 생성 (is_active=True)
    ↓
[포즈 스캔] (매 사용마다)
    → camera_mode = "POSE_SCAN"
    → front → right → back → left (각 완료 시 부저)
    → POSE_DATA 4개 저장
    → SM.trigger('pose_scan_done') → IDLE → TRACKING
    ↓
[메인화면 — 쇼핑 보조]
    ↓
["보내주기"] 선택
    → CART_ITEM 존재 시 앱에 알림 후 차단
    → 비어있으면 SM.trigger('to_returning')
    ↓
[BT5: Nav2 카트 출구(ID 140) 이동]
    → 도착: SESSION.is_active=False, expires_at=now
    →       POSE_DATA 전체 삭제
    →       중앙 서버에 세션 종료 이벤트 전송
    →       SM.trigger('session_ended') → RETURNING → IDLE
```

---

## 결제 흐름

```
boundary_monitor_node: /amcl_pose 구독
    ↓
AMCL pose가 결제 구역(ID 150) 진입 감지
    ↓
CART_ITEM 존재 여부 확인
    비어있음 → 스킵 (그냥 통과)
    있음     ↓
        [가상 결제 실행 — CARD 정보 사용, 데모용]
            성공 → CART_ITEM 전체 삭제
                   앱 → {"type": "payment_done"} 전송
                   상태 유지 (TRACKING 유지)
            실패 → SM.trigger('payment_error') → ALARM
```

---

## 데이터 저장 위치 요약

| 엔티티 | 저장 위치 | 비고 |
|---|---|---|
| USER, CARD | 중앙 서버 DB | 어느 Pinky에서든 동일 계정 사용 |
| ZONE, PRODUCT | 중앙 서버 DB | Waypoint 좌표, 상품→구역 매핑 |
| BOUNDARY_CONFIG | 중앙 서버 DB | 도난 경계, 결제 구역 좌표 |
| ROBOT | 중앙 서버 DB | Pi 5 heartbeat로 갱신 |
| ALARM_LOG | 중앙 서버 DB | 알람 발생/해제 이력 |
| SESSION | Pi 5 로컬 | 활성 세션 여부 관리 |
| POSE_DATA | Pi 5 로컬 | 세션 종료/도난 해제 시 삭제 |
| CART, CART_ITEM | Pi 5 로컬 | Flask 웹앱에서 관리 |
