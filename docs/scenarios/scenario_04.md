# 시나리오 04: 주인 탐색

**SM 전환:** `TRACKING → SEARCHING → (TRACKING | WAITING)`
**모드:** PERSON/ARUCO 공통
**관련 패키지:** shoppinkki_core

---

## 개요

주인을 놓쳤을 때(N프레임 연속 미검출) SEARCHING 상태로 진입해 제자리에서 회전하며 주인을 다시 찾는다. 30초 안에 재발견하면 TRACKING으로 복귀하고, 타임아웃이나 장애물로 회전이 불가능하면 WAITING으로 전환한다.

---

## 기능 체크리스트

| 완료 | 기능 |
|:---:|---|
| [ ] | BTTracking N=30 프레임 미검출 → `owner_lost` 트리거 → SEARCHING 진입 |
| [ ] | BTSearching 시작 시 CCW(+0.5 rad/s) 회전 개시 |
| [ ] | 회전 중 `get_latest()` 동시 확인 (감지 즉시 중단) |
| [ ] | 30초 타임아웃 → `/cmd_vel` 정지 → `to_waiting` |
| [ ] | CCW 회전 중 좌측(π/2 ± 45°) 장애물 감지 → CW 전환 |
| [ ] | CW 회전 중 우측(-π/2 ± 45°) 장애물 감지 → CCW 전환 |
| [ ] | 양측 동시 장애물 → `/cmd_vel` 정지 → `to_waiting` |
| [ ] | `update()` 실행 순서: ① 주인 감지 → ② 타임아웃 → ③ 장애물 방향 전환 (감지 최우선) |
| [ ] | 주인 재발견 → `/cmd_vel` 정지 → `owner_found` → TRACKING |
| [ ] | `test_bt_searching.py` 통과 |

---

## 전제조건

- SM = TRACKING
- BTTracking이 N=30 프레임 연속 미검출 → `owner_lost` 트리거 → SEARCHING 진입

---

## 흐름

```
BTTracking: miss_count >= 30 → FAILURE → sm.trigger('owner_lost')
    ↓
SM: TRACKING → SEARCHING
    → on_enter_SEARCHING: BTSearching 시작 (camera_mode 유지)
    ↓
BTSearching.initialise()
    → _start_time = time.time()
    → _direction = ROTATE_CCW (+0.5 rad/s)
    → /cmd_vel publish (회전 시작)

BTSearching.update() @ 30Hz
    ┌─────────────────────────────────────────────────────┐
    │ ① 감지 체크 (최우선 — 재발견 즉시 반응)              │
    │   get_latest() is not None                          │
    │     → /cmd_vel stop                                 │
    │     → sm.trigger('owner_found') → return SUCCESS    │
    │                                                     │
    │ ② 타임아웃 체크: elapsed >= 30s                      │
    │     → /cmd_vel stop                                 │
    │     → sm.trigger('to_waiting') → return FAILURE     │
    │                                                     │
    │ ③ RPLiDAR 장애물 방향 전환                           │
    │   측면 감지 범위: 좌측 π/2 ± 45°, 우측 -π/2 ± 45°  │
    │   CCW 회전 중 + 좌측(π/2±45°) 장애물                │
    │       우측도 장애물 → to_waiting (양측 막힘)          │
    │       우측 여유 → CW 전환                            │
    │   CW 회전 중 + 우측(-π/2±45°) 장애물                │
    │       좌측도 장애물 → to_waiting (양측 막힘)          │
    │       좌측 여유 → CCW 전환                           │
    │                                                     │
    │ → return RUNNING                                    │
    └─────────────────────────────────────────────────────┘
```

---

## 기대 결과

| 결과 조건 | SM 전환 | 후속 상태 |
|---|---|---|
| 30초 이내 주인 재발견 | `owner_found` | TRACKING 복귀 |
| 30초 타임아웃 | `to_waiting` | WAITING |
| 양측 장애물로 회전 불가 | `to_waiting` | WAITING |

---

## 검증 방법

```bash
# 탐색 시작 확인 (angular_z != 0, linear_x = 0)
ros2 topic echo /cmd_vel

# SM 상태 전환 로그
ros2 topic echo /robot_54/status

# 30초 타임아웃 테스트: 카메라 가리고 30초 대기 → WAITING 진입 확인
```

---

## 파라미터

| 파라미터 | 값 | 설명 |
|---|---|---|
| `ROTATE_CCW` | +0.5 rad/s | 초기 회전 방향 (CCW 고정. 주인 마지막 소실 방향 추적은 미구현 — 단순성 우선) |
| `ROTATE_CW` | -0.5 rad/s | 장애물 감지 시 전환 방향 |
| `SEARCH_TIMEOUT` | 30.0 s | 탐색 타임아웃 |
| `SIDE_OBSTACLE_DIST` | 0.25 m | 측면 장애물 판정 거리 (`MIN_DIST`와 동일 값) |
| `SIDE_ANGLE_RANGE` | π/4 (45°) | 측면 장애물 감지 각도 범위. 좌측: π/2 ± 45°, 우측: -π/2 ± 45° |

> **설계 결정 — CCW 고정 시작:** 마지막 주인 소실 방향을 기억해 그쪽으로 먼저 도는 것이 이론적으로 효율적이나,
> PERSON 모드는 소실 프레임 기준 방향 추론이 어렵고 데모 환경(소형 맵)에서 탐색 거리가 짧으므로 CCW 고정 단순 구현이 적합.
> 추후 개선 시 BTTracking에서 마지막 `detection.cx` 방향을 저장해 전달하는 방식으로 확장 가능.

## UI 검토

| 상태 | 브라우저 피드백 |
|---|---|
| SEARCHING 진입 | status WebSocket `mode: "SEARCHING"` 수신 → "주인을 찾는 중..." 표시 |
| TRACKING 복귀 | status `mode: "TRACKING"` 수신 → 일반 추종 UI 복귀 |
| WAITING 전환 | status `mode: "WAITING"` 수신 → 대기 UI 표시 (사용자에게 "재추적" 버튼 노출) |
