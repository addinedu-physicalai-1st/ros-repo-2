# 시나리오 10: 도난 알람

**SM 전환:** `ANY → ALARM(THEFT) → IDLE`
**관련 패키지:** shoppinkki_core, shoppinkki_nav, admin_ui, control_service

---

## 개요

로봇이 마트 경계(shop_boundary)를 이탈하면 도난으로 판단해 즉시 ALARM 상태로 진입한다. 로봇이 정지하고 LED가 빨간색으로 점멸하며 관제 대시보드와 브라우저에 알람이 전달된다. 관제자가 알람을 해제하면 세션을 강제 종료하고 IDLE로 복귀한다.

> **아키텍처:** admin_ui은 control_service와 **별도 프로세스**. **채널 B(TCP)**로 연결된다.
> control_service가 알람 이벤트 발생 시 admin_ui에 TCP push. admin_ui은 이를 수신해 알람 패널 갱신.

---

## 기능 체크리스트

| 완료 | 기능 |
|:---:|---|
| [ ] | BoundaryMonitor: 마트 경계 좌표 로드 (`GET /boundary`) |
| [ ] | BoundaryMonitor: 경계 이탈 감지 → `on_zone_out()` 콜백 |
| [ ] | `sm.trigger('zone_out')` → ALARM 전환 |
| [ ] | `on_enter_ALARM`: `bt_runner.stop()` |
| [ ] | `on_enter_ALARM`: `current_alarm = "THEFT"` 저장 |
| [ ] | `on_enter_ALARM`: `/cmd_vel` 즉시 정지 |
| [ ] | `on_enter_ALARM`: LED 빨강 점멸 |
| [ ] | `/robot_<id>/alarm` topic publish `{"event": "THEFT", "user_id": "<user_id>"}` (키 `event`) |
| [ ] | control_service: ALARM_LOG 생성 (event_type="THEFT") |
| [ ] | control_service → admin_ui TCP push (채널 B): `{"type": "alarm", "robot_id": ..., "event_type": "THEFT", "occurred_at": ...}` |
| [ ] | admin_ui: 알람 패널 표시 + [해제] 버튼 |
| [ ] | 브라우저: 도난 알람 UI 표시 |
| [ ] | 알람 해제 경로 ①: admin_ui [해제] → TCP → control_service: `{"cmd": "dismiss_alarm", "robot_id": <id>}` → `/robot_<id>/cmd`: `{"cmd": "dismiss_alarm"}` |
| [ ] | 알람 해제 경로 ②: 브라우저 4자리 PIN 입력 → `POST /alarm/dismiss` → customer_web → TCP → control_service → `/robot_<id>/cmd`: `{"cmd": "dismiss_alarm"}` |
| [ ] | `current_alarm == "THEFT"` → `publisher.terminate_session()` 후 `sm.trigger('dismiss_to_idle')` → IDLE |
| [ ] | IDLE 복귀 후 즉시 `publish_status(mode="IDLE")` → `ROBOT.active_user_id = NULL` |

---

## 전제조건

- SM = TRACKING
- BoundaryMonitor 활성화, 마트 경계 좌표 로드됨

---

## 흐름

```
BoundaryMonitor.update_pose(x, y)
    → 마트 경계 (shop_boundary) 이탈 감지
    → on_zone_out() 콜백
    ↓
shoppinkki_core: sm.trigger('zone_out') → ALARM
    ↓
on_enter_ALARM
    → bt_runner.stop()
    → current_alarm = "THEFT"
    → 로봇 정지 (/cmd_vel: 0, 0)
    → LED: 빨강 점멸
    → /robot_<id>/alarm publish: {"event": "THEFT", "user_id": "<user_id>"}
      ※ 키는 "event" (채널 C 명세 기준). "type" 아님.
    ↓
control_service
    → ALARM_LOG 생성 (event_type="THEFT")
    → TCP push → admin_ui (채널 B): {"type": "alarm", "robot_id": 54, "event_type": "THEFT", "occurred_at": "..."}
    → customer_web TCP push: {"type": "alarm", "event": "THEFT"}
    ↓
브라우저: 알람 UI ("도난 감지! 직원에게 문의하세요") + 4자리 PIN 입력창
admin_ui: 알람 패널 표시 + [해제] 버튼

────── 알람 해제 경로 ① (관제) ──────
admin_ui [해제] 버튼
    → TCP → control_service: {"cmd": "dismiss_alarm", "robot_id": 54}
    → control_service: /robot_<id>/cmd publish: {"cmd": "dismiss_alarm"}

────── 알람 해제 경로 ② (현장 PIN) ──────
브라우저: 4자리 PIN 입력 → POST /alarm/dismiss {"robot_id": 54, "pin": "1234"}
    → customer_web → TCP → control_service: 검증 후 dismiss_alarm 처리
    → control_service: /robot_<id>/cmd publish: {"cmd": "dismiss_alarm"}
    ↓ (공통)
shoppinkki_core: on_cmd dismiss_alarm()
    → current_alarm == "THEFT"
    → publisher.terminate_session()  ← REST API: SESSION is_active=False, CART_ITEM 삭제
    → sm.trigger('dismiss_to_idle') → IDLE
    → current_alarm = None
    ↓
on_enter_IDLE
    → publisher.publish_status(mode="IDLE", ...)  ← 즉시 전송
    → control_service: ROBOT.active_user_id = NULL
    → LCD: QR 코드 (다음 사용자 대기)
```

---

## 기대 결과

| 상황 | 결과 |
|---|---|
| 경계 이탈 | ALARM 진입, 로봇 정지, LED 빨강 점멸 |
| admin_ui 알람 수신 | 알람 패널에 THEFT 표시 |
| [해제] 클릭 | IDLE 복귀, 세션 종료, 다음 사용자 로그인 가능 |

---

## 검증 방법

```bash
# 알람 topic 확인
ros2 topic echo /robot_54/alarm

# ALARM_LOG 확인
sqlite3 src/control_center/control_service/data/control.db \
  "SELECT * FROM alarm_log ORDER BY occurred_at DESC LIMIT 3;"

# 알람 해제 후 IDLE 확인
ros2 topic echo /robot_54/status   # mode: "IDLE"

# 세션 종료 확인 (중앙 DB)
sqlite3 src/control_center/control_service/data/control.db \
  "SELECT is_active FROM session ORDER BY created_at DESC LIMIT 1;"
# → is_active = 0
```

---

## UI 검토

| 단계 | 브라우저 |
|---|---|
| ALARM 진입 | 전체 화면 알람 UI (빨간 배경) — "도난 감지! 직원에게 문의하세요" |
| 현장 해제 | 4자리 PIN 입력창 표시. 올바른 PIN → 해제 요청. 틀리면 "비밀번호가 틀렸습니다" |
| IDLE 복귀 | 세션 종료 안내 → 로그인 화면으로 리다이렉트 |

> **알람 해제 PIN 설계:** 데모 단순화를 위해 관리자 고정 PIN을 `config.py`의 `ALARM_DISMISS_PIN`으로 설정.
> 보안상 USER 테이블의 개인 PIN을 사용하는 것이 바람직하나, 도난 상황에서 해당 사용자의 인증보다
> 직원(관리자)이 현장에서 즉시 해제할 수 있어야 하므로 관리자 PIN 방식이 데모에 적합.

## 마트 경계 좌표 (BOUNDARY_CONFIG)

실측 후 `seed_data.py`에 입력.
`config_id=1, description="shop_boundary"` 레코드 사용.
