# 시나리오 03: 주인 추종

**SM 전환:** `TRACKING` (정상 추종 중)
**모드:** PERSON/ARUCO 공통 (거리 추정 방식 상이)
**관련 패키지:** shoppinkki_core, shoppinkki_perception

---

## 개요

TRACKING 상태에서 BTTracking이 30Hz로 동작하며 주인을 따라다닌다. PERSON 모드는 YOLO 바운딩박스 넓이로 거리를 추정하고, ARUCO 모드는 tvec Z 값으로 실제 거리를 측정한다. RPLiDAR로 전방 장애물을 감지해 충돌을 방지한다.

---

## 기능 체크리스트

| 완료 | 기능 |
|:---:|---|
| [ ] | 카메라 루프: 매 프레임 `owner_detector.run(frame, camera_mode)` 호출 |
| [ ] | Detection 결과를 `_latest`에 스레드 세이프하게 저장 (threading.Lock) |
| [ ] | BTTracking 30Hz tick 실행 |
| [ ] | PERSON: `error_z = TARGET_AREA - detection.area` (px² 기반 거리 추정) |
| [ ] | ARUCO: `error_z = TARGET_DIST_M - detection.distance` (tvec m 기반) |
| [ ] | 좌우: `angular_z = -KP_ANGLE * error_x` 계산 및 클리핑 |
| [ ] | 전후: `linear_x = KP_DIST * error_z` 계산 및 클리핑 |
| [ ] | `/cmd_vel` publish |
| [ ] | RPLiDAR `/scan` 전방 ±30° 장애물 감지 → `linear_x` 감속 (0으로 제한) |
| [ ] | N=30 프레임 연속 미검출 → `sm.trigger('owner_lost')` |
| [ ] | `test_bt_tracking.py` 통과 (MockOwnerDetector 사용) |

---

## 전제조건

- SM = TRACKING
- BTTracking 스레드 실행 중 (30Hz tick)
- PERSON: camera_mode = "YOLO", OwnerDetector 로드됨
- ARUCO: camera_mode = "ARUCO", ArucoTracker target_id 등록됨

---

## 흐름

```
카메라 루프 (매 프레임)
    → owner_detector.run(frame, camera_mode)
    → Detection 결과를 _latest에 저장 (threading.Lock)

BTTracking.update() @ 30Hz
    → detection = owner_detector.get_latest()
    → 감지됨: P-Control 계산 → /cmd_vel publish
    → 미감지: miss_count++
        miss_count >= N(=30) → sm.trigger('owner_lost') → FAILURE
```

### P-Control 계산 (모드별)

```python
# PERSON 모드 — 바운딩박스 넓이로 거리 추정
error_x = detection.cx - IMAGE_WIDTH / 2       # 좌우 각도 오차 (px), IMAGE_WIDTH=640
error_z = TARGET_AREA - detection.area          # 거리 오차 (px²)
linear_x  = KP_DIST_PERSON * error_z           # PERSON 전용 게인

# ARUCO 모드 — tvec Z로 실제 거리 측정
error_x = detection.cx - IMAGE_WIDTH / 2       # 좌우 각도 오차 (px)
error_z = TARGET_DIST_M - detection.distance   # 거리 오차 (m)
linear_x  = KP_DIST_ARUCO * error_z            # ARUCO 전용 게인

# 공통
angular_z = -KP_ANGLE * error_x
# 클리핑: linear_x ∈ [LINEAR_X_MIN, LINEAR_X_MAX], angular_z ∈ [-ANGULAR_Z_MAX, ANGULAR_Z_MAX]
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

# 단위 테스트로 P-Control 계산 검증 (Mock Detection 사용)
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
| `IMAGE_WIDTH` | 640 | 카메라 가로 해상도 (px). `error_x` 계산 기준. config.py에 정의 필수 |
| `KP_ANGLE` | 0.002 | 좌우 각속도 이득 (공통) |
| `KP_DIST_PERSON` | 0.0001 | 거리 속도 이득 — PERSON 전용 (px² 단위). `KP_DIST`와 별도 상수로 분리 필요 |
| `KP_DIST_ARUCO` | 0.5 | 거리 속도 이득 — ARUCO 전용 (m 단위). `KP_DIST`와 별도 상수로 분리 필요 |
| `TARGET_AREA` | 40000 | PERSON 목표 bbox 넓이 (px²) |
| `TARGET_DIST_M` | 0.8 | ARUCO 목표 추종 거리 (m). scaffold_plan.md `config.py` 초기값 0.5m → **0.8m로 수정** |
| `MISS_COUNT_MAX` | 30 | owner_lost 판정 연속 미감지 프레임 수 |
| `OBSTACLE_DIST` | 0.3 | 전방 장애물 감속 거리 (m) |
| `LINEAR_X_MAX` | 0.3 | 최대 전진 선속도 (m/s). 클리핑 기준 |
| `LINEAR_X_MIN` | -0.15 | 최대 후진 선속도 (m/s). 클리핑 기준 |
| `ANGULAR_Z_MAX` | 1.0 | 최대 각속도 (rad/s). 클리핑 기준 |

> **config.py 수정 필요:** scaffold_plan.md의 `KP_DIST = 0.5` 단일 상수는
> PERSON/ARUCO 두 모드의 단위(px² vs m)가 달라 공유 불가.
> `KP_DIST_PERSON = 0.0001`, `KP_DIST_ARUCO = 0.5`로 분리하고,
> `IMAGE_WIDTH = 640`, `TARGET_DIST_M = 0.8`을 추가해야 함.
