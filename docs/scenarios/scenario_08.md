# 시나리오 08: 복귀 및 대기열 진입

**SM 전환:** `WAITING → RETURNING → TOWARD_STANDBY_X → STANDBY_X → IDLE`
**관련 패키지:** shoppinkki_core, shoppinkki_nav, control_service

---

## 개요

사용자가 쇼핑을 마치고 [보내주기]를 누르면 로봇이 QueueManager에서 배정한 대기열 위치(ZONE 140/141/142)로 자율 귀환한다. 도착 후 사용자가 카트를 수령하면(또는 QR 스캔) 세션이 종료되고 IDLE로 돌아가 다음 사용자를 기다린다. 장바구니에 물건이 남아있으면 귀환을 차단하고 사용자에게 알린다.

---

## 기능 체크리스트

| 완료 | 기능 |
|:---:|---|
| [ ] | [보내주기] 명령 수신 시 CART_ITEM 조회 (REST API: `GET /cart/<session_id>`) |
| [ ] | 빈 장바구니 → `sm.trigger('to_returning')` → RETURNING |
| [ ] | 장바구니에 물건 있음 → `send_event('returning_blocked')` → 브라우저 알림 (SM 유지) |
| [ ] | `on_enter_RETURNING`: `bt_runner.stop()` — 기존 BT(BTWaiting/BTTracking) 중단 |
| [ ] | `on_enter_RETURNING`: BTReturning 시작 |
| [ ] | BTReturning: `GET /queue/assign?robot_id=<id>` → zone_id 수신 (140 \| 141 \| 142) |
| [ ] | BTReturning: `sm.trigger('to_toward_standby_X')` (zone에 따라 1\|2\|3) → TOWARD_STANDBY_X |
| [ ] | BTReturning: `GET /zone/<zone_id>/waypoint` → Waypoint 조회 |
| [ ] | BTReturning: Nav2 Goal 전송 (배정된 대기열 위치) |
| [ ] | BTReturning: Nav2 `SUCCEEDED` → `sm.trigger('standby_arrived')` → STANDBY_X |
| [ ] | BTReturning: Nav2 `FAILED` → `sm.trigger('nav_failed')` → ALARM |
| [ ] | STANDBY_X: 사용자 카트 수령 대기 (`session_ended` 트리거 대기) |
| [ ] | `sm.trigger('session_ended')` (사용자 카트 수령 확인) → IDLE |
| [ ] | `on_enter_IDLE`: `publisher.terminate_session()` 호출 후 즉시 `publish_status(mode="IDLE")` |
| [ ] | `terminate_session()`: REST API — SESSION `is_active = False`, CART_ITEM 삭제 |
| [ ] | control_service: mode=IDLE 수신 즉시 `ROBOT.active_user_id = NULL` 처리 |
| [ ] | IDLE 복귀 후 LCD QR 코드 재표시 |

---

## 전제조건

- SM = WAITING
- 사용자가 브라우저에서 [보내주기] 버튼 클릭
- CART_ITEM 비어있음 (있을 경우 → returning_blocked 처리)

---

## 흐름

```
브라우저: [보내주기] → {"cmd": "mode", "value": "RETURNING"}
    → customer_web TCP relay → /robot_<id>/cmd
    ↓
shoppinkki_core on_cmd (WAITING 상태)
    → REST GET /cart/<session_id> 조회
        비어있음 → sm.trigger('to_returning') → RETURNING
        있음     → publisher.send_event('returning_blocked', {}) → 브라우저 알림만
    ↓
on_enter_RETURNING
    → bt_runner.stop()   ← 기존 BT 반드시 중단
    → bt_runner.start(BTReturning)

BTReturning 시작
    → GET http://control_service:8080/queue/assign?robot_id=54
      응답: {"zone_id": 140}  ← QueueManager 배정 (140 | 141 | 142)
    → sm.trigger('to_toward_standby_1')  ← zone_id=140 → 1번 위치
    → SM: RETURNING → TOWARD_STANDBY_1

BTReturning (TOWARD_STANDBY_1 상태)
    → GET http://control_service:8080/zone/140/waypoint
      응답: {"x": 0.0, "y": 0.0, "theta": 0.0}
    → nav2_client.send_goal(x=0.0, y=0.0, theta=0.0)

BTReturning.update()
    → nav2_client.get_status()
        "SUCCEEDED" → sm.trigger('standby_arrived') → STANDBY_1
        "FAILED"    → sm.trigger('nav_failed') → ALARM

────── STANDBY_1 대기 ──────
STANDBY_1: 사용자가 카트를 수령할 때까지 대기
    → 사용자 수령 확인 (QR 스캔 또는 관제 확인) → session_ended
    ↓
sm.trigger('session_ended') → IDLE
    ↓
on_enter_IDLE
    → bt_runner.stop()
    → publisher.terminate_session()
        ← REST API: SESSION is_active=False, CART_ITEM 전체 삭제
    → publisher.publish_status(mode="IDLE", ...)  ← heartbeat 대기 없이 즉시 전송
    → control_service: mode=IDLE 수신 → ROBOT.active_user_id = NULL
    → LCD: QR 코드 표시 (다음 사용자 대기)
```

### 대기열 배정에 따른 SM 전환

| QueueManager 배정 zone | SM 트리거 | SM 전환 |
|---|---|---|
| 140 (1번) | `to_toward_standby_1` | RETURNING → TOWARD_STANDBY_1 |
| 141 (2번) | `to_toward_standby_2` | RETURNING → TOWARD_STANDBY_2 |
| 142 (3번) | `to_toward_standby_3` | RETURNING → TOWARD_STANDBY_3 |

---

## 기대 결과

| 상황 | SM 전환 | 결과 |
|---|---|---|
| Nav2 대기열 위치 도착 | TOWARD_STANDBY_X → STANDBY_X | 사용자 카트 수령 대기 |
| 사용자 카트 수령 | STANDBY_1 → IDLE | 세션 종료, 다음 사용자 로그인 가능 |
| Nav2 이동 실패 | RETURNING/TOWARD → ALARM | 알람 발생, 관제 알림 |
| 장바구니에 물건 있음 | RETURNING 진입 안 함 | 브라우저에 반환 차단 알림 |

---

## UI 검토

| 단계 | 브라우저 |
|---|---|
| [보내주기] 클릭 (빈 장바구니) | RETURNING 진입 → "카트를 반납하는 중..." 표시 |
| [보내주기] 클릭 (물건 있음) | "장바구니를 비운 후 보내주세요" 토스트, SM 유지 |
| RETURNING/TOWARD_STANDBY 중 | status `mode` 수신 → 이동 중 UI (취소 버튼 없음) |
| STANDBY 도착 | "카트 반납 위치에 도착했습니다. 카트를 수령해 주세요" |
| IDLE 복귀 | 세션 만료 처리 → "이용해주셔서 감사합니다" 화면으로 리다이렉트 |
| Nav2 실패 → ALARM | status `mode: "ALARM"` 수신 → "직원을 호출했습니다" 안내 |

## 검증 방법

```bash
# SM 전환 확인
ros2 topic echo /robot_54/status

# QueueManager 배정 확인
curl "http://localhost:8080/queue/assign?robot_id=54"
# → {"zone_id": 140}

# control_service ROBOT 테이블 확인
sqlite3 src/control_center/control_service/data/control.db \
  "SELECT active_user_id FROM robot WHERE robot_id=54;"
# → NULL (IDLE 복귀 후)

# 세션 종료 확인
sqlite3 src/control_center/control_service/data/control.db \
  "SELECT is_active FROM session ORDER BY created_at DESC LIMIT 1;"
# → 0 (is_active=False)
```
