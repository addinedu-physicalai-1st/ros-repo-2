# 행동 트리 (Behavior Tree)

> **프로젝트:** 쑈삥끼 (ShopPinkki)
> **팀:** 삥끼랩 | 에드인에듀 자율주행 프로젝트 2팀

쑈삥끼의 **주행·네비게이션 세부 로직**을 Behavior Tree로 정의합니다.
상태 전환 판단은 State Machine(`docs/state_machine.md`)이 담당하며,
BT는 각 상태 안에서 "어떻게 움직일 것인가"만 책임집니다.

---

## SM ↔ BT 역할 분담

```
State Machine           Behavior Tree
──────────────          ──────────────────────────────
어떤 상태인가?    ←───→  그 상태에서 어떻게 움직이는가?
상태 전환 결정           주행·회피·탐색 세부 실행
이벤트 수신              주행 완료/실패 → SM에 이벤트 반환
```

- SM `on_enter_*` 콜백에서 해당 BT를 시작(tick loop)
- SM `on_exit_*` 콜백에서 BT 중단
- BT Action 노드가 `sm.trigger('event')` 호출로 전환을 유발

---

## BT 적용 범위

BT는 **주행·네비게이션 로직이 있는 상태**에만 적용합니다.

| 상태 | BT 적용 | 이유 |
|---|---|---|
| `IDLE` | 없음 | 정지 상태. LCD QR 표시만 수행 |
| `TRACKING` | BT 1 | P-Control 추종 + 장애물 회피 |
| `SEARCHING` | BT 2 | 제자리 회전 탐색 |
| `WAITING` | BT 3 | 통행자 회피 이동 |
| `ITEM_ADDING` | 없음 | 정지 상태. QR 스캔만 수행 (주행 없음) |
| `GUIDING` | BT 4 | Nav2 Waypoint 이동 |
| `RETURNING` | BT 5 | Nav2 귀환 이동 |
| `ALARM` | 없음 | 이동 정지. 직원 호출 대기만 수행 |

---

## 노드 표기

| 표기 | 종류 | 동작 |
|---|---|---|
| `→ Sequence` | 시퀀스 | 자식을 순서대로 실행. 하나라도 FAILURE → FAILURE |
| `? Fallback` | 폴백 | 자식을 순서대로 실행. 하나라도 SUCCESS → SUCCESS |
| `[ ]` | Action | 실제 동작 수행 |
| `(( ))` | Condition | 조건 검사만 수행, 사이드이펙트 없음 |

---

## BT 1: TRACKING

**목적:** 주인을 인식하고 P-Control로 추종. RPLiDAR 장애물 회피를 병렬 적용.
**연관 SR:** SR-21, SR-22, SR-30, SR-31

```mermaid
flowchart TD
    ROOT["⟳ 추적 루프 (30 Hz)"]

    ROOT --> PAR["∥ Parallel\n모두 SUCCESS여야 계속"]

    PAR --> SEQ_TRACK["→ Sequence\n주인 추종"]
    PAR --> SEQ_OBS["→ Sequence\n장애물 회피"]

    SEQ_TRACK --> A1["[ 카메라 프레임 취득 ]"]
    A1 --> A2["[ YOLOv8n 추론 ]"]
    A2 --> FB["? Fallback\n주인 식별"]

    FB --> C1(("ReID 매칭 성공?"))
    FB --> SEQ_LOST["→ Sequence\n미발견 처리"]

    SEQ_LOST --> A3["[ 미발견 카운터 +1 ]"]
    A3 --> C2(("카운터 < N 프레임?"))
    C2 -- FAILURE --> A4["[ /cmd_vel 정지\nsm.trigger: owner_lost ]"]

    FB --> A5["[ 미발견 카운터 = 0 ]"]
    A5 --> A6["[ P-Control 산출\n선속도·각속도 ]"]
    A6 --> A7["[ /cmd_vel 퍼블리시 ]"]

    SEQ_OBS --> A8["[ RPLiDAR 스캔 취득 ]"]
    A8 --> FB2["? Fallback\n속도 보정"]
    FB2 --> C3(("전방 거리 > 안전 거리?"))
    FB2 --> A9["[ 선속도 감속 / 정지 ]"]
```

**설계 포인트**
- 미발견 카운터로 일시적 가림(occlusion)에 내성을 확보한다. N은 구현 시 확정.
- 장애물 회피는 P-Control 출력을 후처리로 보정하며, `/cmd_vel` 는 단일 퍼블리셔에서만 출력한다.

---

## BT 2: SEARCHING

**목적:** 30초간 제자리 회전하며 탐색. 재발견 시 TRACKING 복귀, 타임아웃/장애물 시 WAITING 전환.
**연관 SR:** SR-21, SR-22, SR-37

```mermaid
flowchart TD
    ROOT["BTSearching\n(30초 타이머 시작, CCW 회전)"]

    ROOT --> T{"30초 타임아웃?"}
    T -- Yes --> W["[ sm.trigger: to_waiting ]"]

    T -- No --> OBS_L{"좌측 장애물\n< 0.25m?"}
    OBS_L -- Yes --> OBS_R{"우측도\n장애물?"}
    OBS_R -- Yes --> W
    OBS_R -- No --> SWITCH_CW["[ CW 방향 전환 ]"]
    SWITCH_CW --> DET

    OBS_L -- No --> OBS_R2{"우측 장애물\n< 0.25m?\n(CW 중일 때)"}
    OBS_R2 -- Yes --> OBS_L2{"좌측도\n장애물?"}
    OBS_L2 -- Yes --> W
    OBS_L2 -- No --> SWITCH_CCW["[ CCW 방향 전환 ]"]
    SWITCH_CCW --> DET
    OBS_R2 -- No --> DET

    DET{"주인 감지됨?\nget_latest()"}
    DET -- Yes --> F["[ sm.trigger: owner_found ]"]
    DET -- No --> ROOT
```

**설계 포인트**
- 스텝/각도 없이 시간 기반으로 단순화. `SEARCH_TIMEOUT = 30.0`초.
- 회전하면서 동시에 감지 확인 (정지-감지 반복 없음).
- RPLiDAR 좌/우 호(45°~135°, 225°~315°) 기준으로 장애물 체크.
- 장애물 감지 시 반대 방향으로 전환. 양측 모두 막히면 즉시 WAITING.

---

## BT 3: WAITING

**목적:** 정지 대기 중 근접 통행자를 감지하면 Nav2로 소폭 측방 이동하여 통행로를 확보한다.
**연관 SR:** SR-36

```mermaid
flowchart TD
    ROOT["⟳ 대기 루프 (10 Hz)"]
    ROOT --> FB["? Fallback\n통행로 확보"]

    FB --> C1(("근접 통행자 없음?\n(RPLiDAR 임계 거리 초과)"))

    FB --> SEQ_AVOID["→ Sequence\n회피 이동"]
    SEQ_AVOID --> A1["[ 회피 방향 결정\n(좌우 중 여유 공간 더 넓은 쪽) ]"]
    A1 --> A2["[ 측방 목표 좌표 계산\n(현 위치 기준 ~0.3 m) ]"]
    A2 --> A3["[ Nav2 Goal 전송 ]"]
    A3 --> C2(("Nav2 성공?"))
    C2 --> A4["[ /cmd_vel zero\n정지 복귀 ]"]
```

**설계 포인트**
- WAITING BT는 SM 이벤트(앱 명령, 타임아웃)로만 종료되며 자체적으로 상태 전환을 유발하지 않는다.
- Nav2 실패 시 해당 틱을 FAILURE 처리하고 다음 틱에 재시도한다.

---

## BT 4: GUIDING

**목적:** 중앙 서버에서 상품 구역 Waypoint를 조회하여 Nav2로 이동. 도착 후 앱 알림 전송 및 TRACKING 복귀.
**연관 SR:** SR-35, SR-80, SR-81b

```mermaid
flowchart TD
    ROOT["→ Sequence\n안내 진입"]

    ROOT --> A1["[ 중앙 서버 API 질의\nzone_id → Waypoint 좌표 ]"]
    A1 --> C1(("Waypoint 유효?"))
    C1 -- FAILURE --> A_ERR1["[ 웹앱 '안내 실패' 알림 전송\nsm.trigger: nav_failed → TRACKING 복귀 ]"]

    C1 -- SUCCESS --> A2["[ Nav2 Goal 전송 ]"]
    A2 --> C2(("Nav2 성공?"))
    C2 -- FAILURE --> A_ERR2["[ 웹앱 '안내 실패' 알림 전송\nsm.trigger: nav_failed → TRACKING 복귀 ]"]

    C2 -- SUCCESS --> A3["[ 웹앱 푸시 알림\n'목적지 도착' ]"]
    A3 --> A4["[ sm.trigger: arrived ]"]
```

**설계 포인트**
- SM은 앱으로부터 zone_id를 받아 GUIDING으로 진입한다. Waypoint 조회는 BT가 zone_id로 수행한다.
- Waypoint 조회 실패와 Nav2 실패 모두 `nav_failed`로 처리한다 → TRACKING 복귀 + 앱 알림.
- 구역 이탈 감지(ALARM 전환)는 BT가 아닌 SM의 `/pinky/pose` 구독 콜백에서 처리한다.

---

## BT 5: RETURNING

**목적:** 카트 출구(ID 140) Waypoint로 Nav2 복귀. 도착 후 세션 종료 및 IDLE 전환.
**연관 SR:** SR-35, SR-84, SR-17

```mermaid
flowchart TD
    ROOT["→ Sequence\n귀환 진입"]

    ROOT --> A1["[ 중앙 서버 API 질의\n카트 출구 ID 140 Waypoint 좌표 ]"]
    A1 --> A2["[ Nav2 Goal 전송 ]"]
    A2 --> C1(("Nav2 성공?"))
    C1 -- FAILURE --> A_ERR["[ sm.trigger: nav_failed → ALARM ]"]

    C1 -- SUCCESS --> A3["[ Pi 5 세션 종료\n(POSE_DATA 삭제, SESSION 만료) ]"]
    A3 --> A4["[ 중앙 서버에 세션 종료 이벤트 전송 ]"]
    A4 --> A5["[ sm.trigger: session_ended ]"]
```

**설계 포인트**
- 구역 이탈 감지는 SM의 `/pinky/pose` 구독 콜백에서 처리한다 (BT와 독립).

---

## BT-SM 이벤트 인터페이스 요약

| BT | SM trigger | 전환 결과 |
|---|---|---|
| TRACKING BT | `owner_lost` | TRACKING → SEARCHING |
| SEARCHING BT | `owner_found` | SEARCHING → TRACKING |
| SEARCHING BT | `to_waiting` | SEARCHING → WAITING (타임아웃 또는 양측 장애물) |
| WAITING BT | (없음 — SM 이벤트로만 종료) | — |
| GUIDING BT | `arrived` | GUIDING → TRACKING |
| GUIDING BT | `nav_failed` | GUIDING → TRACKING (앱 "안내 실패" 알림) |
| RETURNING BT | `session_ended` | RETURNING → IDLE |
| RETURNING BT | `nav_failed` | RETURNING → ALARM (직원 개입 필요) |
