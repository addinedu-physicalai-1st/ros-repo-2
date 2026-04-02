# 시나리오 13: 관제 — 실시간 로봇 모니터링

**SM 전환:** 없음 (모니터링 전용)
**관련 패키지:** admin_ui, control_service

---

## 개요

관제 대시보드(admin_ui)가 기동되어 두 로봇(#54, #18)의 현재 상태를 실시간으로 표시한다.
모드, 위치(맵 오버레이), 배터리, 활성 사용자를 1~2Hz로 갱신하며 로봇이 오프라인이면
별도 상태로 표시한다.

> **아키텍처:** admin_ui은 control_service와 **별도 프로세스**. **채널 B(TCP)**로 연결된다.
> control_service가 1~2Hz로 로봇 상태를 admin_ui에 TCP push. admin_ui은 이를 수신해 UI 갱신.

---

## 기능 체크리스트

| 완료 | 기능 |
|:---:|---|
| [ ] | admin_ui 기동 시 control_service에 TCP 연결 (채널 B) |
| [ ] | control_service: `/robot_<id>/status` 수신마다 ROBOT 테이블 갱신 |
| [ ] | control_service: 상태 갱신 시 admin_ui에 TCP push: `{"type": "status", "robot_id": ..., "mode": ..., ...}` |
| [ ] | admin_ui: TCP 수신 메시지 파싱 → UI 갱신 |
| [ ] | admin_ui UI: 로봇 카드 2개 (#54, #18) 표시 |
| [ ] | 로봇 카드: 현재 모드, 배터리 %, 활성 사용자 ID, 좌표 표시 |
| [ ] | 지도 이미지(`shop_map.png`) 위에 로봇 위치 오버레이 (dot 또는 화살표 아이콘) |
| [ ] | 배터리 20% 이하 → 배터리 표시 빨간색 강조 |
| [ ] | 로봇 `last_seen` 기준 OFFLINE 감지 → 로봇 카드 회색 처리 + "오프라인" 뱃지 |
| [ ] | 1~2Hz 갱신 (control_service heartbeat 수신 주기와 동기) |

---

## 전제조건

- control_service 기동 중 (TCP 포트 리스닝)
- admin_ui이 TCP로 control_service에 연결됨 (채널 B)
- `/robot_54/status`, `/robot_18/status` 토픽 수신 중
- `shop_map.png` 맵 이미지 로드됨

---

## 흐름

```
admin_ui 기동
    → TCP 연결: control_service:8080 (채널 B)
    → 맵 이미지 로드, 로봇 카드 UI 초기화
    ↓
control_service: /robot_<id>/status 수신 (1~2Hz)
    → ROBOT 테이블 갱신 (current_mode, pos_x, pos_y, battery_level, last_seen)
    → TCP push → admin_ui:
      {"type": "status", "robot_id": 54, "mode": "TRACKING",
       "pos_x": 1.2, "pos_y": 0.8, "battery": 72}
    ↓
admin_ui: TCP 메시지 수신 → UI 갱신
    → 로봇 카드: 모드 뱃지, 배터리 바, 사용자 ID
    → 지도 오버레이: pos_x, pos_y → 픽셀 좌표 변환 후 dot 갱신
```

### 좌표 → 픽셀 변환

```python
# 맵 yaml에서 resolution, origin을 읽어 변환
def world_to_pixel(x, y, origin_x, origin_y, resolution, img_height):
    px = int((x - origin_x) / resolution)
    py = int(img_height - (y - origin_y) / resolution)  # y축 반전
    return px, py
```

---

## 기대 결과

| 항목 | 기대값 |
|---|---|
| 로봇 카드 갱신 주기 | 1~2Hz (status 수신 주기와 동기) |
| 위치 오버레이 | 실제 AMCL 위치와 시각적으로 일치 |
| 배터리 경고 | 20% 이하 시 빨간색 강조 |
| 오프라인 감지 | last_seen > ROBOT_TIMEOUT_SEC(30s) 시 "오프라인" 뱃지 |

---

## UI 검토

| 요소 | 내용 |
|---|---|
| 로봇 카드 레이아웃 | 로봇 ID(#54/18), 모드 뱃지(색상 구분), 배터리 바, 사용자 ID, 좌표 |
| 맵 오버레이 | shop_map.png 위에 로봇별 아이콘(색상 구분). 아이콘 방향은 yaw 기반 회전 |
| 오프라인 상태 | 카드 전체 회색 처리, 위치 아이콘 X 표시 |
| 다중 알람 알림 | 알람 발생 시 해당 로봇 카드 빨간 테두리 (Scenario 14 연계) |

---

## 검증 방법

```bash
# 두 로봇 status 발행 확인
ros2 topic hz /robot_54/status
ros2 topic hz /robot_18/status

# ROBOT 테이블 실시간 상태 확인
watch -n 1 'sqlite3 src/control_center/control_service/data/control.db \
  "SELECT robot_id, current_mode, pos_x, pos_y, battery_level, last_seen FROM robot;"'

# admin_ui 기동 (별도 프로세스)
ros2 run admin_ui admin_ui
# 또는: python3 src/control_center/admin_ui/admin_ui/main.py
```
