# 시나리오 02: 주인 등록

**SM 전환:** `REGISTERING → TRACKING`
**모드:** PERSON(포즈 스캔) / ARUCO(마커 ID 등록) — 동작 방식 상이
**관련 패키지:** shoppinkki_core, shoppinkki_perception

---

## 개요

REGISTERING 상태에서 로봇이 주인을 식별하기 위한 등록 절차를 수행한다. PERSON 모드는 4방향 포즈 스캔으로 HSV 히스토그램을 저장하고, ARUCO 모드는 인형에 부착된 마커 ID를 감지해 target_id를 저장한다. 등록 완료 후 TRACKING으로 전환된다.

---

## 기능 체크리스트

| 완료 | 기능 |
|:---:|---|
| [ ] | PERSON: `camera_mode = "POSE_SCAN"` 설정 |
| [ ] | PERSON: `threading.Thread(target=pose_scanner.scan, args=(...)).start()` — 괄호 없이 함수 객체 전달 |
| [ ] | PERSON: front/right/back/left 4방향 순서 촬영 |
| [ ] | PERSON: 방향별 YOLO bbox 검출 → HSV 히스토그램 추출 |
| [ ] | PERSON: 방향 완료마다 buzzer 신호음 |
| [ ] | PERSON: `on_direction_done` → `send_event("pose_scan_progress", {"direction": ...})` → 브라우저 진행 표시 갱신 |
| [ ] | PERSON: POSE_DATA Pi DB 저장 (hsv_top, hsv_bottom) |
| [ ] | ARUCO: `camera_mode = "ARUCO_SCAN"` 설정 |
| [ ] | ARUCO: `send_event("registering", {"mode": "ARUCO"})` → 브라우저 스피너 + 마커 안내 표시 |
| [ ] | ARUCO: `threading.Thread(target=aruco_tracker.register_target).start()` — 괄호 없이 함수 객체 전달 |
| [ ] | ARUCO: `detectMarkers()` 성공 시 `target_id` 저장 |
| [ ] | 등록 완료 → `sm.trigger('registration_done')` + `send_event("registration_done", {})` |
| [ ] | SM: `REGISTERING → TRACKING` 전환 |
| [ ] | `on_enter_TRACKING`: `camera_mode` 전환 + BTTracking 시작 |

---

## 전제조건

- SM = REGISTERING
- 별도 스레드로 등록 루틴 실행 중

---

## 흐름 — PERSON 모드

```
on_enter_REGISTERING
    → camera_mode = "POSE_SCAN"
    → publisher.send_event("pose_scan_progress", {"direction": "start"})
      ← 브라우저 pose_scan.html에 스캔 시작 알림
    → threading.Thread(
          target=pose_scanner.scan,          ← ✅ () 없이 함수 객체 전달
          args=(session_id, _on_direction_done)
      ).start()

pose_scanner.scan()  ← 별도 스레드에서 blocking 실행
    front 방향 촬영 → YOLO bbox 검출 → HSV 히스토그램 추출
        → _on_direction_done("front") 호출
            → publisher.send_event("pose_scan_progress", {"direction": "front"})
            → 브라우저 pose_scan.html 진행 표시 갱신 (1/4)
            → buzzer 신호음 1회
    right 방향 촬영 → _on_direction_done("right") → 진행 표시 (2/4)
    back 방향 촬영  → _on_direction_done("back")  → 진행 표시 (3/4)
    left 방향 촬영  → _on_direction_done("left")  → 진행 표시 (4/4)
    → POSE_DATA (hsv_top, hsv_bottom) → Pi DB 저장
    → sm.trigger('registration_done')
    → publisher.send_event("registration_done", {})
      ← 브라우저 main.html로 자동 이동

SM: REGISTERING → TRACKING
    → on_enter_TRACKING: camera_mode = "YOLO", BTTracking 시작
```

브라우저(pose_scan.html)는 WebSocket(채널 A)으로 `pose_scan_progress` 이벤트를 수신해 진행 상태 표시.
채널 A 추가 메시지 타입:
- `{"type": "pose_scan_progress", "direction": "front"|"right"|"back"|"left"|"start"}`
- `{"type": "registration_done"}`

> **구현 주의:** `threading.Thread(target=pose_scanner.scan())` 처럼 `()` 를 붙이면
> `scan()`이 메인 스레드에서 즉시 실행되고 반환값(`None` 또는 list)이 `target`에 들어가
> 별도 스레드가 생성되지 않는다. 반드시 `target=pose_scanner.scan` (괄호 없음) 으로 작성.

---

## 흐름 — ARUCO 모드

```
on_enter_REGISTERING
    → camera_mode = "ARUCO_SCAN"
    → publisher.send_event("registering", {"mode": "ARUCO"})
      ← 브라우저 main.html에 스피너 + "마커를 카메라에 보여주세요" 안내 표시
    → threading.Thread(
          target=aruco_tracker.register_target   ← ✅ () 없이 함수 객체 전달
      ).start()

aruco_tracker.register_target()  ← 별도 스레드에서 blocking 실행
    카메라 루프에서 ArUco 마커 감지될 때까지 대기 (타임아웃 없음)
    → detectMarkers() 성공 → target_id = marker_id 저장
    → sm.trigger('registration_done')
    → publisher.send_event("registration_done", {})
      ← 브라우저 스피너 종료, 정상 추종 UI로 전환

SM: REGISTERING → TRACKING
    → on_enter_TRACKING: camera_mode = "ARUCO", BTTracking 시작
```

포즈 스캔 없음. 카트 위 인형에 부착된 ArUco 마커를 카메라에 보여주면 즉시 등록.

채널 A 추가 메시지 타입:
- `{"type": "registering", "mode": "ARUCO"}` — 스피너 + 안내 문구 표시
- `{"type": "registration_done"}` — 스피너 종료, 추종 UI 전환

---

## 기대 결과

| 항목 | PERSON | ARUCO |
|---|---|---|
| SM 상태 | TRACKING | TRACKING |
| Pi DB POSE_DATA | hsv_top/bottom 저장 | 없음 (불필요) |
| camera_mode | "YOLO" | "ARUCO" |
| BTTracking | 시작됨 | 시작됨 |
| 브라우저 | main.html 이동 | 변화 없음 |

---

## 검증 방법

```bash
# SM 상태 확인
ros2 topic echo /robot_54/status

# Pi DB POSE_DATA 확인 (PERSON 모드)
sqlite3 src/shoppinkki/shoppinkki_core/data/pi.db \
  "SELECT * FROM pose_data ORDER BY created_at DESC LIMIT 1;"

# BTTracking /cmd_vel 발행 확인
ros2 topic echo /cmd_vel
```

---

## UI 검토

| 화면 | 상태 | 필수 요소 |
|---|---|---|
| `pose_scan.html` | 스캔 전 | "카트를 바라보고 서 주세요" 안내, 시작 버튼 또는 자동 시작 |
| `pose_scan.html` | 스캔 중 | 현재 방향 표시 (예: "정면 → 우측 → 후면 → 좌측"), 진행바 또는 아이콘 4개, 방향별 완료 시 체크 표시 |
| `pose_scan.html` | 완료 | "등록 완료" 표시 후 자동으로 `main.html` 이동 |
| `main.html` (ARUCO) | 등록 대기 | 스피너 + "카트 위 마커를 카메라에 보여주세요" 문구. 등록 완료(`registration_done`) 수신 시 스피너 제거하고 일반 UI 전환 |

## 예외 케이스

- **포즈 스캔 중 사람 미검출** → 해당 방향 재시도 (최대 3회 후 건너뜀)
- **ArUco 마커 장시간 미감지** → 타임아웃 없음 (사용자가 마커를 보여줄 때까지 대기). 단, 브라우저에는 대기 중임을 스피너로 지속 표시해야 함
