# 쑈삥끼 시나리오 테스트 플랜

> 3/31 ~ 4/13

각 시나리오는 SM 상태 전환 단위로 구성된 테스트 플랜이다.
전제조건 → 흐름 → 기대 결과 → 검증 방법 순서로 기술한다.

---

## 시나리오 목록 (구현 우선순위 순)

> **우선순위 기준:** 구현 복잡도 낮을수록 ↑ / 타 모듈 의존도 낮을수록 ↑ / 시뮬레이션 가능할수록 ↑

| 순위 | 파일 | 제목 | SM 전환 | 우선순위 근거 |
|:---:|---|---|---|---|
| 1 | [scenario_13.md](scenario_13.md) | 관제 — 실시간 모니터링 | 없음 | 서버 전용. `ros2 topic pub /status`만으로 완전 시뮬레이션 가능. Pi 불필요 |
| 2 | [scenario_16.md](scenario_16.md) | 관제 — 로봇 Offline 감지 | 없음 | 서버 전용. cleanup 스레드 + timer만 구현. Pi 전혀 불필요 |
| 3 | [scenario_17.md](scenario_17.md) | 관제 — 이벤트 로깅 | 없음 | 서버 전용. DB INSERT + 관제 패널만. 다른 시나리오 기반 위에 자동 삽입됨 |
| 4 | [scenario_12.md](scenario_12.md) | 중복 사용 차단 | 없음 (IDLE 유지) | web + control_service만. 로봇 이동 없음. curl로 완전 테스트 |
| 5 | [scenario_01.md](scenario_01.md) | 세션 시작 | IDLE → REGISTERING | 기초 시나리오. Pi는 `/cmd` 구독만 필요. 실제 인식·주행 없음 |
| 6 | [scenario_14.md](scenario_14.md) | 관제 — 알람 수신 및 해제 | ALARM → IDLE/WAITING | `ros2 topic pub /alarm`으로 완전 시뮬레이션. Pi 로직 경량 |
| 7 | [scenario_06.md](scenario_06.md) | 물건 추가 | TRACKING/WAITING → ITEM_ADDING → TRACKING | QR 스캔 Mock 대체 가능. DB 조작 단순. 이동 없음 |
| 8 | [scenario_11.md](scenario_11.md) | 배터리 알람 | ANY → ALARM(BATTERY) → WAITING | `BATTERY_THRESHOLD=90` 임시 설정만으로 트리거. 이동 없음 |
| 9 | [scenario_15.md](scenario_15.md) | 관제 — 세션 강제 종료 및 위치 호출 | ANY → IDLE | 강제 종료는 단순. 위치 호출은 Nav2 필요하나 Gazebo 대체 가능 |
| 10 | [scenario_02.md](scenario_02.md) | 주인 등록 | REGISTERING → TRACKING | 카메라로 인형 촬영 → YOLO 감지 → ReID+색상 등록 |
| 11 | [scenario_04.md](scenario_04.md) | 주인 탐색 | TRACKING → SEARCHING → TRACKING/WAITING | 제자리 회전 + RPLiDAR. Gazebo 시뮬레이션으로 검증 가능 |
| 12 | [scenario_09.md](scenario_09.md) | 결제 구역 진입 | TRACKING → CHECK_OUT → RETURNING/ALARM | BoundaryMonitor + AMCL. Gazebo에서 맵 경계 정의 후 시뮬레이션 가능 |
| 13 | [scenario_10.md](scenario_10.md) | 도난 알람 | ANY → ALARM(THEFT) → IDLE | shop_boundary 이탈 감지. Gazebo에서 맵 밖으로 이동으로 시뮬레이션 |
| 14 | [scenario_05.md](scenario_05.md) | 대기 | WAITING (통행자 회피) | Nav2 소폭 이동 + RPLiDAR. Gazebo 가능하나 실물 회피 정밀도 요구 |
| 15 | [scenario_03.md](scenario_03.md) | 주인 추종 | TRACKING (정상 추종 중) | P-Control + YOLO+ReID. 카메라·인식 품질이 실물 환경에 크게 의존 |
| 16 | [scenario_07.md](scenario_07.md) | 물건 찾기 & 안내 | TRACKING → GUIDING → TRACKING | Nav2 Waypoint + zone DB + LLM 검색. Gazebo로 이동 경로 검증 가능 |
| 17 | [scenario_08.md](scenario_08.md) | 복귀 및 대기열 | WAITING → RETURNING → STANDBY_X → IDLE | Nav2 귀환 + QueueManager 대기열. Gazebo 가능하나 맵 Waypoint 실측값 필요 |
| 18 | [scenario_18.md](scenario_18.md) | 로봇 복귀 대기열 (2대) | RETURNING → STANDBY (2대 동시 관리) | 2대 동시 + Nav2 + 서버 큐 관리. 가장 높은 통합 복잡도. 17번 이후 구현 |

---

## 의존성 그래프 요약

```
[Tier 1 — 서버 전용, Pi 불필요]
  13 (모니터링) ─┐
  16 (Offline)  ─┼─→ 17 (이벤트 로깅 — 모두에 삽입)
  12 (중복 차단) ─┘

[Tier 2 — Pi 기본 구독, 이동 없음]
  01 (세션 시작) → 06 (물건 추가)
  14 (관제 알람) → 15 (강제 종료)
  11 (배터리 알람)

[Tier 3 — 인식 또는 Nav2, Gazebo 가능]
  02 (주인 등록) → 04 (탐색) → 05 (대기)
  09 (결제 구역) → 10 (도난 알람)

[Tier 4 — 인식 + Nav2, 실물 의존도 높음]
  03 (추종) → 07 (안내) → 08 (복귀)

[Tier 5 — 통합, 2대 동시]
  18 (대기열)  ← 08 (복귀) + 15 (admin_goto) + control_service queue API
```

---

## 공통 전제조건

- ROS_DOMAIN_ID=14, Pi ↔ 서버 PC 동일 서브넷
- `shoppinkki_core`, `shoppinkki_nav`, `control_service`, `customer_web` 모두 기동
- 중앙 서버 DB (`control.db`) 초기화 상태 (SESSION 없음, CART 없음)
- ROBOT 테이블 `active_user_id = NULL`
- **추종 모드:** 커스텀 YOLO + ReID 색상 매칭 (단일 모드. PERSON/ARUCO 이중 모드 없음)

---

## 패키지별 구현 체크리스트

> 📄 스캐폴딩: [`docs/scaffold_plan.md`](../scaffold_plan.md)
