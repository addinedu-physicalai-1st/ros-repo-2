# 구현 계획

> 3/31 ~ 4/13 | 팀원: A(Nav2/주행) B(SM/BT/HW) C(인식/카메라) D(웹앱) E(중앙서버)

---

## 전체 폴더 구조

```
ros_ws/
├── src/                                    ← ROS2 패키지만 (colcon 빌드 대상)
│   ├── pinky_pro/                          ← 기존 패키지 (수정 금지)
│   │   └── pinky_navigation/
│   │       └── map/
│   │           ├── shop.pgm               ← 기존 마트 맵 (A가 복사해서 사용)
│   │           └── shop.yaml
│   │
│   └── shoppinkki/                         ← 쑈삥끼 ROS2 패키지
│       ├── shoppinkki_interfaces/          ← 인터페이스 명세 (전원 공유)
│       ├── shoppinkki_core/                ← 메인 노드 (SM + BT1/2 + HW + WS Client)
│       ├── shoppinkki_nav/                 ← Nav2 주행 (BT3/4/5 + 경계 감시)
│       └── shoppinkki_perception/          ← 인식 (YOLO + ReID + QR + 포즈 스캔)
│
├── services/                               ← 비 ROS2 서비스 (독립 실행)
│   ├── webapp/                             ← Pi 5 Flask 웹앱 (포트 5000)
│   └── central_server/                     ← 노트북 Flask 중앙 서버 (포트 8080)
│
└── docs/
    ├── user_requirements.md
    ├── system_architecture.md
    └── plan/
        └── implementation_plan.md          ← 이 파일
```

---

## 패키지 구성

| 패키지 | 실행 위치 | 담당 | 설명 |
|---|---|---|---|
| 위치 | 패키지 | 실행 위치 | 담당 | 설명 |
|---|---|---|---|---|
| `src/shoppinkki/` | `shoppinkki_interfaces` | — | 전원 | Protocol ABC + Mock 클래스. ROS2 패키지 |
| `src/shoppinkki/` | `shoppinkki_core` | Pi 5 | B | 단일 ROS2 노드 (`shoppinkki_main_node`). SM + BT1/2 + HW 제어 + 중앙서버 WS |
| `src/shoppinkki/` | `shoppinkki_nav` | Pi 5 | A | Nav2 파라미터, BT3/4/5, 경계 감시. ROS2 패키지 |
| `src/shoppinkki/` | `shoppinkki_perception` | Pi 5 | C | 카메라 인식 모듈. ROS2 패키지 |
| `services/` | `webapp` | Pi 5 | D | Flask 웹앱 (포트 5000). 비 ROS2 독립 실행 |
| `services/` | `central_server` | 노트북 | E | Flask 중앙 서버 (포트 8080). 비 ROS2 독립 실행 |

---

## Interface Specification

> 📄 **별도 문서로 분리됨:** [`docs/interface_specification.md`](../interface_specification.md)
>
> 인터페이스 정의(`protocols.py`), Mock 사용법(`mocks.py`), 시스템 아키텍처 교차 검토 결과를 포함한다.

### 핵심 의존 관계 (요약)

```
B (main_node) ──uses──► OwnerDetectorInterface   (C가 구현: OwnerDetector 또는 ArucoTracker)
                    ──► QRScannerInterface        (C가 구현)
                    ──► PoseScannerInterface      (C가 구현) ← FACE 모드 전용
                    ──► NavBTInterface            (A가 구현: BT3/4/5) ← ARUCO 모드 전용
                    ──► BoundaryMonitorInterface  (A가 구현) ← ARUCO 모드 전용
                    ──► WebAppBridgeInterface     (D가 구현)
```

### 아키텍처 검토에서 발견된 변경 사항

| 항목 | 내용 |
|---|---|
| `WebAppBridgeInterface.add_cart_item()` 추가 | QR 스캔 완료 시 B → D로 장바구니 추가. 없으면 B가 D의 `db.py`를 직접 import해야 하는 결합 발생 |
| `terminate_session()` 책임 명시 | SESSION 비활성화 + POSE_DATA 삭제를 D가 함께 처리 |
| `camera_mode` GUIDING/RETURNING 중 처리 | 기능상 문제없으나 Pi5 CPU 부하 발생. FPS 저하 시 해당 상태 진입 시 `camera_mode = "IDLE"` 추가 검토 |

---

## 기능별 구현 체크리스트

---

### 1. shoppinkki_interfaces

- [ ] `protocols.py` — 전체 인터페이스 정의 완료 (Detection, CartItem 데이터 클래스 포함)
- [ ] `mocks.py` — Mock 구현체 완료
  - [ ] `MockOwnerDetector(always_detect)` — True/False로 주인 감지 여부 제어
  - [ ] `MockNavBT(result)` — "SUCCESS"/"FAILURE"/"RUNNING" 즉시 반환
  - [ ] `MockWebAppBridge()` — 모든 메서드 no-op (`add_cart_item` 포함)
  - [ ] `MockBoundaryMonitor()` — 콜백 절대 호출하지 않음
- [ ] `package.xml` + `setup.py` 생성

---

### 2. shoppinkki_core

> 단일 ROS2 노드. SM + BT를 통합 관리.

#### 패키지 구조

```
shoppinkki_core/
├── package.xml
├── setup.py
├── shoppinkki_core/
│   ├── main_node.py            ← ROS2 노드 진입점 (전체 와이어링)
│   ├── state_machine.py        ← transitions 기반 SM
│   ├── bt_runner.py            ← BT 스레드 관리
│   ├── bt/
│   │   ├── bt1_tracking.py     ← P-Control 주인 추종 + RPLiDAR 보정
│   │   └── bt2_searching.py    ← 45°×8스텝 제자리 회전 탐색
│   ├── hw/
│   │   ├── led_controller.py
│   │   ├── lcd_controller.py   ← QR 코드 동적 생성 표시
│   │   └── buzzer.py
│   └── ws/
│       └── central_client.py   ← 중앙 서버 WebSocket 클라이언트
└── test/
    ├── test_state_machine.py
    ├── test_bt_runner.py
    ├── test_bt1_tracking.py
    └── test_bt2_searching.py
```

#### 데모 모드 설정

- [ ] `config.py` — `TRACKING_MODE = "FACE" | "ARUCO"` 설정 (기본값: `"FACE"`)
  - `"FACE"`: YOLO+ReID, 포즈 스캔 포함, Nav2/AMCL/결제 구역 없음 (Desktop Demo)
  - `"ARUCO"`: ArUco 마커, 포즈 스캔 없음, Nav2/AMCL/결제 구역 있음 (Map Demo)
- [ ] `main_node.py` — `TRACKING_MODE`에 따라 실제 구현체 선택 (Phase 2 교체 시)

#### State Machine

- [ ] `state_machine.py` — 8개 상태 선언 (`IDLE`, `TRACKING`, `SEARCHING`, `WAITING`, `ITEM_ADDING`, `GUIDING`, `RETURNING`, `ALARM`)
- [ ] 전체 전환 트리거 구현 (`pose_scan_done`, `owner_lost`, `owner_found`, `search_failed`, `to_item_adding`, `to_guiding`, `to_waiting`, `to_tracking`, `to_returning`, `zone_out`, `payment_error`, `qr_scanned`, `item_cancelled`, `arrived`, `nav_failed_guide`, `session_ended`, `nav_failed_return`, `dismiss_to_waiting`, `dismiss_to_idle`, `battery_low`, `timeout`)
- [ ] `current_alarm` 필드 (알람 해제 분기용: `"THEFT"` → `dismiss_to_idle`, 그 외 → `dismiss_to_waiting`)
- [ ] `test_state_machine.py` 전체 통과 (전체 세션 흐름, 알람 해제 2가지 경로, 유효하지 않은 전환 오류)

#### Behavior Tree Runner

- [ ] `bt_runner.py` — BT를 별도 스레드에서 hz 주기로 tick, SUCCESS/FAILURE 시 `on_result` 콜백 호출
- [ ] `stop()` 호출 시 스레드 안전 종료

#### BT1 — 주인 추종

- [ ] `bt1_tracking.py` — `OwnerDetectorInterface.get_latest()` 호출 → P-Control 각속도 계산
- [ ] RPLiDAR `/scan` 전방 장애물 감지 → 감속 로직
- [ ] N프레임 연속 미검출 시 `"FAILURE"` 반환 (→ SM: `owner_lost`)
- [ ] `test_bt1_tracking.py` 통과 (MockOwnerDetector 사용)

#### BT2 — 탐색

- [ ] `bt2_searching.py` — 45°×8스텝 제자리 회전, 매 스텝마다 `OwnerDetectorInterface.get_latest()` 확인
- [ ] 8스텝 내 발견 시 `"SUCCESS"`, 못 찾으면 `"FAILURE"`
- [ ] `test_bt2_searching.py` 통과

#### HW 컨트롤러

- [ ] `led_controller.py` — 모드별 색상 매핑 (IDLE:파랑, TRACKING:초록, SEARCHING:주황, WAITING:파랑, ITEM_ADDING:청록, GUIDING:노랑, RETURNING:보라, ALARM:빨강 점멸)
- [ ] `lcd_controller.py` — 상단: 모드 텍스트, 하단: 동적 IP로 QR 코드 생성 (`SR-51`)
- [ ] `buzzer.py` — 포즈 스캔 방향 전환 시 신호음

#### main_node 와이어링

- [ ] `main_node.py` 뼈대 — Phase 1에서 전체 Mock으로 와이어링
- [ ] `on_enter_IDLE` — bt_runner 정지
  - FACE 모드: `camera_mode = "POSE_SCAN"` → PoseScanner 시작 → `pose_scan_done` 트리거
  - ARUCO 모드: `camera_mode = "YOLO"` → ArucoTracker 바로 시작 → `pose_scan_done` 트리거 (스캔 없이 즉시)
- [ ] `on_enter_TRACKING` — `camera_mode = "YOLO"`, BT1 시작
- [ ] `on_enter_SEARCHING` — BT2 시작 (`camera_mode` 유지: "YOLO")
- [ ] `on_enter_WAITING` — `camera_mode = "NONE"`, 타이머 시작 (5분 후 `timeout` 트리거)
  - ARUCO 모드 전용: BT3 시작 (FACE 모드에서는 BT3 없음)
- [ ] `on_enter_ITEM_ADDING` — bt_runner 정지, `camera_mode = "QR"`, QRScanner 시작
- [ ] `on_exit_ITEM_ADDING` — QRScanner 정지, `camera_mode = "YOLO"`
- [ ] `on_enter_GUIDING` — `camera_mode = "NONE"`, BT4 시작 (`zone_id` kwargs 전달) ← ARUCO 모드 전용
- [ ] `on_enter_RETURNING` — `camera_mode = "NONE"`, BT5 시작 ← ARUCO 모드 전용
- [ ] `on_enter_ALARM` — `camera_mode = "NONE"`, bt_runner 정지, `current_alarm` 저장, 로봇 정지, `central_client.send_alarm()` 호출
- [ ] `dismiss_alarm()` — `current_alarm == "THEFT"` → `webapp_bridge.terminate_session()` (SESSION 비활성화 + POSE_DATA 삭제) + `dismiss_to_idle`, 그 외 → `dismiss_to_waiting`
- [ ] heartbeat 타이머 (2초 주기) — `central_client.send_heartbeat()` 호출
- [ ] 카메라 루프 스레드 — 매 프레임 `owner_detector.run(frame, camera_mode)` 호출

#### 중앙 서버 WS 클라이언트

- [ ] `central_client.py` — `/robot` namespace, `socketio.Client` 사용
- [ ] `send_heartbeat(mode, pos_x, pos_y, battery)` 구현
- [ ] `send_alarm(event_type, user_id)` 구현
- [ ] `dismiss_alarm` 수신 시 `node.dismiss_alarm()` 호출
- [ ] 연결 끊김 시 3초 후 자동 재연결

#### Mock → 실물 교체 (4/8)

- [ ] `MockOwnerDetector` → `OwnerDetector` (C의 구현체)
- [ ] `MockNavBT(bt3/4/5)` → `BT3Waiting`, `BT4Guiding`, `BT5Returning` (A의 구현체)
- [ ] `MockWebAppBridge` → `WebAppBridge` (D의 구현체)
- [ ] `MockBoundaryMonitor` → `BoundaryMonitor` (A의 구현체)

---

### 3. shoppinkki_nav

> Nav2 파라미터 + BT3/4/5 + 경계 감시

#### 패키지 구조

```
shoppinkki_nav/
├── package.xml
├── setup.py
├── shoppinkki_nav/
│   ├── boundary_monitor.py     ← /amcl_pose 감시 → 도난/결제 감지
│   └── bt/
│       ├── bt3_waiting.py      ← RPLiDAR 통행자 감지 → 측방 회피
│       ├── bt4_guiding.py      ← Waypoint 조회 → Nav2 목표 이동
│       └── bt5_returning.py    ← zone 140 (카트 출구) 귀환
├── config/
│   └── nav2_params.yaml        ← AMCL + DWB/MPPI 파라미터
├── maps/
│   ├── shop.pgm                ← pinky_navigation/map/shop.pgm 복사
│   └── shop.yaml               ← resolution: 0.010, origin: [-0.293, -1.660, 0]
├── launch/
│   └── navigation.launch.py
└── test/
    ├── test_boundary_monitor.py
    └── test_bt4_guiding.py
```

#### Nav2 설정

- [ ] `maps/shop.pgm` + `maps/shop.yaml` 복사 (pinky_navigation/map에서 가져옴)
- [ ] `nav2_params.yaml` — 기존 pinky_navigation/params 참고, 마트 속도 제한 (`max_vel_x: 0.3`) 조정
- [ ] `navigation.launch.py` — map_server + AMCL + Nav2 전체 스택 기동
- [ ] Gazebo 시뮬레이션 (`pinky_gz_sim`)에서 Nav2 Goal 전송 → 이동 동작 확인

#### BT3 — 대기 중 통행자 회피

- [ ] `bt3_waiting.py` — `/scan` 전방 임계 거리 이내 감지 시 좌우 여유 비교 → 넓은 쪽으로 Nav2 측방 이동
- [ ] SM 이벤트로만 종료 (BT3 자체는 항상 `"RUNNING"` 반환)

#### BT4 — 구역 안내 이동

- [ ] `bt4_guiding.py` — `start(zone_id)` 시 중앙 서버 `GET /zone/<id>/waypoint` 호출 → Nav2 Goal 전송
- [ ] Nav2 결과에 따라 `"SUCCESS"` / `"FAILURE"` 반환
- [ ] `test_bt4_guiding.py` 통과 (Mock Nav2 클라이언트 사용)

#### BT5 — 귀환

- [ ] `bt5_returning.py` — `GET /zone/140/waypoint` 호출 → 카트 출구로 이동
- [ ] 성공 시 `"SUCCESS"` (→ SM: `session_ended`), 실패 시 `"FAILURE"` (→ SM: `nav_failed_return` → ALARM)

#### Boundary Monitor

- [ ] `boundary_monitor.py` — `load_config(central_server_url)` 시 `GET /boundary` 호출 → 좌표 저장
- [ ] `update_pose(x, y)` — 마트 경계 이탈 시 `on_zone_out()` 콜백 (→ SM: `zone_out`)
- [ ] `update_pose(x, y)` — 결제 구역 진입 시 `on_payment_zone()` 콜백 1회만 발생
- [ ] `test_boundary_monitor.py` 통과
- [ ] Waypoint 실측 (Robot 1, ZONE 1~8 + 130/140/150) → E에게 전달
- [ ] BOUNDARY_CONFIG 실측 (shop_boundary, payment_zone) → E에게 전달

---

### 4. shoppinkki_perception

> 카메라 기반 인식 모듈

#### 패키지 구조

```
shoppinkki_perception/
├── package.xml
├── setup.py
├── shoppinkki_perception/
│   ├── owner_detector.py       ← YOLOv8n + ReID (FACE 모드, 스레드 세이프)
│   ├── aruco_tracker.py        ← ArUco 마커 추종 (ARUCO 모드, OwnerDetectorInterface 구현)
│   ├── reid_matcher.py         ← HSV 히스토그램 Bhattacharyya 비교
│   ├── pose_scanner.py         ← 4방향 촬영 → hsv_top/bottom 추출 (FACE 모드 전용)
│   └── qr_scanner.py           ← OpenCV QRCodeDetector, 30초 타임아웃
├── models/
│   └── yolov8n.pt              ← (FPS < 10 이면 yolov8n_ncnn_model/로 변환)
├── scripts/
│   ├── measure_fps.py          ← Pi 5 FPS 측정
│   └── reid_experiment.py      ← ReID 임계값 실험
└── test/
    ├── fixtures/
    │   ├── person_front.jpg    ← 테스트용 인물 이미지
    │   ├── sample_video.mp4    ← Robot 1에서 녹화한 추종 테스트 영상
    │   ├── aruco_doll.jpg      ← 테스트용 ArUco 마커 인형 이미지
    │   └── qr_cola.png         ← 테스트용 QR 이미지
    ├── test_reid_matcher.py
    ├── test_qr_scanner.py
    ├── test_owner_detector.py
    └── test_aruco_tracker.py
```

#### YOLOv8n 성능 확인

- [ ] `scripts/measure_fps.py` — Pi 5에서 YOLOv8n FPS 측정 (Robot 1 사용)
- [ ] FPS < 10 이면 NCNN 변환 (`yolo export format=ncnn`)

#### ReID Matcher

- [ ] `reid_matcher.py` — HSV 히스토그램 추출 (`16×16 bins`, H×S), Bhattacharyya 거리 비교
- [ ] `extract_hsv_histogram(image, region)` — `region`: `"top"` (상체) / `"bottom"` (하체)
- [ ] `test_reid_matcher.py` 통과 (같은 사람 → score > 0.8)

#### Pose Scanner

- [ ] `pose_scanner.py` — YOLO로 사람 bbox 검출 후 HSV 히스토그램 추출
- [ ] 4방향 (`front`, `right`, `back`, `left`) 순서로 촬영
- [ ] 방향 완료마다 `on_direction_done(direction)` 콜백 호출 (→ buzzer 신호음)
- [ ] `test/fixtures/sample_video.mp4` 녹화 완료 (Robot 1, 최소 30초)

#### QR Scanner

- [ ] `qr_scanner.py` — `cv2.QRCodeDetector` 사용
- [ ] QR 형식: `"상품명:가격"` 파싱 → `on_scanned(name, price)` 콜백
- [ ] 30초 내 미인식 시 `on_timeout()` 콜백
- [ ] 유효하지 않은 QR 형식 → 무시하고 계속 스캔
- [ ] `test/fixtures/qr_cola.png` 등 테스트용 QR 이미지 생성
- [ ] `test_qr_scanner.py` 통과

#### Owner Detector — FACE 모드 (Demo 1)

- [ ] `owner_detector.py` — `YOLO` + `ReIDMatcher` 통합, 스레드 세이프 (`threading.Lock`)
- [ ] `run(frame, "YOLO")` — 모든 사람 bbox 검출 → ReID score 최고인 사람을 `_latest`에 저장
- [ ] `run(frame, "QR"/"POSE_SCAN"/"NONE")` — 아무 동작 안 함 (None 유지)
- [ ] `REID_THRESHOLD` 확정 (Robot 2에서 실험, 기본값 0.6)

#### ArUco Tracker — ARUCO 모드 (Demo 2)

- [ ] `aruco_tracker.py` — `OwnerDetectorInterface` 구현 (`load_pose_data`, `get_latest`, `run`)
- [ ] `cv2.aruco.detectMarkers()` 사용, 인형에 부착한 마커 ID 고정 (예: ID=0)
- [ ] 마커 검출 시 bbox 중심 좌표를 `Detection(bbox_center_x, bbox_center_y, confidence=1.0)`으로 반환
- [ ] `load_pose_data()` — no-op (포즈 데이터 불필요)
- [ ] `run(frame, "YOLO")` 호출 시 동작, 나머지 `camera_mode`에서는 즉시 return
- [ ] `test_aruco_tracker.py` 통과 (테스트 이미지에서 마커 검출 확인)

---

### 5. webapp

> Pi 5에서 실행되는 Flask 웹앱 (포트 5000)

#### 위치: `services/webapp/`

```
services/webapp/
├── app.py                      ← Flask + SocketIO 진입점
├── config.py                   ← CENTRAL_SERVER_URL, ROBOT_ID 등
├── db.py                       ← 로컬 SQLite CRUD
├── webapp_bridge.py            ← WebAppBridgeInterface 구현 (B가 사용)
├── ws_handler.py               ← 앱↔Pi5 WebSocket 핸들러
├── routes/
│   ├── auth.py                 ← GET /, POST /login
│   ├── main.py                 ← GET /app/main, GET /app/pose_scan
│   ├── cart.py                 ← GET /app/cart
│   └── alarm.py                ← POST /alarm/dismiss
├── templates/
│   ├── base.html
│   ├── blocked.html            ← "현재 사용 중" (UR-21)
│   ├── login.html
│   ├── pose_scan.html          ← 4방향 촬영 안내
│   ├── main.html               ← 맵 + 위치 + 모드
│   ├── cart.html               ← 장바구니
│   └── alarm_dismiss.html
├── static/
│   ├── js/
│   │   ├── ws_client.js        ← WebSocket 연결/메시지
│   │   ├── map_overlay.js      ← 맵 좌표→픽셀 변환 + 로봇 마커
│   │   └── stt.js              ← Web Speech API (ko-KR)
│   └── img/
│       └── shop_map.png
├── requirements.txt            ← flask, flask-socketio, requests
└── tests/
    ├── test_auth.py
    ├── test_cart.py
    └── test_ws.py
```

#### 로컬 SQLite 스키마

```
session (session_id, robot_id, user_id, created_at, expires_at, is_active)
pose_data (pose_id, session_id, direction, hsv_top_json, hsv_bottom_json)
cart (cart_id, session_id)
cart_item (item_id, cart_id, product_name, price, scanned_at)
```

#### Flask 앱 기반

- [ ] `app.py` — Flask + SocketIO 초기화, Blueprint 등록, `init_db()` 호출
- [ ] `config.py` — `CENTRAL_SERVER_URL`, `ROBOT_ID` 설정

#### 인증 / 세션

- [ ] `db.py` — 전체 CRUD 함수 구현 (`is_robot_in_use`, `create_session`, `terminate_session`, `save_pose_data`, `create_cart`, `add_cart_item`, `delete_cart_item`, `get_cart_items`, `cart_is_empty` 등)
- [ ] `GET /` — 3가지 분기: 사용 중 → `blocked.html` / 유효 세션 → `/app/main` / 그 외 → `login.html`
- [ ] `POST /login` — 중앙 서버 `/auth/login` 호출 → 세션 생성 + 쿠키 설정 → `/app/pose_scan` 리다이렉트
- [ ] `test_auth.py` 통과

#### 화면 UI

- [ ] `login.html` — ID/PW 입력 폼
- [ ] `blocked.html` — "현재 사용 중" 메시지 (UR-21)
- [ ] `pose_scan.html` — 4방향 상태 표시 + [준비됐어요] 버튼 + WebSocket 완료 수신 시 메인 이동
- [ ] `main.html` — 모드/배터리 + 맵 이미지 + 로봇 위치 점 + [대기 모드] [장바구니] 버튼
- [ ] `cart.html` — 아이템 목록 + 합계 + [물건 추가] [물건 찾기] [보내주기]

#### JS

- [ ] `ws_client.js` — SocketIO 연결, `status` → 모드/배터리 업데이트, `alarm` → 알람 UI
- [ ] `map_overlay.js` — `shop.yaml` 기준 맵 좌표 → 픽셀 변환 (`MAP_RESOLUTION=0.01`, `ORIGIN=[-0.293,-1.660]`), 로봇 마커 업데이트
- [ ] `stt.js` — `webkitSpeechRecognition` (ko-KR), 결과 → `find_product` 명령 전송

#### WebSocket 핸들러

- [ ] `ws_handler.py` — `get_cart`, `delete_item`, `mode` (RETURNING 시 장바구니 확인), `find_product`, `navigate_to` 처리
- [ ] 장바구니 비어있지 않을 때 `RETURNING` 차단 → `error` 메시지 반환
- [ ] `test_ws.py` 통과

#### WebApp Bridge

- [ ] `webapp_bridge.py` — `WebAppBridgeInterface` 구현 (`broadcast_status`, `send_event`, `add_cart_item`, `get_cart_items`, `clear_cart`, `terminate_session` — 세션 만료 + POSE_DATA 삭제 포함)
- [ ] B의 `main_node.py`에 연결 완료 (4/8)

---

### 6. central_server

> 노트북에서 실행되는 중앙 Flask 서버 (포트 8080)

#### 위치: `services/central_server/`

```
services/central_server/
├── app.py                      ← Flask + SocketIO 진입점
├── config.py
├── db.py                       ← 중앙 SQLite CRUD
├── ws_server.py                ← WebSocket 핸들러 (/robot + /dashboard namespace)
├── routes/
│   ├── auth.py                 ← POST /auth/login, POST /auth/register
│   ├── product.py              ← GET /product?name=
│   ├── zone.py                 ← GET /zone/<id>/waypoint
│   └── boundary.py             ← GET /boundary
├── seeds/
│   └── seed_data.py            ← 초기 데이터 (ZONE, PRODUCT, BOUNDARY_CONFIG)
├── dashboard/
│   ├── index.html              ← 관제 대시보드
│   ├── style.css
│   └── app.js                  ← WebSocket + 맵 오버레이 + 알람 UI
├── requirements.txt            ← flask, flask-socketio, werkzeug
└── tests/
    ├── test_api.py
    └── test_ws.py
```

#### 중앙 SQLite 스키마

```
user (user_id, password_hash, name, phone)
card (card_id, user_id, card_number_masked, card_holder_name)
zone (zone_id, zone_name, zone_type, waypoint_x, waypoint_y, waypoint_theta)
product (product_id, product_name, zone_id)
boundary_config (config_id, description, x_min, x_max, y_min, y_max)
robot (robot_id, ip_address, current_mode, pos_x, pos_y, battery_level, last_seen)
alarm_log (log_id, robot_id, user_id, event_type, occurred_at, resolved_at)
```

#### REST API

- [ ] `db.py` — 전체 CRUD 함수 구현
- [ ] `POST /auth/login` — `werkzeug` password hash 검증
- [ ] `POST /auth/register` — 사용자 + 카드 정보 저장 (UR-02b, LOW)
- [ ] `GET /product?name=` — 상품명 검색 → `{zone_id, zone_name}` 반환
- [ ] `GET /zone/<id>/waypoint` — Waypoint 반환 (초기: null, A 실측 후 업데이트)
- [ ] `GET /boundary` — `{shop_boundary, payment_zone}` 반환
- [ ] `seeds/seed_data.py` — ZONE 11개, PRODUCT 18개, BOUNDARY_CONFIG 2개 입력
- [ ] `test_api.py` 통과 (register/login, product, boundary)

#### WebSocket 서버

- [ ] `ws_server.py` — `robot_sessions = {}` (robot_id → SID 매핑)
- [ ] `/robot` namespace — `register` 이벤트로 robot_sessions 등록
- [ ] `heartbeat` 수신 → `upsert_robot()` → `/dashboard` 브로드캐스트
- [ ] `alarm` 수신 → `create_alarm_log()` → `/dashboard` 브로드캐스트
- [ ] `dismiss_alarm` (대시보드 → 서버) — `resolve_alarm()` + 해당 Pi5에 해제 명령 전송
- [ ] 연결 끊김 시 `robot_sessions`에서 해당 robot_id 제거
- [ ] `test_ws.py` 통과 (heartbeat, alarm 전파, dismiss 흐름)

#### 관제 대시보드 (UR-23a)

- [ ] `dashboard/index.html` — 맵 패널 + 알람 패널 레이아웃
- [ ] `dashboard/app.js` — 맵 좌표→픽셀 변환, 로봇 마커 동적 업데이트
- [ ] 알람 발생 시 알람 패널 추가 + [해제] 버튼
- [ ] [해제] 클릭 → `dismiss_alarm` 전송 → 알람 UI 제거
- [ ] 브라우저에서 실제 heartbeat + 알람 흐름 확인

#### Waypoint 입력

- [ ] A의 실측값 수신 후 ZONE Waypoint DB 업데이트
- [ ] BOUNDARY_CONFIG 실측값 업데이트
- [ ] `/zone/<id>/waypoint` 및 `/boundary` API 실측값 반환 확인

---

### 7. 통합 테스트

#### WebSocket 3채널 검증

- [ ] 브라우저 ↔ Pi5 WebSocket 연결 확인 (SocketIO, 포트 5000)
- [ ] Pi5 ↔ 중앙 서버 WebSocket 연결 확인 (`/robot` namespace, 포트 8080)
- [ ] heartbeat end-to-end (Pi5 → 서버 → 대시보드) 확인
- [ ] alarm → dismiss 전체 흐름 (대시보드 → 서버 → Pi5 → SM) 확인

#### 시나리오 테스트 — Demo 1 (FACE 모드, Desktop)

- [ ] QR 접속 → 로그인 → 포즈 스캔 4방향 → TRACKING 시작 (YOLO+ReID)
- [ ] 물건 추가 (QR 스캔) → 장바구니 반영
- [ ] owner_lost → SEARCHING (45°×8 회전) → owner_found → TRACKING 복귀
- [ ] 알람 발생 (BATTERY_LOW) → 대시보드 표시 → 해제 → WAITING 복귀
- [ ] 알람 발생 (THEFT) → 대시보드 표시 → 해제 → IDLE + 세션 종료

#### 시나리오 테스트 — Demo 2 (ARUCO 모드, Map)

- [ ] QR 접속 → 로그인 → ArUco 마커 인형 추종 시작 (포즈 스캔 없음)
- [ ] 물건 추가 (QR 스캔) → 장바구니 반영
- [ ] 물건 찾기 (텍스트 + STT) → 안내 이동 (Nav2) → 추종 재개
- [ ] 결제 구역 진입 → BoundaryMonitor `on_payment_zone` → WAITING
- [ ] 보내주기 → 귀환 (BT5, Nav2) → 세션 종료 → 다음 사용자 로그인 가능
- [ ] 알람 발생 (zone_out) → 대시보드 표시 → 해제 → IDLE + 세션 종료

#### 리허설 + 데모 영상

- [ ] 리허설 2~3회 전체 시나리오 시연 (4/12)
- [ ] 크리티컬 버그 전부 수정
- [ ] 데모 영상 촬영 완료 (4/13)
