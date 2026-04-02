# 시나리오 06: 물건 추가

**SM 전환:** `WAITING/TRACKING → ITEM_ADDING → TRACKING`

---

## 개요

사용자가 [물건 추가] 버튼을 눌러 QR 스캔 모드로 진입한다. 카트에 놓인 상품의 QR 코드를 연속으로 스캔해 장바구니에 추가할 수 있으며, 동일 제품 중복 스캔은 자동으로 방지된다. 30초 무활동 또는 [확인] 버튼으로 TRACKING으로 복귀한다.

---

## 기능 체크리스트

| 완료 | 기능 |
|:---:|---|
| [ ] | `on_enter_ITEM_ADDING`: `bt_runner.stop()` — 진입 전 기존 BT(BTTracking/BTWaiting) 중단 |
| [ ] | `on_enter_ITEM_ADDING`: `camera_mode = "QR"` 설정 |
| [ ] | `on_enter_ITEM_ADDING`: `_scanned_products` 를 현재 CART_ITEM DB 기반으로 초기화 (세션 통합 중복 방지) |
| [ ] | `on_enter_ITEM_ADDING`: QRScanner 시작 |
| [ ] | `on_enter_ITEM_ADDING`: 30초 타임아웃 타이머 시작 |
| [ ] | QR 스캔: `<상품명>:<가격>` 형식 파싱 |
| [ ] | 스캔 성공: `_scanned_products`에 추가 (중복 방지) |
| [ ] | 스캔 성공: 30초 타이머 리셋 (연속 스캔 시 초기화) |
| [ ] | 스캔 성공: REST `POST /cart/<session_id>/items` → `/robot_<id>/cart` topic publish |
| [ ] | 스캔 성공: `send_event('item_added')` → 브라우저 장바구니 UI 갱신 |
| [ ] | 동일 제품 재스캔 → 무시 (set 중복 방지) |
| [ ] | 잘못된 QR 형식 → 무시하고 계속 스캔 |
| [ ] | [확인] 버튼 → `sm.trigger('qr_scanned')` → TRACKING |
| [ ] | 30초 무활동 → `sm.trigger('item_cancelled')` → TRACKING |
| [ ] | [취소] 버튼 → `sm.trigger('item_cancelled')` → TRACKING |
| [ ] | `on_exit_ITEM_ADDING`: QRScanner 정지, camera_mode 복구 |
| [ ] | `test_qr_scanner.py` 통과 |

---

## 전제조건

- SM = WAITING 또는 TRACKING
- 사용자가 브라우저 cart.html에서 [물건 추가] 버튼 클릭

---

## 흐름

```
브라우저: {"cmd": "mode", "value": "ITEM_ADDING"}
    ※ 채널 A 명세 패턴에 맞춤. 기존 문서의 {"cmd": "to_item_adding"}은 오기.
    → customer_web TCP relay → control_service
    → control_service ROS publish → /robot_<id>/cmd: {"cmd": "mode", "value": "ITEM_ADDING"}
    ↓
shoppinkki_core: sm.trigger('to_item_adding')
    → WAITING/TRACKING → ITEM_ADDING
    ↓
on_enter_ITEM_ADDING
    → bt_runner.stop()             ← TRACKING이든 WAITING이든 기존 BT 반드시 중단
    → camera_mode = "QR"
    → _scanned_products = {item['product_name'] for item in rest_get(f'/cart/{session_id}/items')}
      ← set()이 아닌 REST API 기반 초기화 (세션 내 통합 중복 방지)
    → qr_scanner.start(on_scanned=_on_qr_scanned, on_timeout=_on_qr_timeout)
        → 30초 타이머 시작

────── QR 스캔 루프 ──────
카메라 루프 → qr_scanner.run(frame)
    → detectAndDecode() → "콜라:1500" 파싱
    → "콜라" in _scanned_products? → 무시 (중복)
    → 아니면: _scanned_products.add("콜라")
              타이머 리셋 (30초 재시작)
              _on_qr_scanned("콜라", 1500) 호출
    ↓
_on_qr_scanned(name, price)
    → REST POST /cart/<session_id>/items {"product_name": name, "price": price}
    → /robot_<id>/cart topic publish
    → publisher.send_event('item_added', {name, price})
    → SM 유지 (ITEM_ADDING 지속, 연속 스캔 가능)

브라우저: [확인] 버튼 → {"cmd": "confirm_item"}
    → sm.trigger('qr_scanned') → TRACKING

────── 타임아웃 (30초 무활동) ──────
_on_qr_timeout()
    → sm.trigger('item_cancelled') → TRACKING

────── 취소 ──────
브라우저: [취소] → {"cmd": "mode", "value": "TRACKING"}
    → sm.trigger('item_cancelled') → TRACKING
```

---

## 기대 결과

| 상황 | 결과 |
|---|---|
| QR 스캔 성공 | 장바구니에 추가, 타이머 리셋, 연속 스캔 대기 |
| 동일 제품 재스캔 | 무시 (중복 방지) |
| [확인] 클릭 | TRACKING 복귀 |
| 30초 무활동 | TRACKING 복귀 (item_cancelled) |
| [취소] 클릭 | TRACKING 복귀 |

---

## 검증 방법

```bash
# 장바구니 추가 확인
sqlite3 src/control_center/control_service/data/control.db \
  "SELECT * FROM cart_item ORDER BY scanned_at DESC LIMIT 5;"

# /cart topic 발행 확인
ros2 topic echo /robot_54/cart

# QR 이미지 생성 (테스트용)
python3 -c "
import qrcode
img = qrcode.make('콜라:1500')
img.save('/tmp/qr_cola.png')
"
```

---

## QR 코드 형식

```
<상품명>:<가격>
예: 콜라:1500
    과자:800
```

### 방어적 파싱 (구현 시 적용)

```python
def parse_qr(raw: str):
    parts = raw.split(':', 1)   # maxsplit=1 — 상품명에 ':' 포함 가능
    if len(parts) != 2:
        return None             # ':' 없음 → 무시
    name, price_str = parts[0].strip(), parts[1].strip()
    if not name:
        return None
    try:
        price = int(price_str)
        if price < 0:
            return None         # 음수 가격 → 무시
    except ValueError:
        return None             # 비숫자 → 무시
    return name, price
```

파싱 실패 케이스: `:` 없음 / 가격 비숫자 / 음수 가격 → 모두 무시하고 계속 스캔.

## UI 검토

| 상황 | 브라우저 |
|---|---|
| ITEM_ADDING 진입 | "QR 코드를 스캔하세요" 안내 + 장바구니 목록 + [확인] [취소] 버튼 |
| QR 스캔 성공 | 장바구니 목록에 상품 추가 애니메이션 (cart WebSocket 수신 시 갱신) |
| 동일 상품 재스캔 | 중복 안내 토스트 ("이미 담긴 상품입니다") |
| 30초 타임아웃 | 자동으로 TRACKING 복귀 (브라우저 별도 알림 없어도 됨 — status 갱신으로 UI 전환) |
