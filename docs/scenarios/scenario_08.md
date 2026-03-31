# 시나리오 08: 복귀

**SM 전환:** `WAITING → RETURNING → IDLE`
**모드:** ARUCO 전용 (PERSON 모드는 Nav2 없음)

---

## 개요

사용자가 쇼핑을 마치고 [보내주기]를 누르면 로봇이 카트 출구(ZONE 140)로 자율 귀환한다. 도착하면 세션이 종료되고 IDLE로 돌아가 다음 사용자를 기다린다. 장바구니에 물건이 남아있으면 귀환을 차단하고 사용자에게 알린다.

---

## 기능 체크리스트

| 완료 | 기능 |
|:---:|---|
| [ ] | [보내주기] 명령 수신 시 Pi DB CART_ITEM 조회 |
| [ ] | 빈 장바구니 → `sm.trigger('to_returning')` → RETURNING |
| [ ] | 장바구니에 물건 있음 → `send_event('returning_blocked')` → 브라우저 알림 (SM 유지) |
| [ ] | `on_enter_RETURNING`: `bt_runner.stop()` — 기존 BT(BTWaiting/BTTracking) 중단 |
| [ ] | `on_enter_RETURNING`: `camera_mode = "NONE"`, BTReturning 시작 |
| [ ] | BTReturning: `GET /zone/140/waypoint` Waypoint 조회 |
| [ ] | BTReturning: Nav2 Goal 전송 (카트 출구) |
| [ ] | BTReturning: `SUCCEEDED` → `sm.trigger('session_ended')` → IDLE |
| [ ] | BTReturning: `FAILED` → `sm.trigger('nav_failed')` → ALARM (트리거명 `nav_failed`로 통일) |
| [ ] | `on_enter_IDLE`: `publisher.terminate_session()` 호출 후 즉시 `publish_status(mode="IDLE")` |
| [ ] | `terminate_session()`: Pi DB SESSION `is_active = False`, `expires_at = now` |
| [ ] | `terminate_session()`: Pi DB POSE_DATA 삭제 |
| [ ] | `terminate_session()`: Pi DB CART_ITEM 삭제 (인터페이스 명세에 추가 필요) |
| [ ] | control_service: mode=IDLE 수신 즉시 `ROBOT.active_user_id = NULL` 처리 |
| [ ] | IDLE 복귀 후 LCD QR 코드 재표시 |

---

## 전제조건

- SM = WAITING (ARUCO 모드)
- 사용자가 브라우저에서 [보내주기] 버튼 클릭
- Pi DB CART_ITEM 비어있음 (있을 경우 → returning_blocked 처리)

---

## 흐름

```
브라우저: [보내주기] → {"cmd": "mode", "value": "RETURNING"}
    → customer_web TCP relay → /robot_<id>/cmd
    ↓
shoppinkki_core on_cmd (WAITING 상태)
    → Pi DB CART_ITEM 조회
        비어있음 → sm.trigger('to_returning') → RETURNING
        있음     → publisher.send_event('returning_blocked', {}) → 브라우저 알림만
    ↓
on_enter_RETURNING
    → bt_runner.stop()             ← 기존 BT(BTWaiting 등) 반드시 중단
    → camera_mode = "NONE"
    → bt_runner.start(BTReturning)

BTReturning.initialise()
    → GET http://control_service:8080/zone/140/waypoint
      응답: {"x": 0.0, "y": 0.0, "theta": 0.0}  ← 카트 출구 (ZONE 140)
    → nav2_client.send_goal(x=0.0, y=0.0, theta=0.0)

BTReturning.update() @ 30Hz
    → nav2_client.get_status()
        "SUCCEEDED" → return SUCCESS → sm.trigger('session_ended') → IDLE
        "FAILED"    → return FAILURE → sm.trigger('nav_failed') → ALARM
          ※ 트리거명 'nav_failed'로 통일 (state_machine.md 기준)
    ↓
on_enter_IDLE (session_ended 경로)
    → bt_runner.stop()
    → camera_mode = "NONE"
    → publisher.terminate_session()
        ← SESSION is_active=False, expires_at=now
        ← POSE_DATA 삭제
        ← CART_ITEM 삭제 (인터페이스 명세 terminate_session()에 추가 필요)
    → publisher.publish_status(mode="IDLE", ...)  ← heartbeat 대기 없이 즉시 전송
    → control_service: mode=IDLE 수신 → ROBOT.active_user_id = NULL 즉시 처리
    → LCD: QR 코드 표시 (다음 사용자 대기)
```

---

## 기대 결과

| 상황 | SM 전환 | 결과 |
|---|---|---|
| Nav2 카트 출구 도착 | RETURNING → IDLE | 세션 종료, 다음 사용자 로그인 가능 |
| Nav2 이동 실패 | RETURNING → ALARM | 알람 발생, 관제 알림 |
| 장바구니에 물건 있음 | RETURNING 진입 안 함 | 브라우저에 반환 차단 알림 |

---

## UI 검토

| 단계 | 브라우저 |
|---|---|
| [보내주기] 클릭 (빈 장바구니) | RETURNING 진입 → "카트를 반납하는 중..." 표시 |
| [보내주기] 클릭 (물건 있음) | "장바구니를 비운 후 보내주세요" 토스트, SM 유지 |
| RETURNING 중 | status `mode: "RETURNING"` 수신 → 이동 중 UI (취소 버튼 없음 — 자율 귀환은 사용자가 중단 불가) |
| IDLE 복귀 | 세션 만료 처리 → 로그인 화면 또는 "이용해주셔서 감사합니다" 화면으로 리다이렉트 |
| Nav2 실패 → ALARM | status `mode: "ALARM"` 수신 → "직원을 호출했습니다" 안내 |

## 검증 방법

```bash
# SM 전환 확인
ros2 topic echo /robot_54/status

# 세션 종료 확인 (Pi DB)
sqlite3 src/shoppinkki/shoppinkki_core/data/pi.db \
  "SELECT active FROM session ORDER BY created_at DESC LIMIT 1;"
# → active = 0

# control_service ROBOT 테이블 확인
sqlite3 src/control_center/control_service/data/control.db \
  "SELECT active_user_id FROM robot WHERE robot_id=54;"
# → NULL
```
