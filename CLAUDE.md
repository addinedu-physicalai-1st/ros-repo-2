# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**쑈삥끼 (ShopPinkki)** — Pinky Pro 로봇을 활용한 미니어처 마트 스마트 카트 데모 프로젝트.
- Robot platform: Pinky Pro (110×120×142mm), Raspberry Pi 5 (8GB)
- Demo environment: 1.8×1.4m miniature shopping mall
- ROS 2 Jazzy / Ubuntu 24.04
- Two robots: Pinky #54 (`192.168.102.54`), Pinky #18 (`192.168.102.18`)
- **추종 방식:** 인형 전용 custom-trained YOLOv8(AI Server)로 인형 클래스 감지 후, Pi 5 로컬에서 ReID 특징 벡터 + HSV 색상 히스토그램 매칭으로 주인 인형 식별, P-Control 추종

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
pip install transitions              # SM 라이브러리 (shoppinkki_core)
pip install flask flask-socketio     # customer_web
pip install ultralytics              # YOLO (ai_server)
pip install mysql-connector-python   # control_service DB 접속
```

**Open-RMF 의존 패키지 (shoppinkki_rmf 빌드 시):**
```bash
sudo apt install ros-jazzy-rmf-fleet-adapter ros-jazzy-rmf-traffic ros-jazzy-rmf-task
pip install rmf-adapter              # Python binding
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

> 상세 사용법 → `scripts/index.md`

#### 시뮬레이션 (실물 없을 때)

터미널 3개를 열고 순서대로 실행:

```bash
# 터미널 A — 서버 (control_service + AI Docker)
bash scripts/run_server.sh

# 터미널 B — UI (admin_ui + customer_web)
bash scripts/run_ui.sh

# 터미널 C — Gazebo 시뮬 (Nav2 x2 + shoppinkki_core x2)
bash scripts/run_sim.sh
```

Gazebo 로딩 완료(~60초) 후:
1. **admin_ui** 각 로봇 카드 → **[위치 초기화]** 버튼 클릭 (AMCL 초기 위치 설정)
2. **customer_web** `http://localhost:8501/?robot_id=54` 로그인 → CHARGING → IDLE 전환

customer_web 접속: `http://localhost:8501/?robot_id=54` 또는 `?robot_id=18`

> customer_web IDLE 패널의 **[시뮬레이션 모드]** 버튼으로 추종 없이 쇼핑 테스트 가능.

#### 실물 로봇

```bash
# [노트북] 터미널 A — 서버
bash scripts/run_server.sh

# [노트북] 터미널 B — UI
bash scripts/run_ui.sh

# [Pi 5] SSH 접속 후 (각 Pi에서)
bash scripts/run_robot.sh 54   # 로봇 54번
bash scripts/run_robot.sh 18   # 로봇 18번
```

#### 스크립트별 tmux 세션

| 스크립트 | 세션 | 창 구성 |
|---|---|---|
| `run_server.sh` | `sp_server` | control / ai / shell |
| `run_ui.sh` | `sp_ui` | admin / customer |
| `run_sim.sh` | `sp_sim` | gz / core54 / core18 / init / shell |
| `run_robot.sh` | `sp_robot` | bringup / nav / core / shell |

세션 재접속: `tmux attach -t sp_server` (또는 sp_ui / sp_sim / sp_robot)

#### AI 서버 없이 실행 (`--no-ai`)

```bash
bash scripts/run_server.sh --no-ai   # YOLO/LLM Docker 제외
```

### Open-RMF Fleet Adapter 실행
```bash
# [On PC — RMF traffic scheduler + fleet adapter]
ros2 launch shoppinkki_rmf rmf_fleet.launch.py
```
> RMF를 사용하면 `navigate_to` 명령이 `task_dispatcher` → RMF → `FleetAdapter` → `control_service` 경로로 전달됨. Pi 코드 변경 없음.

### DB 관리
```bash
# 중앙 서버 DB 시딩 (대화형: reset / replace / 기본 선택)
bash scripts/seed.sh
```

### Simulation (Gazebo) — 맵 빌딩 / 단독 Nav2 확인
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
│   │   └── shoppinkki_perception/   ← YOLO bbox 수신 + ReID/QR 스캔
│   └── control_center/     ← 서버 PC 실행 ROS2 패키지
│       ├── control_service/         ← ROS2 노드 + TCP(8080) + REST API + 중앙 MySQL DB
│       ├── admin_ui/                ← TCP 관제 클라이언트 (별도 기기 또는 프로세스)
│       └── shoppinkki_rmf/          ← Open-RMF Fleet Adapter (서버 PC 실행)
├── services/
│   ├── customer_web/        ← Flask + SocketIO 고객 웹앱 (포트 8501)
│   └── ai_server/           ← Docker: 커스텀 YOLO(TCP:5005) + LLM(REST:8000)
└── scripts/
    ├── seed.sh              ← 중앙 DB 시딩 대화형 스크립트
    ├── run_server.sh        ← tmux 통합 실행기 (control_service + AI)
    ├── run_ui.sh            ← tmux 통합 실행기 (admin_ui + customer_web)
    ├── run_sim.sh           ← tmux 통합 실행기 (Gazebo + shoppinkki_core)
    ├── run_robot.sh         ← tmux 통합 실행기 (Pi 5 실물 로봇)
    └── run_ai.sh            ← AI 서버 Docker 단독 실행
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
- `shoppinkki_core` — 메인 노드. SM(10개 상태) + BT Runner + HW 제어(LED, LCD, 부저)
- `shoppinkki_nav` — Nav2 기반 BT (BTTracking, BTSearching, BTWaiting, BTGuiding, BTReturning) + BoundaryMonitor. shop 맵 포함. **Keepout Filter**: `config/keepout_mask.yaml` + `lifecycle_manager_filter`(autostart=false) — BTReturning(RETURNING/LOCKED 귀환) 진입 시 활성화, 완료/실패 시 비활성화
- `shoppinkki_perception` — AI Server로부터 bbox 수신 후 ReID + HSV 색상 매칭 (`DollDetector`) + QR 스캔

**`src/control_center/`** provides server-side logic (서버 PC 실행):
- `control_service` — ROS2 노드 + TCP 서버(8080) + REST API(8080) + 중앙 MySQL DB. Pi ↔ customer_web 중계. 충전소 슬롯 배정(`/zone/parking/available`) 포함
- `admin_ui` — TCP 클라이언트 관제 앱. control_service 채널 B(TCP)로 연결. 별도 기기 또는 프로세스로 실행. **카메라 디버그 패널**: `GET /camera/<robot_id>` MJPEG 스트림 + bbox 오버레이로 추종 동작 시각화
- `shoppinkki_rmf` — Open-RMF Fleet Adapter. RMF Traffic Negotiation으로 다중 로봇 경로 충돌 자동 조정. Pi 코드 변경 없이 `control_service` 위에 레이어로 삽입. 구성: `fleet_adapter.py`, `robot_command_handle.py`, `task_dispatcher.py`, `status_bridge.py`, `maps/shop.building`

**`services/`** provides non-ROS services:
- `customer_web` — Flask + SocketIO 고객 웹앱 (**포트 8501**). 스마트폰 브라우저용. LLM 직접 호출(채널 D)
- `ai_server` — Docker Compose. 커스텀 YOLO 추론 서버(TCP:5005) + LLM 자연어 검색(REST:8000)

### Application Architecture

- **추종 방식:** IDLE 상태에서 카메라 프레임을 채널 H(UDP) → 채널 F(TCP)로 AI Server YOLO에 전달. bbox 수신 후 Pi 5가 ReID/색상 매칭으로 주인 인형 식별. 등록 완료(`is_ready()`) 시 TRACKING 진입.
- **State Machine (SM):** 10개 상태 — CHARGING, IDLE, TRACKING, TRACKING_CHECKOUT, GUIDING, SEARCHING, WAITING, LOCKED, RETURNING, HALTED
- **Behavior Trees:** BT1=TRACKING/TRACKING_CHECKOUT(P-Control + 장애물 회피 Parallel), BT2=SEARCHING(회전 탐색), BT3=WAITING(통행 회피), BT4=GUIDING(Nav2), BT5=RETURNING/LOCKED(Keepout + 슬롯 조회 + Nav2)
- **is_locked_return 플래그:** LOCKED → RETURNING → CHARGING 경로 전체에서 LED 잠금 신호 유지. `staff_resolved` 수신 시 `False` 초기화 + `terminate_session()`.
- **LCD 표시 정책:** IDLE 상태만 QR 코드(웹앱 접속용) 표시. 나머지 상태는 텍스트 상태 메시지만 표시 (카메라 영상·QR 없음). 상태별 LCD 내용은 `docs/user_requirements.md` UR-21 테이블 참고.
- **Communication Channels (A~H):** `docs/system_architecture.md` 기준
  - A: Customer UI ↔ customer_web (WebSocket)
  - B: Admin UI ↔ control_service (TCP) — admin이 `mode`/`resume_tracking`/`force_terminate`/`staff_resolved`/`admin_goto` 명령 전송 가능
  - C: customer_web ↔ control_service (TCP :8080)
  - D: customer_web ↔ LLM (REST :8000)
  - E: control_service ↔ MySQL DB (TCP :3306)
  - F: control_service ↔ AI Server YOLO (TCP + UDP 하이브리드)
  - G: control_service ↔ shoppinkki packages (ROS DDS, `ROS_DOMAIN_ID=14`)
  - H: Pi 5 → control_service (UDP 카메라 스트림) + control_service → Pi 5 (ROS DDS `/cmd_vel`)

### Key SM Transitions (주요 상태 전환)

| Trigger | From → To | 발생 조건 |
|---|---|---|
| `charging_completed` | CHARGING → IDLE | 충전 완료 |
| `enter_tracking` | IDLE → TRACKING | 주인 인형 등록 완료 (`is_ready()`) |
| `enter_searching` | TRACKING / TRACKING_CHECKOUT → SEARCHING | N프레임 연속 미감지 (BT1) |
| `enter_guiding` | TRACKING / TRACKING_CHECKOUT → GUIDING | 앱 상품 안내 요청 |
| `enter_waiting` | GUIDING → WAITING | Nav2 목적지 도착 (BT4 SUCCESS). 앱 `arrived` 전송 |
| `enter_waiting` | TRACKING → WAITING | 앱 [대기하기] 요청 |
| `enter_waiting` | SEARCHING → WAITING | 탐색 타임아웃 (30s) |
| `resume_tracking()` | WAITING / GUIDING(실패) → TRACKING 또는 TRACKING_CHECKOUT | `previous_tracking_state` 기반 복귀 |
| `enter_tracking_checkout` | TRACKING → TRACKING_CHECKOUT | 결제 완료 (`payment_success` cmd) |
| `enter_tracking` | TRACKING_CHECKOUT → TRACKING | BoundaryMonitor 결제구역 재진입 |
| `enter_locked` | TRACKING / TRACKING_CHECKOUT / WAITING → LOCKED | 보내주기 + 미결제 항목 있음 |
| `enter_returning` | TRACKING / TRACKING_CHECKOUT / WAITING → RETURNING | 보내주기 + 빈 카트 |
| `enter_returning` | LOCKED → RETURNING | LOCKED 진입 즉시 자동 귀환 |
| `enter_charging` | RETURNING → CHARGING | 충전소 도착 (BT5 Nav2 성공) |
| `enter_halted` | **ANY** → HALTED | 배터리 임계값 이하 (`source='*'`) |
| `staff_resolved` | HALTED → CHARGING | 스태프 수동 처리 완료 |

> `force_terminate` (관제): 임의 활성 상태 → CHARGING. HALTED·LOCKED·CHARGING·OFFLINE 상태에서는 Admin UI 버튼 비활성화.

### Key Topics (Pi ↔ control_service, 채널 G ROS DDS)

| Topic | Type | Purpose |
|---|---|---|
| `/cmd_vel` | `geometry_msgs/Twist` | Motor velocity commands |
| `/odom` | `nav_msgs/Odometry` | Wheel encoder odometry |
| `/scan` | `sensor_msgs/LaserScan` | RPLiDAR C1 scans |
| `/amcl_pose` | `geometry_msgs/PoseWithCovarianceStamped` | AMCL localization |
| `/robot_<id>/status` | `std_msgs/String` | Pi→control: `{"mode":..., "pos_x":..., "pos_y":..., "battery":..., "is_locked_return":...}` (1~2Hz) |
| `/robot_<id>/alarm` | `std_msgs/String` | Pi→control: `{"event": "LOCKED"\|"HALTED"}` |
| `/robot_<id>/cart` | `std_msgs/String` | Pi→control: `{"items": [{"id":..., "name":..., "price":..., "is_paid":...}]}` |
| `/robot_<id>/cmd` | `std_msgs/String` | control→Pi: 아래 cmd 목록 참고 |

**`/robot_<id>/cmd` 페이로드 목록:**

| cmd | 페이로드 | 동작 |
|---|---|---|
| `start_session` | `{"cmd": "start_session", "user_id": "..."}` | CHARGING → IDLE |
| `mode` | `{"cmd": "mode", "value": "WAITING"\|"RETURNING"}` | SM 전환 |
| `resume_tracking` | `{"cmd": "resume_tracking"}` | `sm.resume_tracking()` → TRACKING 또는 TRACKING_CHECKOUT |
| `navigate_to` | `{"cmd": "navigate_to", "zone_id": 6, "x": 1.2, "y": 0.8, "theta": 0.0}` | SM → GUIDING + Nav2 Goal |
| `payment_success` | `{"cmd": "payment_success"}` | TRACKING → TRACKING_CHECKOUT + `mark_items_paid()` |
| `delete_item` | `{"cmd": "delete_item", "item_id": 3}` | 장바구니 항목 삭제 |
| `force_terminate` | `{"cmd": "force_terminate"}` | 세션 종료 → CHARGING |
| `staff_resolved` | `{"cmd": "staff_resolved"}` | `is_locked_return=False` + 세션 종료 → CHARGING |
| `admin_goto` | `{"cmd": "admin_goto", "x": 1.2, "y": 0.8, "theta": 0.0}` | IDLE 상태에서 Nav2 직접 목표 전송 |

### Key Services (pinky_interfaces)
- `/set_emotion` — LCD emotion (hello, happy, angry, etc.)
- `/set_led` — WS2812B LED colors
- `/set_lamp` — Top lamp color/mode/duration
- `/set_brightness` — LCD brightness

## DB Schema Summary

### 중앙 서버 MySQL DB (`shoppinkki` database, localhost:3306)

| 테이블 | 주요 컬럼 | 용도 |
|---|---|---|
| `USER` | user_id, password_hash | 사용자 계정 |
| `CARD` | card_id, user_id | 결제 카드 정보 (가상 결제용) |
| `ZONE` | zone_id, zone_name, zone_type, waypoint_x/y/theta | 구역 Waypoint. zone_type: `product`(1~8) / `special`(100~) |
| `PRODUCT` | product_id, product_name, zone_id | 상품명 → 구역 매핑 |
| `BOUNDARY_CONFIG` | description, x_min/max, y_min/max | 결제 구역 좌표 + 맵 외곽 경계 |
| `ROBOT` | robot_id, ip_address, current_mode, pos_x/y, battery_level, last_seen, active_user_id, **is_locked_return** | 로봇 실시간 상태 |
| `STAFF_CALL_LOG` | robot_id, user_id, event_type, occurred_at, resolved_at | 직원 호출 이벤트 (resolved_at=NULL이면 미처리) |
| `EVENT_LOG` | robot_id, user_id, event_type, event_detail, occurred_at | 전체 운용 이벤트 타임라인 |
| `SESSION` | session_id, robot_id, user_id, is_active, expires_at | 활성 세션 (유효: `is_active=1 AND expires_at > NOW()`) |
| `CART` | cart_id, session_id | 세션당 1개 장바구니 |
| `CART_ITEM` | item_id, cart_id, product_name, price, scanned_at, **is_paid** | QR 스캔 상품. `is_paid=1`이면 결제 완료 |

> **Pi 5 로컬 DB 없음.** 모든 테이블이 중앙 서버 MySQL DB에 통합.

**ROBOT.current_mode 값:** `CHARGING` / `IDLE` / `TRACKING` / `TRACKING_CHECKOUT` / `GUIDING` / `SEARCHING` / `WAITING` / `LOCKED` / `RETURNING` / `HALTED` / `OFFLINE`

**STAFF_CALL_LOG.event_type 값:** `LOCKED` / `HALTED`

**EVENT_LOG.event_type 값:** `SESSION_START` / `SESSION_END` / `FORCE_TERMINATE` / `LOCKED` / `HALTED` / `STAFF_RESOLVED` / `PAYMENT_SUCCESS` / `MODE_CHANGE` / `OFFLINE` / `ONLINE`

### 특수 구역 (ZONE 테이블 주요 ID)

| zone_id | 구역명 | 용도 |
|---|---|---|
| 110 | 입구 | 로봇 초기 진입 구역 |
| 120 | 출구 | TRACKING 차단 기준 |
| 140 | 충전소 주차 슬롯 1 (P1) | 귀환 목적지. 북쪽(theta=90°) 방향 |
| 141 | 충전소 주차 슬롯 2 (P2) | 귀환 목적지. 북쪽(theta=90°) 방향 |
| 150 | 결제 구역 | BoundaryMonitor TRACKING_CHECKOUT 트리거 |

## Key Parameters (`config.py`)

| 파라미터 | 값 | 설명 |
|---|---|---|
| `TARGET_AREA` | `40000` | 목표 bbox 넓이 (px²) — P-Control 선속도 기준 |
| `IMAGE_WIDTH` | `640` | 카메라 해상도 (px) |
| `KP_ANGLE` | `0.002` | P-Control 각속도 게인 |
| `KP_DIST` | `0.0001` | P-Control 선속도 게인 (px² 단위) |
| `BATTERY_THRESHOLD` | `20` | 배터리 HALTED 임계값 (%). 테스트 시 90으로 임시 상향 |
| `ROBOT_TIMEOUT_SEC` | `30` | OFFLINE 판정 기준 (마지막 status 수신 후 초) |
| `SEARCH_TIMEOUT` | `30.0` | SEARCHING 상태 타임아웃 (초) |
| `WAITING_TIMEOUT` | `300` | WAITING 상태 타임아웃 (초) |
| `N_MISS_FRAMES` | `30` | 인형 소실 판정 연속 미감지 프레임 수 |
| `MIN_DIST` | `0.25` | RPLiDAR 장애물 감지 최소 거리 (m) |
| `LINEAR_X_MAX` | `0.3` | 최대 선속도 (m/s) |
| `ANGULAR_Z_MAX` | `1.0` | 최대 각속도 (rad/s) |

## control_service 주요 구현 사항

- **cleanup 스레드** (10s 주기): `last_seen < NOW() - 30s` → `current_mode='OFFLINE'`, `active_user_id=NULL`
- **충전소 슬롯 배정** (`GET /zone/parking/available`): ROBOT 테이블에서 슬롯 140/141 주변 점유 로봇 확인 후 빈 슬롯 반환. 둘 다 점유 시 140 반환.
- **카메라 MJPEG 스트림** (`GET /camera/<robot_id>`): 채널 H(UDP)로 수신한 Pi 카메라 프레임을 MJPEG로 re-stream. Admin UI 카메라 디버그 패널용.
- **MySQL connection pool**: `pool_size=5`. 연결 설정은 환경 변수 `MYSQL_HOST/PORT/USER/PASSWORD/DATABASE`로 관리
- **SQL 패턴**: 플레이스홀더 `%s`, 명시적 cursor, `cursor(dictionary=True)`로 dict row 반환
- **Keepout Filter**: RETURNING / LOCKED 귀환 시 `lifecycle_manager_filter` STARTUP으로 활성화, 완료/실패 시 PAUSE. BTGuiding에는 미적용

## Key Documentation

| File | Content |
|---|---|
| `docs/user_requirements.md` | 사용자 요구사항 (UR) 테이블 |
| `docs/system_requirements.md` | 시스템 요구사항 (SR) 테이블 |
| `docs/system_architecture.md` | **Source of truth** — 전체 구성도, 컴포넌트 목록, 통신 채널 A~H |
| `docs/interface_specification.md` | Python 인터페이스 명세 + 채널별 메시지 포맷 + REST API |
| `docs/state_machine.md` | SM 10개 상태 정의, 전환 테이블, `is_locked_return` / `previous_tracking_state` 구현 노트 |
| `docs/behavior_tree.md` | BT 1~5 flowchart + SM↔BT 역할 분담 |
| `docs/erd.md` | DB 스키마 (MySQL DDL 포함). `STAFF_CALL_LOG`, `CART_ITEM.is_paid`, `ROBOT.is_locked_return` |
| `docs/map.md` | 미니어처 마트 맵 레이아웃, 구역 ID, Keepout Filter 설명 |
| `docs/customer_ui.md` | Customer UI 화면 구성, 기능 목록, 유저 플로우 |
| `docs/admin_ui.md` | Admin UI 화면 구성, 기능 목록, TCP 메시지 요약, 유저 플로우. 카메라 디버그 패널(MJPEG + bbox 오버레이) 포함 |
| `docs/scaffold_plan.md` | 구현 폴더 구조 계획. 컴포넌트별 파일 목록 + 구현 순서 (8단계, Open-RMF 포함) |
| `docs/scenarios/index.md` | 시나리오 목록 (SC-01~SC-82, 총 26개) — 상태 전환 단위 테스트 |
| `cheatsheet.md` | SLAM and navigation command reference |
