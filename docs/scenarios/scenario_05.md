# 시나리오 05: 대기

**SM 전환:** `WAITING` (대기 중 통행자 회피, 사용자 명령 대기)
**모드:** PERSON/ARUCO 공통
**관련 패키지:** shoppinkki_core, shoppinkki_nav

---

## 개요

주인을 찾지 못하거나 결제 구역에 도착했을 때 진입하는 대기 상태다. BTWaiting이 RPLiDAR로 전방 통행자를 감지해 측방으로 비켜준다. 사용자는 이 상태에서 [물건 추가] 또는 [보내주기]를 선택할 수 있으며, 5분 동안 아무 동작이 없으면 ALARM으로 전환된다.

---

## 기능 체크리스트

| 완료 | 기능 |
|:---:|---|
| [ ] | `on_enter_WAITING`: `camera_mode = "NONE"` 설정 |
| [ ] | `on_enter_WAITING`: `WAITING_TIMEOUT(=300s)` 타이머 시작 |
| [ ] | `on_enter_WAITING`: BTWaiting 시작 |
| [ ] | BTWaiting: `/scan` 전방 `FRONT_OBSTACLE_DIST(=0.5m)` 이내 감지 시 좌우(45°~135°/우:-135°~-45°) 여유 비교 |
| [ ] | BTWaiting: 더 여유 있는 쪽으로 angular_z 회전 (lateral 이동 불가 — differential drive) |
| [ ] | BTWaiting: 항상 RUNNING 반환 (SM 이벤트로만 종료) |
| [ ] | [물건 추가] 명령 (`{"cmd": "mode", "value": "ITEM_ADDING"}`) → `sm.trigger('to_item_adding')` → ITEM_ADDING |
| [ ] | [보내주기] + Pi DB 빈 장바구니 → `sm.trigger('to_returning')` → RETURNING |
| [ ] | [보내주기] + 장바구니에 물건 있음 → `send_event('returning_blocked')` → 브라우저 알림 |
| [ ] | `WAITING_TIMEOUT(=300s)` 경과 → `sm.trigger('timeout')` → ALARM |
| [ ] | `on_exit_WAITING`: 타이머 즉시 취소 |
| [ ] | `on_exit_WAITING`: `bt_runner.stop()` 호출 |

---

## 전제조건

- SM = WAITING (SEARCHING 타임아웃 or 양측 장애물로 진입)
- BTWaiting 시작, 5분 타임아웃 타이머 시작

---

## 흐름

```
on_enter_WAITING
    → camera_mode = "NONE"
    → threading.Timer(300, lambda: sm.trigger('timeout')).start()
    → bt_runner.start(BTWaiting)

BTWaiting.update() @ 30Hz
    → /scan 전방 FRONT_OBSTACLE_DIST(0.5m) 이내 감지?
        → 좌우 여유(좌측 45°~135°, 우측 -135°~-45°) 비교
        → 더 여유 있는 쪽으로 angular_z 회전 (소폭 회피)
          ※ Pinky Pro는 differential drive로 lateral 이동 불가.
             "측방 이동"이 아닌 회피 방향으로의 제자리 회전으로 구현.
    → 전방 여유 충분: angular_z=0, linear_x=0 (정지 유지)
    → 항상 RUNNING 반환 (SM 이벤트로만 종료)

사용자 명령 수신 가능 (WAITING 중)
    → "물건 추가" 버튼 → {"cmd": "mode", "value": "ITEM_ADDING"}
        → sm.trigger('to_item_adding') → ITEM_ADDING
          ※ WAITING → ITEM_ADDING 전환이 state_machine.md에 추가됨 (기존 누락)
    → "보내주기" 버튼 → cmd: mode=RETURNING → Pi DB CART_ITEM 확인
        비어있음 → sm.trigger('to_returning') → RETURNING
        있음     → send_event('returning_blocked') → 브라우저 알림

5분 타임아웃
    → sm.trigger('timeout') → ALARM
```

---

## 기대 결과

| 상황 | 동작 |
|---|---|
| 전방 통행자 감지 | 좌/우 측방 이동으로 회피 |
| 5분 경과 | ALARM (timeout) |
| "물건 추가" 명령 | ITEM_ADDING 진입 |
| "보내주기" + 빈 장바구니 | RETURNING 진입 |
| "보내주기" + 장바구니에 물건 있음 | 브라우저에 반환 차단 알림 |

---

## 검증 방법

```bash
# WAITING 진입 확인
ros2 topic echo /robot_54/status   # mode: "WAITING"

# 통행자 회피 동작 확인: 전방에 장애물 배치 후 cmd_vel 확인
ros2 topic echo /cmd_vel

# 5분 타임아웃 (테스트용 단축): config.py에서 WAITING_TIMEOUT=10으로 임시 변경 후 확인

# 장바구니 상태 확인
sqlite3 src/shoppinkki/shoppinkki_core/data/pi.db \
  "SELECT * FROM cart_item WHERE session_id=(SELECT session_id FROM session WHERE active=1);"
```

---

## 파라미터

| 파라미터 | 값 | 설명 |
|---|---|---|
| `WAITING_TIMEOUT` | 300 s | WAITING 상태 최대 대기 시간. 초과 시 ALARM 전환 |
| `FRONT_OBSTACLE_DIST` | 0.5 m | WAITING 전방 감지 거리. TRACKING(0.3m)보다 여유있게 설정 |
| `AVOID_ANGULAR_Z` | 0.3 rad/s | 통행자 회피 시 회전 속도 |

## UI 검토

| 상황 | 브라우저 |
|---|---|
| WAITING 진입 | "잠시 기다리고 있어요" + 재추적 버튼, 물건 추가 버튼, 보내주기 버튼 표시 |
| 장바구니에 물건 있는 상태에서 [보내주기] | "장바구니를 비운 후 보내주세요" 토스트 알림 |
| 5분 타임아웃 | status `mode: "ALARM"` 수신 → 알람 UI 표시 |

## on_exit_WAITING

WAITING에서 다른 상태로 전환 시:
- 타이머 즉시 취소 (`timer.cancel()`)
- `bt_runner.stop()` 호출 (BTWaiting 종료)
