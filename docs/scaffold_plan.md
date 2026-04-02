# 프로젝트 스캐폴딩 계획

> 시나리오 구현(`docs/scenarios/`) 착수 전에 완료해야 할 뼈대 작업.
> 각 패키지에서 코드를 작성하려면 아래 항목이 먼저 존재해야 한다.

---

## 전체 폴더 구조

```
ros_ws/
├── src/
│   ├── pinky_pro/                          ← 기존 패키지 (수정 금지)
│   │   ├── pinky_bringup/                  ← [사용] 모터 드라이버, 오도메트리, TF
│   │   ├── pinky_description/              ← [사용] URDF 로봇 모델
│   │   ├── pinky_navigation/               ← [맵만 사용] Nav2 스택 + shop.yaml
│   │   ├── pinky_interfaces/               ← [사용] SetLed/SetLamp/Emotion 서비스 정의
│   │   ├── pinky_led/                      ← [사용] WS2812B LED 제어 (ARM64 전용)
│   │   ├── pinky_lamp_control/             ← [사용] 상단 램프 제어 (ARM64 전용)
│   │   ├── pinky_emotion/                  ← [사용] LCD ST7789 감정 GIF 표시
│   │   └── pinky_gz_sim/                   ← [개발용] Gazebo 시뮬레이션
│   │
│   ├── shoppinkki/                         ← Pi 5 실행 ROS2 패키지 (구현 대상)
│   │   ├── shoppinkki_interfaces/          ← 인터페이스 명세 (전원 공유)
│   │   ├── shoppinkki_core/                ← 메인 노드 (SM + BT + HW) — Pi 로컬 DB 없음
│   │   ├── shoppinkki_nav/                 ← Nav2 주행 BT + 경계 감시
│   │   └── shoppinkki_perception/          ← 커스텀 YOLO 인형 감지 + QR 스캔
│   │
│   └── control_center/                     ← 서버 PC 실행 ROS2 패키지 (구현 대상)
│       ├── control_service/                ← ROS2 노드 + TCP 서버 + REST API
│       │   └── data/control.db            ← Control SQLite: 모든 테이블 통합
│       │                                     (USER, CARD, ZONE, PRODUCT, BOUNDARY_CONFIG,
│       │                                      ROBOT, ALARM_LOG, EVENT_LOG,
│       │                                      SESSION, CART, CART_ITEM)
│       └── admin_ui/                       ← 별도 기기 TCP 관제 클라이언트
│
├── services/                               ← 비 ROS2 서비스 (독립 실행, 구현 대상)
│   ├── customer_web/                       ← Flask + SocketIO 고객 웹앱 (포트 8501)
│   └── ai_server/                          ← Docker Compose
│       ├── docker-compose.yml
│       ├── yolo/                           ← 커스텀 YOLO 추론 서버 (TCP:5005)
│       │   └── models/                    ← 인형 전용 custom-trained 모델 (.pt)
│       └── llm/                            ← LLM 자연어 서버 (REST:8000)
│
└── docs/
    ├── scaffold_plan.md                    ← 이 파일
    ├── scenarios/                          ← 시나리오 테스트 플랜
    └── ...
```

---

## 목표

- 모든 패키지가 `colcon build` 통과
- 인터페이스(`protocols.py`) + Mock 구현체(`mocks.py`) 완성 → 각 패키지가 Mock으로 먼저 연결 가능
- 각 패키지에 빈 클래스/함수 스텁 + 올바른 메서드 시그니처 존재
- `main_node.py`가 Mock으로 완전히 와이어링되어 실행 가능 (SM 상태 전환 로그 출력)
- DB 스키마 초기화 스크립트 동작

---

## 1. shoppinkki_interfaces  ← **최우선**

> 다른 패키지가 Mock으로 시작하려면 이 패키지가 먼저 있어야 함

```
src/shoppinkki/shoppinkki_interfaces/
├── package.xml
├── setup.py
└── shoppinkki_interfaces/
    ├── __init__.py
    ├── protocols.py        ← 인터페이스 + 데이터클래스
    └── mocks.py            ← Mock 구현체
```

### 체크리스트

- [ ] `package.xml` + `setup.py` 생성 (ament_python)
- [ ] `protocols.py` — 아래 항목 모두 정의
  - `Detection(cx, area, confidence, reid_score)` dataclass
  - `CartItem(item_id, product_name, price)` dataclass
  - `DollDetectorInterface`: `register(frame) -> bool`, `run(frame)`, `get_latest() → Detection | None`, `is_ready() → bool`
  - `QRScannerInterface`: `start(on_scanned, on_timeout)`, `stop()`
  - `NavBTInterface`: `start(**kwargs)`, `stop()`, `tick() → str` (`"RUNNING"/"SUCCESS"/"FAILURE"`)
  - `BoundaryMonitorInterface`: `set_callbacks(on_zone_out, on_payment_zone)`, `update_pose(x, y)`
  - `RobotPublisherInterface`: `publish_status(mode, pos_x, pos_y, battery)`, `publish_alarm(event_type, user_id="")`, `publish_cart()`, `add_cart_item(product_name, price)`, `get_cart_items() → list[CartItem]`, `clear_cart()`, `terminate_session()`
- [ ] `mocks.py` — 아래 Mock 구현체 완성
  - `MockDollDetector(always_detect=True)` — `register()` → True, `get_latest()` 고정값 반환, `is_ready()` → True
  - `MockQRScanner()` — `on_scanned` 절대 호출 안 함
  - `MockNavBT(result="SUCCESS")` — `start()`/`stop()` 즉시, `tick()` 고정값 반환
  - `MockBoundaryMonitor()` — 콜백 절대 호출 안 함
  - `MockRobotPublisher()` — 모든 메서드 `print`만
- [ ] `colcon build --packages-select shoppinkki_interfaces` 통과

---

## 2. shoppinkki_core

```
src/shoppinkki/shoppinkki_core/
├── package.xml
├── setup.py
├── resource/shoppinkki_core
├── shoppinkki_core/
│   ├── __init__.py
│   ├── config.py           ← 타이밍 상수, P-Control 파라미터
│   ├── main_node.py        ← ROS2 노드 진입점 (Mock 와이어링)
│   ├── state_machine.py    ← transitions 기반 SM (9개 상태)
│   ├── bt_runner.py        ← BT 스레드 래퍼
│   ├── bt/
│   │   ├── __init__.py
│   │   ├── bt_tracking.py  ← 스텁 (P-Control 시그니처만)
│   │   └── bt_searching.py ← 스텁
│   └── hw/
│       ├── __init__.py
│       ├── led_controller.py   ← 스텁
│       ├── lcd_controller.py   ← 스텁
│       └── buzzer.py           ← 스텁
├── test/
│   └── test_state_machine.py
└── setup.cfg
```

### 체크리스트

- [ ] `package.xml` + `setup.py` (의존: `shoppinkki_interfaces`, `transitions`, `rclpy`)
- [ ] `config.py` — 아래 상수 정의
  - `SEARCH_TIMEOUT = 30.0`      # 탐색 타임아웃 (초)
  - `WAITING_TIMEOUT = 300.0`    # 대기 타임아웃 (초)
  - `ITEM_ADDING_TIMEOUT = 30.0` # QR 스캔 무활동 타임아웃 (초)
  - `N_MISS_FRAMES = 30`         # 인형 소실 판정 연속 미감지 프레임 수
  - `MIN_DIST = 0.25`            # RPLiDAR 장애물 감지 최소 거리 (m)
  - `TARGET_AREA = 40000`        # 목표 bbox 넓이 (px²) — P-Control 선속도 기준
  - `IMAGE_WIDTH = 640`           # 카메라 가로 해상도 (px). error_x 계산 기준
  - `KP_ANGLE = 0.002`           # P-Control 각속도 게인
  - `KP_DIST = 0.0001`           # P-Control 선속도 게인 (px² 단위)
  - `LINEAR_X_MAX = 0.3`         # 최대 전진 선속도 (m/s)
  - `LINEAR_X_MIN = -0.15`       # 최대 후진 선속도 (m/s)
  - `ANGULAR_Z_MAX = 1.0`        # 최대 각속도 (rad/s)
  - `BATTERY_THRESHOLD = 20`     # 배터리 알람 임계값 (%)
- [ ] `state_machine.py` — 18개 상태 + 전체 전환 트리거 선언, `current_alarm` 필드
  - 상태: `BATTERY_CHECK`, `CHARGING`, `IDLE`, `REGISTERING`, `TRACKING`, `SEARCHING`, `WAITING`, `ITEM_ADDING`, `GUIDING`, `CHECK_OUT`, `RETURNING`, `TOWARD_STANDBY_1`, `TOWARD_STANDBY_2`, `TOWARD_STANDBY_3`, `STANDBY_1`, `STANDBY_2`, `STANDBY_3`, `ALARM`
  - 빈 `on_enter_*` / `on_exit_*` 콜백 스텁 (로그만 출력)
- [ ] `test_state_machine.py` 통과 (전체 세션 흐름, 알람 해제 2가지, 유효하지 않은 전환 오류)
- [ ] `bt_runner.py` — `start(bt, hz)` / `stop()` / `on_result` 콜백 시그니처 완성
- [ ] `bt_tracking.py` 스텁 — `NavBTInterface` 구현 시그니처, 본문 `return "RUNNING"`
- [ ] `bt_searching.py` 스텁 — 동일
- [ ] `main_node.py` — Mock으로 완전 와이어링
  - `MockDollDetector`, `MockQRScanner`, `MockNavBT` × 3, `MockBoundaryMonitor`, `MockRobotPublisher` 주입
  - `/robot_<id>/cmd` 구독 → `sm.trigger()` 호출
  - `on_enter_IDLE`~`on_enter_ALARM` 콜백 연결 (로그 출력, HW 호출 스텁)
  - heartbeat 타이머 (2초 주기) `publish_status` 호출
- [ ] `colcon build --packages-select shoppinkki_core` 통과
- [ ] `ros2 run shoppinkki_core main_node` → 노드 기동 + SM=IDLE 로그 확인

---

## 3. shoppinkki_nav

```
src/shoppinkki/shoppinkki_nav/
├── package.xml
├── setup.py
├── resource/shoppinkki_nav
├── shoppinkki_nav/
│   ├── __init__.py
│   ├── boundary_monitor.py ← BoundaryMonitorInterface 구현 스텁
│   └── bt/
│       ├── __init__.py
│       ├── bt_waiting.py   ← NavBTInterface 구현 스텁
│       ├── bt_guiding.py   ← 스텁
│       └── bt_returning.py ← 스텁
├── config/
│   └── nav2_params.yaml    ← 기존 pinky_navigation/params 복사 후 속도 조정
├── maps/
│   ├── shop.pgm            ← pinky_navigation/map/shop.pgm 복사
│   └── shop.yaml           ← pinky_navigation/map/shop.yaml 복사
├── launch/
│   └── navigation.launch.py ← map_server + AMCL + Nav2 기동
└── test/
    ├── test_boundary_monitor.py
    └── test_bt_guiding.py
```

### 체크리스트

- [ ] `package.xml` + `setup.py` (의존: `shoppinkki_interfaces`, `nav2_msgs`, `rclpy`)
- [ ] `maps/` — `shop.pgm` + `shop.yaml` 복사
- [ ] `nav2_params.yaml` — 기존 params 복사, `max_vel_x: 0.3` 조정
- [ ] `navigation.launch.py` — map_server + AMCL + nav2_bringup 기동 (경로만 올바르면 됨)
- [ ] `bt_waiting.py` 스텁 — `NavBTInterface` 구현, `tick()` → `"RUNNING"` 고정
- [ ] `bt_guiding.py` 스텁 — `start(zone_id)` 시그니처, `tick()` → `"RUNNING"` 고정
- [ ] `bt_returning.py` 스텁 — 동일
- [ ] `boundary_monitor.py` 스텁 — `BoundaryMonitorInterface` 구현, 콜백 등록 시그니처
- [ ] `colcon build --packages-select shoppinkki_nav` 통과

---

## 4. shoppinkki_perception

```
src/shoppinkki/shoppinkki_perception/
├── package.xml
├── setup.py
├── resource/shoppinkki_perception
├── shoppinkki_perception/
│   ├── __init__.py
│   ├── doll_detector.py    ← DollDetectorInterface 구현 스텁 (커스텀 YOLO)
│   └── qr_scanner.py       ← QRScannerInterface 구현 스텁
├── models/                 ← 인형 전용 custom-trained .pt 파일 위치 (gitignore)
├── scripts/
│   └── measure_fps.py      ← 스텁
└── test/
    ├── fixtures/           ← 테스트 이미지 위치 (gitignore)
    ├── test_doll_detector.py
    └── test_qr_scanner.py
```

### 체크리스트

- [ ] `package.xml` + `setup.py` (의존: `shoppinkki_interfaces`, `opencv-python`, `ultralytics`)
- [ ] `doll_detector.py` 스텁 — `DollDetectorInterface` 구현
  - `__init__(model_path: str)` — 커스텀 YOLO 모델 로드
  - `run(frame)`, `get_latest() → Detection | None`, `is_ready() → bool` 시그니처 + `pass`
- [ ] `qr_scanner.py` 스텁 — `start(on_scanned, on_timeout)`, `stop()` 시그니처
- [ ] `colcon build --packages-select shoppinkki_perception` 통과

---

## 5. control_service

```
src/control_center/control_service/
├── package.xml
├── setup.py
├── resource/control_service
├── control_service/
│   ├── __init__.py
│   ├── main_node.py        ← ROS2 노드 진입점 스텁
│   ├── db.py               ← 중앙 SQLite 스키마 생성 + CRUD 스텁
│   ├── tcp_server.py       ← TCP 서버 스텁 (localhost:8080)
│   └── seeds/
│       └── seed_data.py    ← ZONE 14개, PRODUCT 샘플, BOUNDARY_CONFIG 2개
├── data/                   ← control.db 저장 위치 (gitignore)
└── tests/
    ├── test_tcp.py
    └── test_api.py
```

### 체크리스트

- [ ] `package.xml` + `setup.py` (의존: `rclpy`, `std_msgs`)
- [ ] `db.py` — `init_db()` (테이블 생성: USER, CARD, ZONE, PRODUCT, BOUNDARY_CONFIG, ROBOT, ALARM_LOG, EVENT_LOG, SESSION, CART, CART_ITEM), CRUD 함수 시그니처
- [ ] `seeds/seed_data.py` — 초기 데이터 삽입 스크립트 (ZONE 14개, PRODUCT 샘플, BOUNDARY_CONFIG 2개. 실측 좌표는 나중에 채움)
- [ ] `tcp_server.py` 스텁 — `start()`, 수신 메시지 타입별 `handle_*()` 함수 시그니처
- [ ] cleanup 스레드 스텁 — `ROBOT_TIMEOUT_SEC=30` 기준 `last_seen` 초과 로봇의 `active_user_id = NULL` 처리 (10초 주기)
- [ ] `main_node.py` 스텁 — ROS2 노드 초기화, topic 구독 시그니처 (`/robot_<id>/status`, `/robot_<id>/alarm`, `/robot_<id>/cart`)
- [ ] `colcon build --packages-select control_service` 통과
- [ ] `python seeds/seed_data.py` → DB 생성 + 초기 데이터 확인

---

## 6. customer_web

```
services/customer_web/
├── app.py              ← Flask + SocketIO 초기화 스텁
├── config.py           ← CONTROL_SERVICE_HOST, PORT=8501 등
├── tcp_client.py       ← TCP 클라이언트 스텁 (control_service 연결)
├── llm_client.py       ← LLM REST 클라이언트 스텁 (채널 D, :8000)
├── ws_handler.py       ← SocketIO 이벤트 핸들러 시그니처
├── routes/
│   ├── __init__.py
│   ├── auth.py         ← GET /, POST /login 라우트 스텁
│   ├── main.py         ← GET /app/main 스텁
│   └── cart.py         ← GET /app/cart 스텁
├── templates/
│   ├── base.html       ← 공통 레이아웃
│   ├── login.html      ← ID/PW 폼
│   ├── blocked.html    ← "현재 사용 중"
│   ├── registering.html ← 인형 감지 대기 스피너
│   ├── main.html       ← 맵 + 버튼 (내용 스텁)
│   └── cart.html       ← 장바구니 (내용 스텁)
├── static/
│   ├── js/
│   │   ├── ws_client.js    ← SocketIO 연결 스텁
│   │   ├── map_overlay.js  ← 스텁
│   │   └── stt.js          ← 스텁
│   └── img/
│       └── shop_map.png    ← 맵 이미지
├── requirements.txt    ← flask, flask-socketio
└── tests/
    └── test_auth.py
```

### 체크리스트

- [ ] `requirements.txt` 생성
- [ ] `config.py` — 환경변수 기반 설정 (`CONTROL_SERVICE_HOST`, `CONTROL_SERVICE_PORT=8080`, `PORT=8501`)
- [ ] `app.py` 스텁 — Flask + SocketIO 초기화, Blueprint 등록
- [ ] `tcp_client.py` 스텁 — `connect()`, `send(data)`, `disconnect()` 시그니처
- [ ] `llm_client.py` 스텁 — `query_product(name: str) → dict` 시그니처 (채널 D, LLM:8000 직접 호출)
- [ ] `ws_handler.py` 스텁 — SocketIO 이벤트 핸들러 함수 시그니처 (`on_connect`, `on_cmd` 등)
- [ ] `routes/auth.py` 스텁 — `GET /` (login.html), `POST /login` (TCP 전달 스텁)
- [ ] 모든 HTML 템플릿 기본 파일 생성 (`base.html` extends 구조)
- [ ] `python app.py` → Flask 서버 기동 + `http://localhost:8501/` 접속 → login.html 확인

---

## 7. admin_ui (범위 외 — 이후 구현)

> 별도 기기(또는 별도 프로세스)에서 TCP로 control_service에 연결하는 독립 클라이언트 (채널 B).
> scaffold 단계에서는 구현하지 않는다.
> control_service TCP(8080) 연결 후 로봇 상태 수신, 알람/강제종료/위치호출 명령 전송.
> `control_service` 빌드 및 TCP 통신이 검증된 이후 착수.

---

## 8. ai_server (Docker 뼈대)

```
services/ai_server/
├── docker-compose.yml
├── yolo/
│   ├── Dockerfile
│   ├── models/             ← 인형 전용 custom-trained .pt (gitignore)
│   └── app/
│       └── main.py         ← UDP 영상 수신 → YOLO 추론 → TCP 반환 스텁
└── llm/
    ├── Dockerfile
    └── app/
        └── main.py         ← REST API 스텁 (GET /query)
```

### 체크리스트

- [ ] `docker-compose.yml` — yolo(UDP 수신/TCP:5005), llm(REST:8000) 서비스 정의
- [ ] `yolo/Dockerfile` — `ultralytics/ultralytics` 베이스
- [ ] `yolo/app/main.py` 스텁 — UDP accept 루프, 커스텀 YOLO 추론, TCP 결과 반환 시그니처
- [ ] `llm/Dockerfile` — python 베이스
- [ ] `llm/app/main.py` 스텁 — Flask `GET /query?name=<>` → `{"zone_id": null}` 고정 반환
- [ ] `docker compose build` 통과 (추론 미구현이어도 빌드만 되면 됨)

---

## 완료 기준

아래 조건이 모두 충족되면 시나리오 구현 착수 가능:

| 확인 항목 | 명령 |
|---|---|
| 전체 ROS2 패키지 빌드 | `colcon build` |
| shoppinkki_core 노드 기동 (Mock) | `ros2 run shoppinkki_core main_node` |
| SM: IDLE → REGISTERING 전환 확인 | `ros2 topic pub /robot_54/cmd std_msgs/String '{"cmd":"start_session","user_id":"test"}'` |
| control_service 빌드 | `colcon build --packages-select control_service` |
| 중앙 DB 초기화 + 시드 데이터 | `python seeds/seed_data.py` |
| customer_web Flask 기동 | `python services/customer_web/app.py` (포트 8501) |

---

## 참고

- 시나리오별 테스트 플랜: [`docs/scenarios/index.md`](scenarios/index.md)
- 인터페이스 명세: [`docs/interface_specification.md`](interface_specification.md)
