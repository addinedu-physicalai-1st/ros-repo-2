# 시나리오 07: 물건 찾기 & 안내

**SM 전환:** `TRACKING → GUIDING → TRACKING`
---

## 개요

사용자가 텍스트 또는 음성(STT)으로 상품명을 검색하면 control_service가 DB에서 해당 구역을 조회해 로봇을 Nav2로 안내한다. 목적지 도착 후 TRACKING으로 복귀하며, 이동 중 취소도 가능하다.

---

## 기능 체크리스트

| 완료 | 기능 |
|:---:|---|
| [ ] | 브라우저 텍스트 입력 → `find_product` 명령 전송 |
| [ ] | STT (`webkitSpeechRecognition`, ko-KR) → `find_product` 명령 전송 (HTTPS 필요 — 미지원 환경은 텍스트 전용으로 대체) |
| [ ] | control_service: PRODUCT 테이블 `LIKE` + `ORDER BY zone_id ASC LIMIT 1` 검색 |
| [ ] | 상품 미검색 시 브라우저에 "찾을 수 없음" 알림 (GUIDING 진입 안 함) |
| [ ] | 검색 결과 브라우저 표시 + [안내받기] 버튼 활성화 (자동 navigate_to 전송 아님) |
| [ ] | 사용자 [안내받기] 클릭 → `navigate_to` 명령 전송 |
| [ ] | `sm.trigger('to_guiding', zone_id=N)` → GUIDING 진입 |
| [ ] | `on_enter_GUIDING`: `bt_runner.stop()` + BTGuiding 시작 |
| [ ] | BTGuiding: `GET /zone/<id>/waypoint` Waypoint 조회 (REST API, control_service 제공) |
| [ ] | BTGuiding: Waypoint 조회 실패(404) → FAILURE → TRACKING 복귀 + 브라우저 알림 |
| [ ] | BTGuiding: Nav2 Goal 전송 |
| [ ] | BTGuiding: `SUCCEEDED` → `arrived` → TRACKING + 브라우저 도착 알림 |
| [ ] | BTGuiding: `FAILED` → `nav_failed_guide` → TRACKING + 브라우저 실패 알림 |
| [ ] | 이동 중 [취소] → `nav2_client.cancel_goal()` → `to_tracking` → TRACKING |
| [ ] | `test_bt_guiding.py` 통과 (Mock Nav2 사용) |

---

## 전제조건

- SM = TRACKING
- 사용자가 브라우저 cart.html에서 [물건 찾기] 버튼 + 상품명 입력 또는 STT

---

## 흐름

```
브라우저: 텍스트 입력 또는 STT(ko-KR, HTTPS 필요) → {"cmd": "find_product", "query": "콜라"}
    → customer_web TCP relay → control_service TCP 수신
    ↓
control_service: find_product 처리
    → PRODUCT 테이블: SELECT zone_id, zone_name
                       FROM product p JOIN zone z USING(zone_id)
                       WHERE product_name LIKE '%콜라%'
                       ORDER BY zone_id ASC LIMIT 1
    → 결과: {zone_id: 3, zone_name: "음료 코너"}
    → TCP push → customer_web → WebSocket → 브라우저
      {"type": "find_product_result", "zone_id": 3, "zone_name": "음료 코너"}
    ↓
브라우저: 검색 결과 표시 + [안내받기] 버튼 활성화
    ※ find_product 결과만으로 자동 navigate_to 전송하지 않음.
      사용자가 [안내받기]를 눌러야 안내 시작.
    ↓
사용자: [안내받기] 클릭
    → 브라우저: {"cmd": "navigate_to", "zone_id": 3} (채널 A)
    → customer_web → TCP → control_service
    → control_service ROS publish → /robot_<id>/cmd: {"cmd": "navigate_to", "zone_id": 3}
    ↓
shoppinkki_core: on_cmd navigate_to
    → sm.trigger('to_guiding', zone_id=3) → GUIDING
    ↓
on_enter_GUIDING
    → bt_runner.stop()   ← 기존 BTTracking 중단
    → bt_runner.start(BTGuiding, zone_id=3)

BTGuiding.initialise()
    → GET http://control_service/zone/3/waypoint
      응답: {"x": 1.2, "y": 0.8}
    → 실패 시: FAILURE (→ SM: nav_failed_guide → TRACKING + 앱 알림)
    → 성공 시: nav2_client.send_goal(x=1.2, y=0.8)

BTGuiding.update() @ 30Hz
    → nav2_client.get_status()
        "SUCCEEDED" → return SUCCESS → sm.trigger('arrived') → TRACKING
        "FAILED"    → return FAILURE → sm.trigger('nav_failed_guide') → TRACKING

────── 사용자 취소 ──────
브라우저: [취소] 버튼 → {"cmd": "mode", "value": "TRACKING"}
    ↓
shoppinkki_core on_cmd (GUIDING 상태)
    → nav2_client.cancel_goal()
    → sm.trigger('to_tracking') → TRACKING
```

---

## 기대 결과

| 상황 | SM 전환 | 브라우저 알림 |
|---|---|---|
| Nav2 목표 도착 | GUIDING → TRACKING | "음료 코너에 도착했습니다" |
| Nav2 이동 실패 | GUIDING → TRACKING | "안내 이동에 실패했습니다" |
| 사용자 취소 | GUIDING → TRACKING | 없음 |
| Waypoint 조회 실패 | GUIDING → TRACKING | "구역 정보를 찾을 수 없습니다" |
| 상품 DB 미검색 | GUIDING 진입 안 함 | "해당 상품을 찾을 수 없습니다" |

---

## find_product 처리 (control_service)

```python
# DB 직접 조회 (LLM 경유 없음 — LLM은 LOW priority)
# ORDER BY zone_id ASC: 동일 상품명이 여러 구역에 있을 경우 낮은 구역 ID 우선
def find_product(query: str):
    row = db.execute(
        "SELECT p.zone_id, z.zone_name FROM product p "
        "JOIN zone z USING(zone_id) "
        "WHERE p.product_name LIKE ? "
        "ORDER BY p.zone_id ASC LIMIT 1",
        (f'%{query}%',)
    ).fetchone()
    if row:
        return {"zone_id": row["zone_id"], "zone_name": row["zone_name"]}
    return None
```

## Waypoint REST API (control_service)

BTGuiding이 진입 시 zone_id로 Waypoint를 조회하는 REST 엔드포인트.
interface_specification.md에 별도 명세 추가 필요.

```
GET /zone/<zone_id>/waypoint
응답 200: {"x": 1.2, "y": 0.8, "theta": 0.0}
응답 404: {"error": "zone_not_found"}
```

| 항목 | 값 |
|---|---|
| 호출 주체 | BTGuiding.initialise() (Pi 5 내부) |
| 제공 주체 | control_service HTTP 서버 (포트 8080) |
| 데이터 소스 | ZONE 테이블 `waypoint_x`, `waypoint_y`, `waypoint_theta` |

---

## UI 검토

| 단계 | 브라우저 요소 |
|---|---|
| 검색 입력 | 텍스트 입력창 + 검색 버튼 + STT 버튼(선택, HTTPS 환경만) |
| 검색 결과 표시 | "콜라 → 음료 코너" + [안내받기] 버튼 + [취소] 버튼 |
| GUIDING 중 | "음료 코너로 이동 중..." + [취소] 버튼 (status mode=GUIDING 수신 시) |
| 도착 | "음료 코너에 도착했습니다" 토스트 + 자동 추종 복귀 |
| 실패 | "안내 이동에 실패했습니다" 토스트 + 자동 추종 복귀 |
| 구역 미발견 | "해당 상품을 찾을 수 없습니다" 토스트 (GUIDING 진입 없음) |

> **STT 주의:** `webkitSpeechRecognition`은 HTTPS 또는 localhost 환경에서만 동작.
> 데모 환경이 `http://192.168.x.xxx:8501`이면 STT 비활성화됨.
> 텍스트 입력을 기본으로 하고 STT는 선택 기능으로 처리할 것.

## 검증 방법

```bash
# control_service find_product 직접 테스트
curl "http://localhost:8080/find_product?query=콜라"

# Waypoint API 확인
curl "http://localhost:8080/zone/3/waypoint"

# SM 전환 확인 (Gazebo)
ros2 topic echo /robot_54/status   # mode 변화: GUIDING → TRACKING
```
