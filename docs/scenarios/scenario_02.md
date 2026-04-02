# 시나리오 02: 주인 등록

**SM 전환:** `REGISTERING → TRACKING`
**관련 패키지:** shoppinkki_core, shoppinkki_perception

---

## 개요

REGISTERING 상태에서 사용자가 인형을 카메라 앞에 보여주면 로봇이 주인 인형을 등록한다.
커스텀 YOLO 모델이 인형을 감지하고, ReID 특징 벡터 + 색상 히스토그램을 템플릿으로 저장한다.
등록 완료 후 TRACKING으로 전환된다.

---

## 기능 체크리스트

| 완료 | 기능 |
|:---:|---|
| [ ] | `on_enter_REGISTERING`: `send_event("registering", {})` → 브라우저 스피너 + "인형을 카메라에 보여주세요" 안내 표시 |
| [ ] | `on_enter_REGISTERING`: 별도 스레드에서 등록 루프 시작 |
| [ ] | 등록 루프: 매 프레임 `doll_detector.register(frame)` 호출 |
| [ ] | `register(frame)`: 내부적으로 YOLO로 인형 감지 → ReID 특징 벡터 + 색상 히스토그램 추출 → 템플릿으로 저장 |
| [ ] | `register(frame)` 성공(True 반환) → `doll_detector.is_ready() == True` |
| [ ] | `is_ready()` True 확인 → `sm.trigger('registration_done')` |
| [ ] | `send_event("registration_done", {})` → 브라우저 스피너 종료, 추종 UI 전환 |
| [ ] | SM: `REGISTERING → TRACKING` 전환 |
| [ ] | `on_enter_TRACKING`: BTTracking 시작 |

---

## 전제조건

- SM = REGISTERING
- 카메라 활성화, `doll_detector` 초기화됨 (`is_ready() == False` 상태)

---

## 흐름

```
on_enter_REGISTERING
    → publisher.send_event("registering", {})
      ← 브라우저 main.html에 스피너 + "인형을 카메라에 보여주세요" 안내 표시
    → threading.Thread(target=_registration_loop).start()

_registration_loop()  ← 별도 스레드에서 실행
    카메라 루프
        frame = camera.get_frame()
        success = doll_detector.register(frame)
        ┌── success == True:
        │       → doll_detector.is_ready() == True
        │       → sm.trigger('registration_done')
        │       → publisher.send_event("registration_done", {})
        │         ← 브라우저 스피너 종료, 추종 UI 전환
        │       → 루프 종료
        └── success == False: 다음 프레임으로 계속

SM: REGISTERING → TRACKING
    → on_enter_TRACKING: BTTracking 시작
```

### `doll_detector.register(frame)` 내부 파이프라인

```
1. YOLO 추론 → 프레임 내 "인형" 클래스 bbox 감지
2. bbox 없음 → False 반환
3. bbox 있음 (가장 신뢰도 높은 1개 선택):
   → ReID 특징 벡터 추출 (bbox 크롭 → 임베딩)
   → 색상 히스토그램 계산 (HSV)
   → (reid_template, color_template) 저장
   → True 반환
```

### 채널 A 추가 메시지 타입

- `{"type": "registering"}` — 스피너 + 안내 문구 표시
- `{"type": "registration_done"}` — 스피너 종료, 추종 UI 전환

---

## 기대 결과

| 항목 | 기대값 |
|---|---|
| SM 상태 | TRACKING |
| `doll_detector.is_ready()` | True |
| 등록된 템플릿 | ReID 특징 벡터 + 색상 히스토그램 저장됨 |
| BTTracking | 시작됨 |
| 브라우저 | 스피너 → 추종 UI 전환 |

---

## 검증 방법

```bash
# SM 상태 확인
ros2 topic echo /robot_54/status   # mode: "TRACKING"

# BTTracking /cmd_vel 발행 확인 (인형 앞에 놓으면 움직여야 함)
ros2 topic echo /cmd_vel
```

---

## UI 검토

| 화면 | 상태 | 필수 요소 |
|---|---|---|
| `main.html` | 등록 대기 | 스피너 + "인형을 카메라에 보여주세요" 문구 |
| `main.html` | 등록 완료 | 스피너 종료 → 일반 추종 UI (장바구니 버튼, 물건 찾기 버튼 등) 활성화 |

## 예외 케이스

- **인형 미감지** → `register(frame)` False 반환 → 다음 프레임 계속 시도 (무한 루프, 타임아웃 없음)
- **등록 루프 중 force_terminate** → `admin_force_idle` 트리거 → SM IDLE로 강제 전환, 루프 종료 플래그 확인 필요
