# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**쑈삥끼 (ShopPinkki)** — Pinky Pro 로봇을 활용한 미니어처 마트 스마트 카트 데모 프로젝트.
- Robot platform: Pinky Pro (110×120×142mm), Raspberry Pi 5 (8GB)
- Demo environment: 1.4×1.8m miniature shopping mall
- ROS 2 Jazzy / Ubuntu 24.04
- Two robots: Pinky #54 (`192.168.102.54`), Pinky #18 (`192.168.102.18`)
- **추종 방식:** 인형 전용 custom-trained YOLOv8로 인형 클래스 감지 후, ReID 특징 벡터 + 색상 히스토그램 매칭으로 주인 인형 식별, P-Control 추종

## Build

```bash
# Full build
cd ~/ros_ws
colcon build

# Build specific packages
colcon build --packages-select <pkg_name>

# Source workspace after build
source install/setup.zsh
```

**Architecture restriction:** `pinky_lamp_control` and `pinky_led` only build on ARM64 (aarch64/Raspberry Pi). They will be skipped automatically on x86 PC.

### Python Dependencies (pip)

```bash
pip install transitions          # SM 라이브러리 (shoppinkki_core)
pip install flask flask-socketio # customer_web
pip install ultralytics          # YOLO (shoppinkki_perception)
```

## Testing & Linting

```bash
# Run tests for a package
colcon test --packages-select <pkg_name>
colcon test-result --verbose

# Python linting (flake8, pep257) is run via ament_lint_auto
```

Python packages use pytest. Test files are in `test/` subdirectories of each package.

## Running the Robot

### Map Building (Real Robot)
```bash
# [On Pinky]
ros2 launch pinky_bringup bringup_robot.launch.xml
ros2 launch pinky_navigation map_building.launch.xml

# [On PC]
ros2 launch pinky_navigation map_view.launch.xml
ros2 run teleop_twist_keyboard teleop_twist_keyboard  # manual driving
ros2 run nav2_map_server map_saver_cli -f "<map_name>"
```

### Navigation (Real Robot)
```bash
# [On Pinky]
ros2 launch pinky_bringup bringup_robot.launch.xml
ros2 launch shoppinkki_nav navigation.launch.py

# [On PC]
ros2 launch pinky_navigation nav2_view.launch.xml
# Use RViz: "2D Pose Estimate" to localize, then "Nav2 Goal" to navigate
```

### ShopPinkki 전체 스택 실행
```bash
# [On Pinky]
ros2 launch pinky_bringup bringup_robot.launch.xml
ros2 launch shoppinkki_nav navigation.launch.py
ros2 run shoppinkki_core main_node

# [On PC — 통합 실행 (tmux)]
~/ros_ws/scripts/run_server.sh

# [On PC — 개별 실행]
python services/customer_web/app.py      # → http://localhost:8501
cd services/ai_server && docker compose up
```

### DB 관리
```bash
# 중앙 서버 DB 시딩 (대화형: reset / replace / 기본 선택)
~/ros_ws/scripts/seed.sh
```

### Simulation (Gazebo)
```bash
# Map building in sim
ros2 launch pinky_gz_sim launch_sim_shop.launch.xml
ros2 launch pinky_navigation gz_map_building.launch.xml
ros2 run teleop_twist_keyboard teleop_twist_keyboard

# Navigation in sim
ros2 launch pinky_gz_sim launch_sim_shop.launch.xml
ros2 launch pinky_navigation gz_bringup_launch.xml map:=src/pinky_pro/pinky_navigation/map/shop.yaml
ros2 launch pinky_navigation gz_nav2_view.launch.xml
```

### Get map coordinates
```bash
ros2 topic echo /clicked_point   # then use RViz "Publish Point"
ros2 topic echo /amcl_pose       # current robot pose
```

## Architecture

### Directory Structure

```
ros_ws/
├── src/
│   ├── pinky_pro/          ← 하드웨어 플랫폼 패키지 (git submodule, 수정 금지)
│   ├── shoppinkki/         ← Pi 5 실행 ROS2 패키지
│   │   ├── shoppinkki_interfaces/   ← 인터페이스 + Mock 구현체
│   │   ├── shoppinkki_core/         ← 메인 노드 (SM + BT + HW)
│   │   ├── shoppinkki_nav/          ← Nav2 BT + BoundaryMonitor + shop 맵
│   │   └── shoppinkki_perception/   ← 커스텀 YOLO 인형 감지 + QR 스캔
│   └── control_center/     ← 서버 PC 실행 ROS2 패키지
│       ├── control_service/         ← ROS2 노드 + TCP(8080) + REST API + 중앙 DB
│       └── admin_ui/                ← TCP 관제 클라이언트 (별도 기기 또는 프로세스)
├── services/
│   ├── customer_web/        ← Flask + SocketIO 고객 웹앱 (포트 8501)
│   └── ai_server/           ← Docker: 커스텀 YOLO(TCP:5005) + LLM(REST:8000)
└── scripts/
    ├── seed.sh              ← 중앙 DB 시딩 대화형 스크립트
    ├── run_server.sh        ← tmux 통합 실행기
    ├── run_admin.sh
    ├── run_customer_web.sh
    └── run_ai.sh
```

**`src/pinky_pro/`** provides foundational drivers:
- `pinky_bringup` — Dynamixel XL330 motor init, odometry publisher, TF broadcaster. Serial: `/dev/ttyAMA4` @ 1Mbps
- `pinky_description` — URDF/XACRO robot model (wheel radius: 28mm, wheelbase: 96.1mm)
- `pinky_navigation` — Nav2 + slam_toolbox stack. Pre-built shop map: `pinky_navigation/map/shop.yaml`
- `pinky_gz_sim` — Gazebo simulation with miniature shop world
- `pinky_interfaces` — Custom ROS2 service definitions (Emotion, SetLed, SetLamp, SetBrightness)
- `pinky_emotion` — LCD ST7789 GIF emotion display (8 emotions: hello, basic, angry, bored, fun, happy, interest, sad)
- `pinky_lamp_control` — Top lamp control (ARM64 only, uses libws2811)
- `pinky_led` — WS2812B LED strip control (ARM64 only)
- `pinky_imu_bno055` — BNO055 9-axis IMU driver (I2C)

**`src/shoppinkki/`** provides application logic (Pi 5 실행):
- `shoppinkki_interfaces` — Python Protocol 인터페이스 + Mock 구현체 (`protocols.py`, `mocks.py`)
- `shoppinkki_core` — 메인 노드. SM(18개 상태) + BT Runner + HW 제어(LED, LCD, 부저)
- `shoppinkki_nav` — Nav2 기반 BT (BTWaiting, BTGuiding, BTReturning, BTStandBy) + BoundaryMonitor. shop 맵 포함
- `shoppinkki_perception` — 커스텀 YOLO 인형 감지 (`DollDetector`) + QR 스캔

**`src/control_center/`** provides server-side logic (서버 PC 실행):
- `control_service` — ROS2 노드 + TCP 서버(8080) + REST API(8080) + 중앙 SQLite DB. Pi ↔ customer_web 중계. `QueueManager` 포함
- `admin_ui` — TCP 클라이언트 관제 앱. control_service 채널 B(TCP)로 연결. 별도 기기 또는 프로세스로 실행

**`services/`** provides non-ROS services:
- `customer_web` — Flask + SocketIO 고객 웹앱 (**포트 8501**). 스마트폰 브라우저용. LLM 직접 호출(채널 D)
- `ai_server` — Docker Compose. 커스텀 YOLO 추론 서버(TCP:5005) + LLM 자연어 검색(REST:8000)

### Application Architecture

- **추종 방식:** 인형 전용 custom-trained YOLOv8 (단일 모드). REGISTERING 시 인형 감지 + ReID/색상 템플릿 등록 완료 후 TRACKING 진입.
- **State Machine (SM):** 18개 상태 — BATTERY_CHECK, CHARGING, IDLE, REGISTERING, TRACKING, SEARCHING, WAITING, ITEM_ADDING, GUIDING, CHECK_OUT, RETURNING, TOWARD/STANDBY 1~3, ALARM
- **Behavior Trees:** BT1=TRACKING(P-Control), BT2=SEARCHING(회전 탐색), BT3=WAITING(통행 회피), BT4=GUIDING(Nav2), BT5=RETURNING+Standby(Nav2 + 대기열 배정)
- **Communication Channels (A~H):** `docs/system_architecture.md` 기준
  - A: Customer UI ↔ customer_web (WebSocket)
  - B: Admin UI ↔ control_service (TCP)
  - C: customer_web ↔ control_service (TCP :8080)
  - D: customer_web ↔ LLM (REST :8000)
  - E: control_service ↔ Control DB (TCP)
  - F: control_service ↔ YOLO (TCP + UDP 하이브리드)
  - G: control_service ↔ shoppinkki packages (ROS DDS, `ROS_DOMAIN_ID=14`)
  - H: control_service ↔ pinky_pro packages (ROS DDS + UDP 카메라 스트림)

### Key SM Transitions (주요 상태 전환)

| Trigger | From → To | 발생 조건 |
|---|---|---|
| `start_session` | IDLE → REGISTERING | 로그인 완료, Pi가 `/cmd` 수신 |
| `registration_done` | REGISTERING → TRACKING | 커스텀 YOLO 인형 첫 감지 (`is_ready()`) |
| `owner_lost` | TRACKING → SEARCHING | N프레임 연속 미감지 (BT1) |
| `to_waiting` | TRACKING/SEARCHING → WAITING | 앱 명령 / 탐색 타임아웃 |
| `enter_checkout` | TRACKING → CHECK_OUT | BoundaryMonitor 결제 구역(ID 150) 진입 |
| `payment_success` | CHECK_OUT → RETURNING | 가상 결제 성공 |
| `payment_error` | CHECK_OUT → ALARM | 가상 결제 실패 |
| `battery_low` | ANY → ALARM | 배터리 ≤ 20% |
| `zone_out` | ANY → ALARM | shop_boundary 이탈 (THEFT) |
| `dismiss_to_idle` | ALARM → IDLE | THEFT 알람 해제 |
| `dismiss_to_waiting` | ALARM → WAITING | BATTERY_LOW/TIMEOUT/PAYMENT_ERROR 해제 |
| `queue_advance` | STANDBY_3→2, STANDBY_2→1 | QueueManager 큐 전진 신호 |
| `session_ended` | STANDBY_1 → IDLE | 사용자 카트 수령 + 세션 종료 |
| `admin_force_idle` | **ANY** → IDLE | 관제 강제 종료. `machine.add_transition('admin_force_idle', source='*', dest='IDLE')` |

### Key Topics (Pi ↔ control_service, 채널 G ROS DDS)

| Topic | Type | Purpose |
|---|---|---|
| `/cmd_vel` | `geometry_msgs/Twist` | Motor velocity commands |
| `/odom` | `nav_msgs/Odometry` | Wheel encoder odometry |
| `/scan` | `sensor_msgs/LaserScan` | RPLiDAR C1 scans |
| `/amcl_pose` | `geometry_msgs/PoseWithCovarianceStamped` | AMCL localization |
| `/robot_<id>/status` | `std_msgs/String` | Pi→control: `{"mode":..., "pos_x":..., "pos_y":..., "battery":...}` (1~2Hz) |
| `/robot_<id>/alarm` | `std_msgs/String` | Pi→control: `{"event": "THEFT"\|"BATTERY_LOW"\|"TIMEOUT"\|"PAYMENT_ERROR", "user_id": "..."}` |
| `/robot_<id>/cart` | `std_msgs/String` | Pi→control: `{"items": [...]}` |
| `/robot_<id>/cmd` | `std_msgs/String` | control→Pi: 아래 cmd 목록 참고 |

**`/robot_<id>/cmd` 페이로드 목록:**

| cmd | 페이로드 | 동작 |
|---|---|---|
| `start_session` | `{"cmd": "start_session", "user_id": "..."}` | SM: IDLE → REGISTERING |
| `mode` | `{"cmd": "mode", "value": "WAITING"\|"TRACKING"\|"RETURNING"\|"ITEM_ADDING"}` | SM 전환 |
| `navigate_to` | `{"cmd": "navigate_to", "zone_id": 6}` | SM → GUIDING |
| `dismiss_alarm` | `{"cmd": "dismiss_alarm"}` | ALARM → IDLE(THEFT) 또는 WAITING(기타) |
| `payment_error` | `{"cmd": "payment_error"}` | CHECK_OUT → ALARM |
| `delete_item` | `{"cmd": "delete_item", "item_id": 3}` | 장바구니 항목 삭제 |
| `force_terminate` | `{"cmd": "force_terminate"}` | ANY → IDLE (관제 강제 종료) |
| `queue_advance` | `{"cmd": "queue_advance"}` | STANDBY_X → 앞 위치로 이동 |
| `admin_goto` | `{"cmd": "admin_goto", "x": 1.2, "y": 0.8, "theta": 0.0}` | IDLE 상태에서 Nav2 직접 목표 전송 |

### Key Services (pinky_interfaces)
- `/set_emotion` — LCD emotion (hello, happy, angry, etc.)
- `/set_led` — WS2812B LED colors
- `/set_lamp` — Top lamp color/mode/duration
- `/set_brightness` — LCD brightness

## DB Schema Summary

### 중앙 서버 DB (`control_service/data/control.db`)

| 테이블 | 주요 컬럼 | 용도 |
|---|---|---|
| `USER` | user_id, password_hash | 사용자 계정 |
| `CARD` | card_id, user_id | 결제 카드 정보 |
| `ZONE` | zone_id, zone_name, zone_type, waypoint_x/y/theta | 구역 Waypoint. zone_type: `product`(1~8) / `special`(100~) |
| `PRODUCT` | product_id, product_name, zone_id | 상품명 → 구역 매핑 |
| `BOUNDARY_CONFIG` | description, x_min/max, y_min/max | 도난 경계 + 결제 구역 좌표 |
| `ROBOT` | robot_id, ip_address, current_mode, pos_x/y, battery_level, last_seen, active_user_id | 로봇 실시간 상태 |
| `ALARM_LOG` | robot_id, user_id, event_type, occurred_at, resolved_at | 알람 이벤트 (resolved_at=NULL이면 미처리) |
| `EVENT_LOG` | robot_id, user_id, event_type, event_detail, occurred_at | 전체 운용 이벤트 타임라인 |
| `SESSION` | session_id, robot_id, user_id, is_active, expires_at | 활성 세션 (유효: `is_active=1 AND expires_at > now()`) |
| `CART` | cart_id, session_id | 세션당 1개 장바구니 |
| `CART_ITEM` | item_id, cart_id, product_name, price, scanned_at | QR 스캔 담긴 상품 |

> **Pi 5 로컬 DB 없음.** 모든 테이블이 중앙 서버 DB에 통합.

**ROBOT.current_mode 값:** `BATTERY_CHECK` / `CHARGING` / `IDLE` / `REGISTERING` / `TRACKING` / `SEARCHING` / `WAITING` / `ITEM_ADDING` / `GUIDING` / `CHECK_OUT` / `RETURNING` / `TOWARD_STANDBY_1~3` / `STANDBY_1~3` / `ALARM` / `OFFLINE`

**ALARM_LOG.event_type 값:** `THEFT` / `BATTERY_LOW` / `TIMEOUT` / `PAYMENT_ERROR`

**EVENT_LOG.event_type 값:** `SESSION_START` / `SESSION_END` / `FORCE_TERMINATE` / `ALARM_RAISED` / `ALARM_DISMISSED` / `PAYMENT_SUCCESS` / `PAYMENT_FAIL` / `MODE_CHANGE` / `OFFLINE` / `ONLINE` / `QUEUE_ADVANCE`

### 특수 구역 (ZONE 테이블 주요 ID)

| zone_id | 구역명 | 용도 |
|---|---|---|
| 130 | 카트 입구 | 로봇 초기 진입 구역 |
| 140 | STANDBY_1 (대기열 1번) | 사용자 카트 수령 위치 |
| 141 | STANDBY_2 (대기열 2번) | 2번째 대기 위치 |
| 142 | STANDBY_3 (대기열 3번) | 3번째 대기 위치 |
| 150 | 결제 구역 | BoundaryMonitor CHECK_OUT 트리거 |

## Key Parameters (`config.py`)

| 파라미터 | 값 | 설명 |
|---|---|---|
| `TARGET_AREA` | `40000` | 목표 bbox 넓이 (px²) — P-Control 선속도 기준 |
| `IMAGE_WIDTH` | `640` | 카메라 해상도 (px) |
| `KP_ANGLE` | `0.002` | P-Control 각속도 게인 |
| `KP_DIST` | `0.0001` | P-Control 선속도 게인 (px² 단위) |
| `BATTERY_THRESHOLD` | `20` | 배터리 알람 임계값 (%). 테스트 시 90으로 임시 상향 |
| `ROBOT_TIMEOUT_SEC` | `30` | offline 판정 기준 (마지막 status 수신 후 초) |
| `ALARM_DISMISS_PIN` | `"1234"` | 현장 알람 해제 4자리 PIN (데모용) |
| `SEARCH_TIMEOUT` | `30.0` | SEARCHING 상태 타임아웃 (초) |
| `WAITING_TIMEOUT` | `300` | WAITING 상태 타임아웃 (초) |
| `N_MISS_FRAMES` | `30` | 인형 소실 판정 연속 미감지 프레임 수 |
| `LINEAR_X_MAX` | `0.3` | 최대 선속도 (m/s) |
| `ANGULAR_Z_MAX` | `1.0` | 최대 각속도 (rad/s) |

## control_service 주요 구현 사항

- **cleanup 스레드** (10s 주기): `last_seen < now - 30s` → `current_mode='OFFLINE'`, `active_user_id=NULL`
- **QueueManager**: RETURNING 시 `/queue/assign` 호출 → zone 140/141/142 배정. 앞 위치 비워지면 `queue_advance` cmd 전송
- **DB Lock**: `threading.Lock()` (`_lock`) — ROS 스레드 + cleanup 스레드 + Flask 스레드 동시 접근 보호
- **SQLite UPDATE 주의**: `UPDATE ... ORDER BY ... LIMIT 1` — SQLite 미지원. 서브쿼리로 `log_id` 먼저 조회 필요

## Key Documentation

| File | Content |
|---|---|
| `docs/user_requirements.md` | 사용자 요구사항 (UR) 테이블 |
| `docs/system_requirements.md` | 시스템 요구사항 (SR) 테이블 |
| `docs/system_architecture.md` | **Source of truth** — 전체 구성도, 컴포넌트 목록, 통신 채널 A~H |
| `docs/interface_specification.md` | Python 인터페이스 명세 + 채널별 메시지 포맷 |
| `docs/state_machine.md` | SM 18개 상태 정의, 전환 테이블 |
| `docs/behavior_tree.md` | 5개 BT flowchart + SM↔BT 역할 분담 |
| `docs/erd.md` | DB 스키마 (중앙 서버 DB 통합). Pi 로컬 DB 없음 |
| `docs/map.md` | 미니어처 마트 맵 레이아웃, 구역 ID |
| `docs/scaffold_plan.md` | 패키지 뼈대 구현 계획 + 체크리스트 |
| `docs/scenarios/index.md` | 시나리오 목록 (우선순위 순, 총 18개) |
| `cheatsheet.md` | SLAM and navigation command reference |
