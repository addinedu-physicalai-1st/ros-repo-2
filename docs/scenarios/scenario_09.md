# 시나리오 09: 결제 구역 진입

**SM 전환:** `TRACKING → CHECK_OUT → (RETURNING | ALARM | TRACKING)`
**관련 패키지:** shoppinkki_core, shoppinkki_nav, customer_web, control_service

---

## 개요

로봇이 지도상 결제 구역(ZONE 150)에 진입하면 BoundaryMonitor가 감지해 자동으로 CHECK_OUT 상태로 전환하고 브라우저에 결제 UI를 띄운다. 결제 성공 시 RETURNING, 결제 실패 시 ALARM, 사용자 취소 시 TRACKING으로 복귀한다.

---

## 기능 체크리스트

| 완료 | 기능 |
|:---:|---|
| [ ] | BoundaryMonitor: `/amcl_pose` 구독 및 좌표 갱신 |
| [ ] | BoundaryMonitor: `GET /boundary` → 결제 구역 좌표 로드 |
| [ ] | BoundaryMonitor: 결제 구역 범위 내 진입 감지 |
| [ ] | `on_payment_zone()` 콜백 1회만 발생 (`_payment_triggered` 플래그) |
| [ ] | `BoundaryMonitor.reset()` — `on_enter_REGISTERING` 및 `on_enter_IDLE`에서 호출하여 플래그 초기화 |
| [ ] | `sm.trigger('enter_checkout')` → CHECK_OUT 전환 |
| [ ] | `on_enter_CHECK_OUT`: BTTracking 정지 (`bt_runner.stop()`) |
| [ ] | `on_enter_CHECK_OUT`: `send_event('payment_zone_entered', {})` → 브라우저 결제 UI 표시 |
| [ ] | 브라우저: 등록된 카드 정보 표시 + [결제하기] 버튼 + [쇼핑 계속] 버튼 |
| [ ] | [결제하기] → `{"cmd": "process_payment"}` → control_service 결제 처리 |
| [ ] | 결제 성공 → control_service: `{"type": "payment_done"}` → 브라우저 "결제 완료" |
| [ ] | 결제 성공 → control_service: `/robot_<id>/cmd`: `{"cmd": "mode", "value": "RETURNING"}` → `sm.trigger('payment_success')` → RETURNING |
| [ ] | 결제 실패 → control_service: `/robot_<id>/cmd`: `{"cmd": "payment_error"}` → `sm.trigger('payment_error')` → ALARM |
| [ ] | 사용자 [쇼핑 계속] → `{"cmd": "mode", "value": "TRACKING"}` → `sm.trigger('to_tracking')` → TRACKING |
| [ ] | `test_boundary_monitor.py` 통과 |

---

## 전제조건

- SM = TRACKING
- BoundaryMonitor 활성화, `/amcl_pose` 구독 중
- ZONE 150 (payment_zone) 좌표 로드됨

---

## 흐름

```
BoundaryMonitor.update_pose(x, y) — /amcl_pose 콜백
    → 결제 구역 좌표 범위 내 진입 감지
    → _payment_triggered == False → on_payment_zone() 1회 호출
    → _payment_triggered = True (이후 재진입 무시)
    ↓
shoppinkki_core: sm.trigger('enter_checkout') → CHECK_OUT
    ↓
on_enter_CHECK_OUT
    → bt_runner.stop()    ← BTTracking 정지 (추종 중단)
    → publisher.send_event('payment_zone_entered', {})
    → 브라우저: 결제 UI 표시 ("결제 구역에 도착했습니다")
      카드 정보 표시 + [결제하기] 버튼 + [쇼핑 계속] 버튼

────── 경로 1: 결제 성공 ──────
사용자: [결제하기] 클릭
    → 브라우저: {"cmd": "process_payment"} (채널 A)
    → customer_web → TCP → control_service: 가상 결제 처리
    ↓
결제 성공
    → control_service → customer_web: {"type": "payment_done"}
    → 브라우저: "결제가 완료되었습니다 ✓"
    → control_service → /robot_<id>/cmd: {"cmd": "mode", "value": "RETURNING"}
    → shoppinkki_core: sm.trigger('payment_success') → RETURNING
    ↓
on_enter_RETURNING: BTReturning 시작 → QueueManager 배정 → STANDBY 대기

────── 경로 2: 결제 실패 ──────
결제 실패
    → control_service → /robot_<id>/cmd: {"cmd": "payment_error"}
    → shoppinkki_core: sm.trigger('payment_error') → ALARM
    → 브라우저: {"type": "alarm", "event": "PAYMENT_ERROR"}

────── 경로 3: 사용자 취소 ──────
브라우저: [쇼핑 계속] 버튼
    → {"cmd": "mode", "value": "TRACKING"} (채널 A)
    → customer_web → TCP → control_service → /robot_<id>/cmd
    → shoppinkki_core: sm.trigger('to_tracking') → TRACKING
    → on_enter_TRACKING: BTTracking 재시작
```

---

## 기대 결과

| 상황 | 동작 |
|---|---|
| 결제 구역 진입 | TRACKING → CHECK_OUT, 로봇 정지, 브라우저 결제 UI |
| 동일 구역 재진입 | 콜백 발생 안 함 (`_payment_triggered` 플래그) |
| 결제 성공 | CHECK_OUT → RETURNING (QueueManager 배정 → STANDBY 대기) |
| 결제 실패 | CHECK_OUT → ALARM |
| [쇼핑 계속] | CHECK_OUT → TRACKING (추종 재개) |

## UI 검토

| 단계 | 브라우저 |
|---|---|
| 결제 구역 진입 | "결제 구역에 도착했습니다" 팝업 + 등록 카드 정보(마스킹) + [결제하기] 버튼 + [쇼핑 계속] 버튼 |
| 결제 처리 중 | [결제하기] 버튼 비활성화 + 스피너 |
| 결제 성공 | "결제가 완료되었습니다 ✓" → 복귀 UI로 전환 |
| 결제 실패 | "결제에 실패했습니다. 직원에게 문의하세요" + 알람 UI 전환 |
| [쇼핑 계속] | 결제 UI 종료 → 추종 UI 복귀 |

---

## 검증 방법

```bash
# AMCL 포즈 확인 (실제 로봇)
ros2 topic echo /amcl_pose

# BoundaryMonitor 결제 구역 좌표 확인
curl "http://localhost:8080/boundary"
# 응답: {"payment_zone": {"x_min": ..., "x_max": ..., "y_min": ..., "y_max": ...}}

# SM 전환 확인
ros2 topic echo /robot_54/status   # TRACKING → CHECK_OUT

# 결제 성공 시뮬레이션 (control_service 직접 호출)
curl -X POST http://localhost:8080/process_payment \
  -d '{"robot_id": 54}'

# 결제 실패 시뮬레이션
ros2 topic pub --once /robot_54/cmd std_msgs/String \
  '{"data": "{\"cmd\": \"payment_error\"}"}'
```

---

## 결제 구역 좌표 (BOUNDARY_CONFIG)

실측 후 `seed_data.py`에 입력.
`config_id=2, description="payment_zone"` 레코드 사용.
