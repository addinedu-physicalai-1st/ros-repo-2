# 시나리오 목록

> **목적:** 구현 완료 후 상태 전환 단위 테스트. 각 시나리오는 하나의 SM 전환(또는 독립 기능)을 검증한다.
> **실행 환경:** 실 로봇 또는 Gazebo 시뮬레이션. control_service + customer_web + admin_ui 모두 기동 상태.

**범례:**

- ⬜ 미구현
- ✅ 구현 완료 (코드 작성 완료)

---

## 세션 / 진입

| 구현 | ID | 제목 | 상태 전환 | 우선순위 |
|:---:|---|---|---|---|
| ⬜ | [SC-01](SC-01.md) | 로그인 → 인형 등록 → 추종 시작 | `CHARGING` → `IDLE` → `TRACKING` | HIGH |
| ⬜ | [SC-02](SC-02.md) | 세션 재접속 (쿠키 유효) | 세션 유지 → 메인화면 직행 | MEDIUM |
| ⬜ | [SC-03](SC-03.md) | 사용 중인 카트 접속 차단 | — (blocked.html 표시) | LOW |
| ⬜ | [SC-04](SC-04.md) | 중복 로그인 차단 | — (오류 메시지 표시) | LOW |
| ⬜ | SC-05 | 시뮬레이션 모드 진입 | `IDLE` → `TRACKING` (추종 비활성화) | MEDIUM |

## 추종 / 재탐색

| 구현 | ID | 제목 | 상태 전환 | 우선순위 |
|:---:|---|---|---|---|
| ⬜ | [SC-10](SC-10.md) | 주인 놓침 → 재발견 → 추종 복귀 | `TRACKING` → `SEARCHING` → `TRACKING` | HIGH |
| ⬜ | [SC-11](SC-11.md) | 주인 놓침 → 탐색 타임아웃 → 대기 | `TRACKING` → `SEARCHING` → `WAITING` | HIGH |

## 대기

| 구현 | ID | 제목 | 상태 전환 | 우선순위 |
|:---:|---|---|---|---|
| ⬜ | [SC-20](SC-20.md) | 사용자 [대기하기] → [따라가기] 복귀 | `TRACKING` → `WAITING` → `TRACKING` | MEDIUM |
| ⬜ | [SC-21](SC-21.md) | WAITING 타임아웃 → 빈 카트 귀환 | `WAITING` → `RETURNING` | MEDIUM |
| ⬜ | [SC-22](SC-22.md) | WAITING 타임아웃 → 미결제 LOCKED 귀환 | `WAITING` → `LOCKED` | MEDIUM |
| ⬜ | [SC-23](SC-23.md) | 대기 중 통행자 감지 → 회피 이동 | `WAITING` 내부 (BT 3) | LOW |

## 상품 안내 (GUIDING)

| 구현 | ID | 제목 | 상태 전환 | 우선순위 |
|:---:|---|---|---|---|
| ⬜ | [SC-30](SC-30.md) | 상품 검색 → 안내 → 도착 → 추종 복귀 | `TRACKING` → `GUIDING` → `WAITING` → `TRACKING` | HIGH |
| ⬜ | [SC-31](SC-31.md) | 상품 안내 중 Nav2 실패 → 추종 복귀 | `GUIDING` → `TRACKING` | MEDIUM |

## 장바구니

| 구현 | ID | 제목 | 상태 전환 | 우선순위 |
|:---:|---|---|---|---|
| ⬜ | [SC-40](SC-40.md) | 웹앱 카메라 QR 스캔으로 상품 추가 | `TRACKING` 내부 (SM 변경 없음) | HIGH |
| ⬜ | [SC-41](SC-41.md) | 장바구니 항목 삭제 | `TRACKING` 내부 (SM 변경 없음) | MEDIUM |

## 결제

| 구현 | ID | 제목 | 상태 전환 | 우선순위 |
|:---:|---|---|---|---|
| ⬜ | [SC-50](SC-50.md) | 결제 구역 진입 → 결제 완료 | `TRACKING` → `TRACKING_CHECKOUT` | HIGH |
| ⬜ | [SC-51](SC-51.md) | 미결제 상태 출구 통과 차단 | `TRACKING` 유지 (BoundaryMonitor) | HIGH |
| ⬜ | [SC-52](SC-52.md) | 결제 완료 후 쇼핑 재개 | `TRACKING_CHECKOUT` → `TRACKING` | MEDIUM |

## 귀환

| 구현 | ID | 제목 | 상태 전환 | 우선순위 |
|:---:|---|---|---|---|
| ⬜ | [SC-60](SC-60.md) | 정상 귀환 — 빈 카트 | `TRACKING` → `RETURNING` → `CHARGING` | HIGH |
| ⬜ | [SC-61](SC-61.md) | 정상 귀환 — TRACKING_CHECKOUT | `TRACKING_CHECKOUT` → `RETURNING` → `CHARGING` | HIGH |
| ⬜ | [SC-62](SC-62.md) | 미결제 보내주기 → LOCKED 귀환 | `TRACKING` → `LOCKED` → `RETURNING` → `CHARGING` | HIGH |
| ⬜ | [SC-63](SC-63.md) | LOCKED 도착 → staff_resolved | `CHARGING`(locked) → `CHARGING`(normal) | HIGH |

## 배터리 / HALTED

| 구현 | ID | 제목 | 상태 전환 | 우선순위 |
|:---:|---|---|---|---|
| ⬜ | [SC-70](SC-70.md) | 배터리 부족 → 즉시 정지 | `*` → `HALTED` | HIGH |
| ⬜ | [SC-71](SC-71.md) | HALTED → staff_resolved → CHARGING | `HALTED` → `CHARGING` | HIGH |

## 관제

| 구현 | ID | 제목 | 상태 전환 | 우선순위 |
|:---:|---|---|---|---|
| ⬜ | [SC-80](SC-80.md) | 관제 강제 종료 | `*` → `CHARGING` | MEDIUM |
| ⬜ | [SC-81](SC-81.md) | admin_goto — 위치 호출 | `IDLE` → Nav2 이동 | LOW |
| ⬜ | [SC-82](SC-82.md) | 로봇 오프라인 감지 | → `OFFLINE` | MEDIUM |

## Open-RMF

| 구현 | ID | 제목 | 상태 전환 | 우선순위 |
|:---:|---|---|---|---|
| ⬜ | [SC-90](SC-90.md) | 다중 로봇 경로 충돌 → RMF 자동 협상 | 두 로봇 `GUIDING` 동시 (SM 전환 없음) | MEDIUM |

---

## 실행 권장 순서

```
SC-01 → SC-10 → SC-11 → SC-20 → SC-21 → SC-22
→ SC-30 → SC-31 → SC-40 → SC-41
→ SC-50 → SC-51 → SC-52
→ SC-60 → SC-61 → SC-62 → SC-63
→ SC-70 → SC-71
→ SC-02 → SC-03 → SC-04 → SC-23
→ SC-80 → SC-81 → SC-82
→ SC-90
```

> HIGH 우선순위 시나리오만 먼저 통과시킨 후 MEDIUM/LOW 진행.

---

## 공통 기호

| 기호 | 의미 |
|---|---|
| `pub` | `ros2 topic pub` 명령 |
| `echo` | `ros2 topic echo` 명령 |
| `[앱]` | customer_web 브라우저 (스마트폰 또는 로컬 http://localhost:8501) |
| `[관제]` | admin_ui PyQt6 앱 |
| `→ ✅` | 예상 결과 일치 |
| `→ ❌` | 실패 조건 |
