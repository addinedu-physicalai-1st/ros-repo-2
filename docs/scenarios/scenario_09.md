# 시나리오 09: 결제 구역 진입

**SM 전환:** `TRACKING → WAITING`
**모드:** ARUCO 전용 (BoundaryMonitor 사용)

---

## 개요

로봇이 지도상 결제 구역(ZONE 150)에 진입하면 BoundaryMonitor가 감지해 자동으로 WAITING 상태로 전환하고 브라우저에 결제 UI를 띄운다. 결제 완료 후 사용자는 [보내주기]를 눌러 복귀 흐름(Scenario 08)으로 이어간다.

---

## 기능 체크리스트

| 완료 | 기능 |
|:---:|---|
| [ ] | BoundaryMonitor: `/amcl_pose` 구독 및 좌표 갱신 |
| [ ] | BoundaryMonitor: `GET /boundary` → 결제 구역 좌표 로드 |
| [ ] | BoundaryMonitor: 결제 구역 범위 내 진입 감지 |
| [ ] | `on_payment_zone()` 콜백 1회만 발생 (`_payment_triggered` 플래그) |
| [ ] | `BoundaryMonitor.reset()` — `on_enter_REGISTERING` 및 `on_enter_IDLE` 에서 호출하여 플래그 초기화 |
| [ ] | `sm.trigger('to_waiting')` → WAITING 전환 (state_machine.md 수정 반영) |
| [ ] | `on_enter_WAITING`: `send_event('payment_zone_entered', {})` → 브라우저 결제 UI 표시 |
| [ ] | 브라우저: 등록된 카드 정보 표시 + [결제하기] 버튼 |
| [ ] | [결제하기] → `{"cmd": "process_payment"}` → control_service 결제 처리 |
| [ ] | 결제 성공 → `{"type": "payment_done"}` → 브라우저 "결제 완료" + [보내주기] 버튼 강조. SM은 WAITING 유지 |
| [ ] | 결제 실패 → control_service가 `/robot_<id>/cmd`: `{"cmd": "payment_error"}` 전송 → `sm.trigger('payment_error')` → ALARM |
| [ ] | `test_boundary_monitor.py` 통과 |

---

## 전제조건

- SM = TRACKING (ARUCO 모드)
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
shoppinkki_core: sm.trigger('to_waiting') → WAITING
    ↓
on_enter_WAITING
    → publisher.send_event('payment_zone_entered', {})
    → 브라우저: 결제 UI 표시 ("결제 구역에 도착했습니다")
      카드 정보 표시 + [결제하기] 버튼

사용자: [결제하기] 클릭
    → 브라우저: {"cmd": "process_payment"} (채널 A)
    → customer_web → TCP → control_service: 가상 결제 처리
    ↓
결제 성공
    → control_service → WebSocket → 브라우저: {"type": "payment_done"}
    → 브라우저: "결제가 완료되었습니다" + [보내주기] 버튼 강조
    → SM: WAITING 유지 (사용자가 [보내주기] 선택 대기)
    → 사용자: [보내주기] → Scenario 08 (복귀)

결제 실패
    → control_service → /robot_<id>/cmd: {"cmd": "payment_error"}
    → shoppinkki_core: sm.trigger('payment_error') → ALARM
    → 브라우저: {"type": "alarm", "event": "PAYMENT_ERROR"}
```

> **state_machine.md 수정 사항:** 기존 `TRACKING → TRACKING(결제 성공)` / `TRACKING → ALARM(결제 오류)` 자동 결제 방식을
> `TRACKING → WAITING(결제 구역 진입)` + `WAITING → ALARM(결제 오류)` UX 중심 방식으로 변경.

---

## 기대 결과

| 상황 | 동작 |
|---|---|
| 결제 구역 진입 | TRACKING → WAITING, 브라우저 결제 UI |
| 동일 구역 재진입 | 콜백 발생 안 함 (`_payment_triggered` 플래그) |
| 결제 성공 후 [보내주기] | WAITING → RETURNING → IDLE (Scenario 08) |
| 결제 실패 | WAITING → ALARM (관제 해제 후 WAITING 복귀) |

## UI 검토

| 단계 | 브라우저 |
|---|---|
| 결제 구역 진입 | "결제 구역에 도착했습니다" 팝업 + 등록 카드 정보(마스킹) + [결제하기] 버튼 |
| 결제 처리 중 | [결제하기] 버튼 비활성화 + 스피너 |
| 결제 성공 | "결제가 완료되었습니다 ✓" + [보내주기] 버튼 강조 표시 |
| 결제 실패 | "결제에 실패했습니다. 직원에게 문의하세요" + 알람 UI 전환 |

---

## 검증 방법

```bash
# AMCL 포즈 확인 (실제 로봇)
ros2 topic echo /amcl_pose

# BoundaryMonitor 결제 구역 좌표 확인
curl "http://localhost:8080/boundary"
# 응답: {"payment_zone": {"x_min": ..., "x_max": ..., "y_min": ..., "y_max": ...}}

# SM 전환 확인
ros2 topic echo /robot_54/status   # TRACKING → WAITING
```

---

## 결제 구역 좌표 (BOUNDARY_CONFIG)

실측 후 `seed_data.py`에 입력.
`config_id=2, description="payment_zone"` 레코드 사용.
