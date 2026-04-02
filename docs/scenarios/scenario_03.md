# 시나리오 03: 주인 추종

**SM 전환:** `TRACKING` (정상 추종 중)
**관련 패키지:** shoppinkki_core, shoppinkki_perception

---

## 개요

TRACKING 상태에서 BTTracking이 30Hz로 동작하며 주인 인형을 따라다닌다. 커스텀 YOLO 모델이 "인형" 클래스를 감지하고, ReID 특징 벡터 + 색상 히스토그램으로 REGISTERING 시 등록한 주인 인형을 식별한다. 바운딩박스 넓이(px²)로 거리를 추정해 P-Control로 추종하며, RPLiDAR로 전방 장애물을 감지해 충돌을 방지한다.

---

## 기능 체크리스트

| 완료 | 기능 |
|:---:|---|
| [ ] | 카메라 루프: 매 프레임 `doll_detector.run(frame)` 호출 |
| [ ] | `run(frame)` 내부: YOLO로 "인형" 클래스 감지 → ReID+색상 히스토그램으로 주인 인형 매칭 |
| [ ] | Detection 결과(`cx`, `area`, `reid_score`)를 `_latest`에 스레드 세이프하게 저장 (threading.Lock) |
| [ ] | BTTracking 30Hz tick 실행 |
| [ ] | `error_z = TARGET_AREA - detection.area` (bbox 넓이 기반 거리 추정) |
| [ ] | `error_x = detection.cx - IMAGE_WIDTH / 2` (좌우 각도 오차) |
| [ ] | `angular_z = -KP_ANGLE * error_x` 계산 및 클리핑 |
| [ ] | `linear_x = KP_DIST * error_z` 계산 및 클리핑 |
| [ ] | `/cmd_vel` publish |
| [ ] | RPLiDAR `/scan` 전방 ±30° 장애물 감지 → `linear_x` 감속 (0으로 제한) |
| [ ] | N=30 프레임 연속 미검출 → `sm.trigger('owner_lost')` |
| [ ] | `test_bt_tracking.py` 통과 (MockDollDetector 사용) |

---

## 전제조건

- SM = TRACKING
- BTTracking 스레드 실행 중 (30Hz tick)
- `doll_detector.is_ready() == True` (REGISTERING 단계에서 주인 인형 등록 완료)

---

## 흐름

```
카메라 루프 (매 프레임)
    → doll_detector.run(frame)
      ├─ YOLO 추론: "인형" 클래스 bbox 감지
      ├─ 각 bbox에 대해 ReID 특징 벡터 + 색상 히스토그램 계산
      ├─ 등록된 주인 인형 템플릿과 유사도 비교 (reid_score)
      └─ 가장 높은 reid_score 가진 결과를 _latest에 저장 (Lock)

BTTracking.update() @ 30Hz
    → detection = doll_detector.get_latest()
    → 감지됨: P-Control 계산 → /cmd_vel publish
    → 미감지: miss_count++
        miss_count >= N(=30) → sm.trigger('owner_lost') → FAILURE
```

### P-Control 계산

```python
# bbox 넓이로 거리 추정 — REGISTERING 시 등록한 동일 인형 기준
error_x = detection.cx - IMAGE_WIDTH / 2   # 좌우 각도 오차 (px), IMAGE_WIDTH=640
error_z = TARGET_AREA - detection.area     # 거리 오차 (px²), TARGET_AREA=40000

angular_z = -KP_ANGLE * error_x            # 좌우 방향 제어
linear_x  = KP_DIST * error_z             # 전후 거리 제어

# 클리핑
linear_x  = max(LINEAR_X_MIN, min(LINEAR_X_MAX, linear_x))
angular_z = max(-ANGULAR_Z_MAX, min(ANGULAR_Z_MAX, angular_z))
```

### RPLiDAR 전방 장애물 감지

```
/scan 구독 콜백
    angle_min ~ angle_max 순회 (angle_increment 단위)
    -π/6 <= angle <= π/6 (전방 ±30°) 범위 필터링
    → 유효 거리(range_min < r < range_max) 중 최솟값 < OBSTACLE_DIST(=0.3m)
        → linear_x = min(linear_x, 0)  (전진 차단, 후진은 허용)

※ Pinky Pro URDF: lidar frame 기준 0rad = 로봇 정면 방향
```

---

## 기대 결과

| 상황 | /cmd_vel |
|---|---|
| 주인이 정면 적정 거리 | linear_x≈0, angular_z≈0 |
| 주인이 좌측으로 이동 | angular_z > 0 (CCW) |
| 주인이 멀어짐 | linear_x > 0 (전진) |
| 주인이 너무 가까움 | linear_x < 0 (후진) |
| 전방 장애물 + 주인 멀어짐 | linear_x = 0 (정지) |

---

## 검증 방법

```bash
# cmd_vel 실시간 확인
ros2 topic echo /cmd_vel

# RPLiDAR 전방 거리 확인 (전방 ±30° 범위 최솟값)
ros2 topic echo /scan --once | grep -A2 "ranges"

# FPS 측정 (measure_fps.py는 scaffold 단계에서 스텁 — 구현 후 사용)
# python3 src/shoppinkki/shoppinkki_perception/scripts/measure_fps.py

# 단위 테스트로 P-Control 계산 검증 (MockDollDetector 사용)
python3 -m pytest src/shoppinkki/shoppinkki_core/test/test_bt_tracking.py -v
```

---

## UI 검토

| 화면 | 필수 요소 | 비고 |
|---|---|---|
| `main.html` (TRACKING 중) | 현재 모드 뱃지 ("추종 중" 등), 배터리 퍼센트, 장바구니 버튼, 물건 찾기 버튼 | status WebSocket 수신마다 갱신 |
| `main.html` (장애물 감지) | 별도 UI 없음 — 로봇이 알아서 멈춤. 사용자에게 피드백 불필요 | 속도 제어는 Pi 내부 처리 |

---

## 튜닝 파라미터

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `IMAGE_WIDTH` | 640 | 카메라 가로 해상도 (px). `error_x` 계산 기준 |
| `KP_ANGLE` | 0.002 | 좌우 각속도 이득 |
| `KP_DIST` | 0.0001 | 거리 속도 이득 (px² 단위) |
| `TARGET_AREA` | 40000 | 목표 bbox 넓이 (px²) — 적정 추종 거리 기준 |
| `N_MISS_FRAMES` | 30 | owner_lost 판정 연속 미감지 프레임 수 |
| `OBSTACLE_DIST` | 0.3 | 전방 장애물 감속 거리 (m) |
| `LINEAR_X_MAX` | 0.3 | 최대 전진 선속도 (m/s) |
| `LINEAR_X_MIN` | -0.15 | 최대 후진 선속도 (m/s) |
| `ANGULAR_Z_MAX` | 1.0 | 최대 각속도 (rad/s) |
