# 시스템 아키텍처 (System Architecture)

> **프로젝트:** 쑈삥끼 (ShopPinkki)

---

## 데모 모드

> 로봇이 작아 실제 맵에서 사람을 인식하기 어렵기 때문에 데모를 두 가지로 나눈다.

| | Demo 1 — PERSON | Demo 2 — ARUCO |
|---|---|---|
| **로봇 위치** | 책상 위 (카메라가 사람 높이) | 마트 바닥 |
| **추종 방식** | YOLO + ReID | ArUco 마커 인형 |
| **포즈 스캔** | ✅ | ❌ |
| **Nav2 / AMCL / 맵** | ❌ (P-Control만) | ✅ |
| **결제 구역 / 경계 감시** | ❌ | ✅ |
| **설정값** | `TRACKING_MODE = "PERSON"` | `TRACKING_MODE = "ARUCO"` |

---

## 전체 구성

![System Architecture](./SA.png)

---

## 컴포넌트 목록

| 컴포넌트 | 실행 위치 | 역할 |
|---|---|---|
| `shoppinkki_core` | Pi 5 | SM + BT 통합 노드. HW 제어(LED, LCD, 부저) |
| `shoppinkki_perception` | Pi 5 | YOLO+ReID / ArUco 추종 / QR 스캔 / 포즈 스캔 |
| `shoppinkki_nav` | Pi 5 | BTWaiting / BTGuiding / BTReturning / BoundaryMonitor |
| `pinky_pro packages` | Pi 5 | 모터 드라이버, 오도메트리, TF, LiDAR, 카메라 원시 데이터 |
| `Nav2 스택` | Pi 5 | AMCL 위치 추정, 경로 계획, `/scan` `/amcl_pose` 발행 |
| `control_service` | 서버 PC | ROS2 노드 + TCP(8080) + REST API. **Control DB 전체 관리** (SESSION/CART 포함) |
| `Control DB` | 서버 PC | SQLite. 모든 테이블 중앙 통합 (Pi 로컬 DB 제거) |
| `customer_web` | 서버 PC | Flask + SocketIO. 브라우저 ↔ control_service 중계. **LLM 직접 호출** |
| `Admin UI` | **별도 관제 기기** | TCP로 control_service에 연결하는 독립 클라이언트 |
| `yolo` (Docker) | 서버 PC | YOLOv8 추론 서버. **영상 UDP 수신 → 결과 TCP 반환** |
| `llm` (Docker) | 서버 PC | 자연어 상품 검색. customer_web REST 요청 처리 |

---

## 통신 채널

| 채널 | 연결 | 프로토콜 | 방향 | 설계 이유 |
|---|---|---|---|---|
| A | Customer UI ↔ customer_web | WebSocket (SocketIO) | 양방향 | 로봇 상태·위치를 새로고침 없이 실시간 Push |
| B | **Admin UI ↔ control_service** | **TCP** | 양방향 | 관리자 명령 유실 불허 → 신뢰성 최우선. 별도 기기에서 연결 |
| C | customer_web ↔ control_service | TCP (localhost:8080, JSON 개행 구분) | 양방향 | 기존과 동일 |
| D | **customer_web ↔ LLM** | **TCP (REST HTTP, :8000)** | 양방향 | 자연어 검색을 customer_web이 직접 처리 |
| E | **control_service ↔ Control DB** | **TCP** | 양방향 | DB가 독립 서비스로 분리 |
| F | **control_service ↔ YOLO** | **TCP + UDP 하이브리드** | 양방향 | 영상 데이터(무거움) → UDP / 인식 결과(좌표) → TCP |
| G | control_service ↔ shoppinkki packages | ROS 2 DDS (`ROS_DOMAIN_ID=14`) | 양방향 | 비즈니스 로직 명령·상태 발행/구독 |
| H | control_service ↔ pinky_pro packages | **ROS 2 + UDP** | 양방향 | 주행 명령 → ROS / 원시 카메라·센서 데이터 → UDP |

> 각 채널의 메시지 포맷 상세: [`docs/interface_specification.md`](interface_specification.md)

---

## 주요 아키텍처 변경 이력

| 항목 | 변경 전 | 변경 후 |
|---|---|---|
| Admin 연결 방식 | 동일 프로세스 직접 참조 (채널 D) | **별도 기기 TCP 연결 (채널 B)** |
| LLM 접근 주체 | control_service | **customer_web** |
| YOLO 접근 주체 | Pi (카메라 → TCP 직접 전송) | **control_service (UDP 영상 수신 후 처리)** |
| 카메라 데이터 전송 | Pi 내부 처리 후 결과만 전송 | **Pi → 서버 UDP 스트리밍** |
| Pi 로컬 DB | SQLite (pi.db) — SESSION/CART/POSE_DATA | **제거 → Control DB 통합** |
| Control DB 위치 | control_service 내부 | **독립 서비스 (TCP 접근)** |
