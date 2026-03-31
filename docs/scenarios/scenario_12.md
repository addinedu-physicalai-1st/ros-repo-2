# 시나리오 12: 중복 사용 차단

**SM 전환:** 없음 (IDLE 유지)
**모드:** PERSON/ARUCO 공통
**관련 요구사항:** UR-21b, SR-19

---

## 개요

한 명의 사용자가 이미 로봇을 이용 중일 때, 다른 사용자가 동일 로봇 QR을 스캔해 접속하면 로그인을 차단하고 안내 메시지를 표시한다. 기존 사용자의 세션이 완전히 종료된 이후에만 새 로그인이 가능하다.

---

## 기능 체크리스트

| 완료 | 기능 |
|:---:|---|
| [ ] | `GET /cart/<robot_id>`: session_check → `in_use`이면 blocked.html 렌더링 |
| [ ] | `POST /login`: `ROBOT.active_user_id` NULL 여부 확인 (SR-19) |
| [ ] | `active_user_id != NULL` → `{"error": "already_in_use"}` 반환 |
| [ ] | 브라우저: session_check 단계 → blocked.html ("사용 중" 전용 화면) |
| [ ] | 브라우저: login 단계 race condition → login.html에 오류 메시지 표시 |
| [ ] | 차단 시 쿠키 미발급 (세션 생성 안 함) |
| [ ] | 정상 복귀/도난 해제 → `publish_status(mode="IDLE")` 즉시 전송 → `active_user_id = NULL` |
| [ ] | control_service cleanup 스레드: `ROBOT_TIMEOUT_SEC(=30s)` 기준 `last_seen` timeout → `active_user_id = NULL` |
| [ ] | `active_user_id = NULL` 이후 새 로그인 성공 확인 |

---

## 전제조건

- 사용자 A가 로봇 #54를 이미 사용 중 (`ROBOT.active_user_id = user_A_id`)
- 사용자 B가 동일 로봇 QR을 스캔해 `/cart/54`에 접속

---

## 흐름

```
────── 경로 1: QR 스캔 시점에 이미 사용 중 ──────
사용자 B: GET /cart/54
    ↓
customer_web: TCP → control_service: session_check {"robot_id": 54}
    → active_user_id != NULL → {"status": "in_use"}
    ↓
customer_web: blocked.html 렌더링
    → "현재 다른 사람이 이 카트를 사용 중입니다" 표시

────── 경로 2: session_check 통과 후 login 시도 시 이미 사용 중 (Race condition) ──────
사용자 B: GET /cart/54 → session_check → available → login.html 표시
    ↓
사용자 B: POST /login → {"robot_id": 54, "user_id": "B", "password": "..."}
    ↓
customer_web: TCP → control_service: login
    ↓
control_service: login 처리
    1. USER/CARD 인증 → 성공
    2. ROBOT 테이블: SELECT active_user_id FROM robot WHERE robot_id=54
       → active_user_id = user_A_id (NULL 아님) ← 다른 사용자가 먼저 로그인
    3. → {"error": "already_in_use"} 반환
    ↓
customer_web: POST /login 응답 처리
    → error == "already_in_use"
    → 로그인 화면에 오류 메시지 표시 (쿠키 설정 안 함)
    → "다른 사용자가 방금 이 카트를 사용하기 시작했습니다. 잠시 후 다시 시도하세요."
```

---

## active_user_id 초기화 시점

| 이벤트 | 처리 | 지연 |
|---|---|---|
| 정상 복귀 (session_ended → IDLE) | `publish_status(mode="IDLE")` 즉시 전송 → `active_user_id = NULL` | 즉시 |
| 도난 해제 (dismiss_to_idle) | `publish_status(mode="IDLE")` 즉시 전송 → `active_user_id = NULL` | 즉시 |
| 로봇 재시작/연결 끊김 | `last_seen` 기준 `ROBOT_TIMEOUT_SEC(=30s)` 초과 → cleanup job이 NULL 처리 | 최대 30s |
| 브라우저 강제 종료 | Pi heartbeat는 계속 발행됨 → timeout 발생 안 함. Pi 재시작 또는 ROBOT_TIMEOUT_SEC 경과 시 해제 | Pi 상태에 따라 다름 |

> **ROBOT_TIMEOUT_SEC = 30s** — control_service 백그라운드 cleanup 스레드가 10초 주기로 확인.
> `last_seen < now - 30s` 이면 `active_user_id = NULL` 처리.
> scaffold_plan.md `control_service/main_node.py`에 cleanup 스레드 구현 필요.

---

## 기대 결과

| 상황 | 결과 |
|---|---|
| QR 스캔 시 이미 사용 중 | blocked.html 표시 ("사용 중" 안내) |
| session_check 후 race condition | login.html에 오류 메시지 ("방금 다른 사용자가 시작") |
| 기존 사용자 정상 복귀 후 재시도 | 즉시 로그인 가능 |
| 로봇 재시작/통신 끊김 30초 후 | cleanup 스레드가 NULL 처리 → 로그인 가능 |

## UI 검토

| 화면 | 필수 요소 |
|---|---|
| `blocked.html` | "현재 다른 사람이 이 카트를 사용 중입니다" + 뒤로 가기 버튼. 새로고침 버튼으로 재확인 가능 |
| `login.html` (오류) | already_in_use 오류 메시지 — "방금 다른 사용자가 사용을 시작했습니다. 잠시 후 다시 시도하세요." auth_failed와 구분된 메시지 사용 |

---

## 검증 방법

```bash
# ROBOT 테이블 active_user_id 확인
sqlite3 src/control_center/control_service/data/control.db \
  "SELECT robot_id, active_user_id FROM robot;"

# 중복 로그인 시도 (curl)
curl -X POST http://localhost:5000/login \
  -d "robot_id=54&user_id=B&password=test"
# → "already_in_use" 오류 메시지 확인

# 기존 세션 종료 후 재시도
# → 로그인 성공 확인
```
