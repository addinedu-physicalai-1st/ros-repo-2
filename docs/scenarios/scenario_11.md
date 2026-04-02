# 시나리오 11: 배터리 알람

**SM 전환:** `ANY → ALARM(BATTERY_LOW) → WAITING`

---

## 개요

배터리가 임계값(20%) 이하로 떨어지면 현재 상태와 무관하게 ALARM으로 진입한다. 관제자가 알람을 해제하면 세션을 유지한 채 WAITING으로 복귀한다. 도난 알람(THEFT)과 달리 세션이 종료되지 않는다는 점이 핵심 차이다.

---

## 기능 체크리스트

| 완료 | 기능 |
|:---:|---|
| [ ] | 배터리 레벨 모니터링 (`BATTERY_THRESHOLD=20%` 이하 감지) — `_battery_alarm_fired` 플래그로 중복 트리거 방지 |
| [ ] | `sm.trigger('battery_low')` → ALARM 전환 |
| [ ] | `on_enter_ALARM`: `bt_runner.stop()` |
| [ ] | `on_enter_ALARM`: `current_alarm = "BATTERY_LOW"` 저장 |
| [ ] | `on_enter_ALARM`: `/cmd_vel` 정지, LED 빨강 점멸 |
| [ ] | `/robot_<id>/alarm` topic publish `{"event": "BATTERY_LOW", "user_id": "..."}` (키 `event` 통일) |
| [ ] | control_service: ALARM_LOG 생성 (event_type="BATTERY_LOW") |
| [ ] | admin_ui: 알람 패널 표시 + [해제] 버튼 (채널 B TCP 수신) |
| [ ] | 브라우저: 배터리 알람 UI + 4자리 PIN 입력창 표시 |
| [ ] | 알람 해제 경로 ①: admin_ui [해제] → TCP 명령 → control_service: `{"cmd": "dismiss_alarm", "robot_id": ...}` |
| [ ] | 알람 해제 경로 ②: 브라우저 PIN 입력 → `POST /alarm/dismiss` → control_service |
| [ ] | `current_alarm != "THEFT"` → `sm.trigger('dismiss_to_waiting')` |
| [ ] | WAITING 복귀 후 세션 유지 확인 (SESSION is_active=True) |
| [ ] | WAITING 복귀 후 `ROBOT.active_user_id` 유지 확인 |

---

## 전제조건

- SM = 임의 활성 상태 (TRACKING, SEARCHING, WAITING 등)
- 배터리 레벨 읽기: `pinky_bringup`의 `/battery_state` 토픽(`sensor_msgs/BatteryState`) 구독 권장.
  미지원 시 GPIO ADC 직접 읽기 또는 Mock 대체.
  (`pinky_sensor_adc`는 scaffold_plan.md에 미정의 — 별도 구현 필요)

---

## 흐름

```
배터리 레벨 감지 (polling 또는 /battery_state 구독)
    → battery_level <= BATTERY_THRESHOLD(=20%) AND NOT _battery_alarm_fired
    → _battery_alarm_fired = True  ← 중복 트리거 방지 플래그
    → sm.trigger('battery_low') → ALARM
    ↓
on_enter_ALARM
    → bt_runner.stop()
    → current_alarm = "BATTERY_LOW"
    → 로봇 정지
    → LED: 빨강 점멸
    → /robot_<id>/alarm publish: {"event": "BATTERY_LOW", "user_id": "..."}
      ※ 키는 "event" (채널 C 명세 기준)
    ↓
control_service
    → ALARM_LOG 생성 (event_type="BATTERY_LOW")
    → admin_ui TCP push (채널 B): {"type": "alarm", "robot_id": ..., "event_type": "BATTERY_LOW", "occurred_at": ...}
    → customer_web push: {"type": "alarm", "event": "BATTERY_LOW"}

────── 알람 해제 경로 ① (관제) ──────
admin_ui [해제] 버튼
    → TCP → control_service: {"cmd": "dismiss_alarm", "robot_id": <id>}
    → /robot_<id>/cmd: {"cmd": "dismiss_alarm"}

────── 알람 해제 경로 ② (현장 PIN) ──────
브라우저: 4자리 PIN 입력 → POST /alarm/dismiss
    → customer_web → TCP → control_service 검증 → /robot_<id>/cmd: {"cmd": "dismiss_alarm"}
    ↓ (공통)
shoppinkki_core: on_cmd dismiss_alarm()
    → current_alarm != "THEFT"
    → sm.trigger('dismiss_to_waiting') → WAITING
    → current_alarm = None
    ↓
on_enter_WAITING
    → 타이머 재시작, BTWaiting 시작
    (세션 유지 — 장바구니/세션 그대로)
    ※ 배터리가 여전히 낮아도 _battery_alarm_fired=True이므로 재트리거 안 함
```

---

## 파라미터

| 파라미터 | 값 | 설명 |
|---|---|---|
| `BATTERY_THRESHOLD` | 20 % | 알람 트리거 임계값 (scaffold_plan.md 정의) |
| `_battery_alarm_fired` | bool | 중복 트리거 방지 플래그. 충전 완료 전까지 True 유지 |

## UI 검토

| 단계 | 브라우저 |
|---|---|
| ALARM 진입 | 배터리 알람 UI (경고 색상) — "배터리가 부족합니다. 직원에게 문의하세요" |
| status `battery` 필드 | 상단 배터리 아이콘에 잔량 % 항상 표시. 20% 이하면 빨간색 강조 |
| 현장 해제 | 4자리 PIN 입력창 (scenario_10과 동일 UI 컴포넌트 재사용) |
| WAITING 복귀 | 배터리 경고 아이콘 유지 (낮은 배터리 상태임을 인지) + 정상 대기 UI |

## 기대 결과

| 상황 | 결과 |
|---|---|
| 배터리 부족 감지 | ALARM 진입, 로봇 정지 |
| admin_ui 알람 수신 | 알람 패널에 BATTERY_LOW 표시 |
| [해제] 클릭 | **WAITING 복귀** (세션 유지, IDLE 가지 않음) |

> THEFT와의 차이: BATTERY_LOW 해제 → `dismiss_to_waiting` (세션 유지)
> THEFT 해제 → `dismiss_to_idle` (세션 종료)

---

## 검증 방법

```bash
# [방법 A] BATTERY_THRESHOLD 임시 상향 (권장)
# config.py에서 BATTERY_THRESHOLD = 90 임시 설정 후 노드 재시작
# → 현재 배터리가 90% 이하이면 자동 트리거

# [방법 B] 테스트 전용 simulate cmd (main_node.py에 추가 필요)
ros2 topic pub --once /robot_54/cmd std_msgs/String \
  '{"data": "{\"cmd\": \"simulate_battery_low\"}"}'
# ※ {"cmd": "battery_low"} 로 직접 pub하는 것은 Pi on_cmd()에 해당 핸들러 없으면 무시됨

# ALARM_LOG 확인
sqlite3 src/control_center/control_service/data/control.db \
  "SELECT * FROM alarm_log ORDER BY occurred_at DESC LIMIT 3;"

# 해제 후 WAITING 확인
ros2 topic echo /robot_54/status   # mode: "WAITING"

# 세션 유지 확인 (중앙 DB)
sqlite3 src/control_center/control_service/data/control.db \
  "SELECT is_active FROM session ORDER BY created_at DESC LIMIT 1;"
# → is_active = 1 (유지됨)
```
