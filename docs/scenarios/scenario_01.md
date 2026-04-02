# 시나리오 01: 세션 시작

**SM 전환:** `IDLE → REGISTERING`
**관련 패키지:** shoppinkki_core, customer_web, control_service

---

## 개요

쇼핑 카트 로봇에 부착된 QR 코드를 고객이 스캔해 접속하고, ID/PW 로그인을 완료하면 로봇이 IDLE에서 REGISTERING 상태로 전환되는 최초 진입 흐름을 검증한다. 중복 사용 차단, 인증 실패, TCP 재연결 등 예외도 포함한다.

---

## 기능 체크리스트

| 완료 | 기능 |
|:---:|---|
| [ ] | IDLE 상태에서 LCD에 `/cart/<robot_id>` QR 코드 표시 |
| [ ] | `/cart/<robot_id>` 접속 시 session_check → available이면 login.html 렌더링, 사용 중이면 blocked.html 표시 |
| [ ] | POST /login → USER/CARD 인증 |
| [ ] | 로그인 시 `ROBOT.active_user_id` 중복 확인 (SR-19) |
| [ ] | 인증 성공 → `ROBOT.active_user_id = user_id` 갱신 |
| [ ] | 중앙 DB SESSION 레코드 생성 (`is_active=1`, `expires_at` 설정) |
| [ ] | 중앙 DB CART 레코드 SESSION과 동시 생성 (atomic, 같은 트랜잭션) |
| [ ] | control_service가 ROS publish → `/robot_<id>/cmd`: `start_session` (customer_web 직접 publish 아님) |
| [ ] | SM: `IDLE → REGISTERING` 전환 |
| [ ] | 로그인 성공 후 `main.html` 리다이렉트 (인형 등록 안내 표시) |
| [ ] | 인증 실패 시 로그인 화면에 오류 메시지 표시 |
| [ ] | TCP 연결 끊김 시 3초 간격 자동 재연결 |

---

## 전제조건

- 로봇이 IDLE 상태 (도킹 위치, SM=IDLE)
- LCD에 QR 코드 표시 중 (`/cart/<robot_id>`)
- ROBOT 테이블 `active_user_id = NULL`
- 사용자: USER/CARD 테이블에 등록된 계정 보유

---

## 흐름

```
사용자 QR 스캔
    │
    ▼
브라우저 → /cart/<robot_id> 접속 (customer_web, 포트 8501)
    │
    ▼
customer_web: GET /cart/<robot_id>
    → TCP → control_service: session_check
    → ROBOT.active_user_id == NULL → "available"
    → login.html 렌더링  [이미 사용 중이면 blocked.html 표시]
    │
    ▼
사용자 ID/PW 입력 → POST /login
    │
    ▼
customer_web: TCP → control_service: login
    1. USER/CARD 인증
    2. ROBOT.active_user_id 중복 확인 (SR-19)
    → 성공: ROBOT.active_user_id = user_id 갱신
    → 중앙 DB SESSION 생성 (is_active=1, expires_at 설정)
    → 중앙 DB CART 생성 (SESSION과 동일 트랜잭션)
    → 쿠키 설정 → /app/main 리다이렉트
    │
    ▼
control_service: ROS publish → /robot_<id>/cmd
    {"cmd": "start_session", "user_id": <id>}
    ※ customer_web은 ROS DDS 직접 접근 불가.
      TCP 수신 후 control_service가 ROS publisher로 중계.
    │
    ▼
shoppinkki_core: sm.trigger('start_session')
    → IDLE → REGISTERING
    → on_enter_REGISTERING: send_event("registering", {})
        ← 브라우저 main.html에 스피너 + "인형을 카메라에 보여주세요" 안내
```

---

## 기대 결과

| 항목 | 기대값 |
|---|---|
| SM 상태 | REGISTERING |
| ROBOT.active_user_id | 로그인한 user_id |
| 중앙 DB SESSION | 새 레코드 생성 (`is_active=1 AND expires_at > now()`) |
| 중앙 DB CART | SESSION과 동시 생성 (session_id 동일, 1:1) |
| LCD | QR 코드 → 등록 안내 화면 |
| 브라우저 | main.html (스피너 + "인형을 카메라에 보여주세요") |

---

## 검증 방법

```bash
# SM 상태 확인
ros2 topic echo /robot_54/status

# control_service DB 확인
sqlite3 src/control_center/control_service/data/control.db \
  "SELECT active_user_id FROM robot WHERE robot_id=54;"

# 중앙 DB SESSION 확인
sqlite3 src/control_center/control_service/data/control.db \
  "SELECT session_id, robot_id, user_id, is_active, expires_at FROM session ORDER BY created_at DESC LIMIT 1;"

# 중앙 DB CART 동시 생성 확인 (session_id가 SESSION과 일치해야 함)
sqlite3 src/control_center/control_service/data/control.db \
  "SELECT s.session_id, c.cart_id FROM session s JOIN cart c USING(session_id) ORDER BY s.created_at DESC LIMIT 1;"
```

### 예제 구현 참고

```python
# control_service/tcp_server.py — login 처리 후 SESSION+CART 생성 및 ROS publish
def handle_login(robot_id, user_id, password):
    # ... 인증 및 active_user_id 중복 확인 ...
    session_id = str(uuid.uuid4())
    with db_lock:
        db.execute(
            "UPDATE robot SET active_user_id=? WHERE robot_id=?",
            (user_id, robot_id)
        )
        db.execute(
            "INSERT INTO session (session_id, robot_id, user_id, is_active, expires_at) "
            "VALUES (?, ?, ?, 1, datetime('now', '+1 hour'))",
            (session_id, robot_id, user_id)
        )
        db.execute(
            "INSERT INTO cart (session_id) VALUES (?)", (session_id,)
        )
        db.commit()
    # customer_web이 아닌 control_service가 ROS publish 담당
    ros_node.publish_cmd(robot_id, {"cmd": "start_session", "user_id": user_id})
```

---

## UI 검토

| 화면 | 필수 요소 | 비고 |
|---|---|---|
| `login.html` | 로봇 번호 표시 (`#54`), ID/PW 입력, 로그인 버튼, 오류 메시지 영역 | 어떤 카트인지 사용자가 인지할 수 있어야 함 |
| `blocked.html` | "현재 다른 사람이 이 카트를 사용 중입니다" 문구, 뒤로가기 버튼 | session_check 단계에서 already_in_use 시 렌더링 |
| `main.html` | 스피너 + "인형을 카메라에 보여주세요" 안내 문구 | REGISTERING 진입 직후 인형 등록 대기 중 표시 |

## 예외 케이스

- **이미 사용 중인 로봇** → Scenario 12 참조
- **인증 실패** → `{"error": "auth_failed"}` → 로그인 화면에 오류 메시지
- **네트워크 끊김** → TCP 재연결 루프 (3초 간격)
