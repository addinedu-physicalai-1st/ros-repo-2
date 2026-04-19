# 멀티로봇 시뮬레이션 + Nav2 + RMF 통합 진행 현황

> 브랜치: `feat/multi-robot-sim-nav2` | 최종 업데이트: 2026-04-12

## 아키텍처

```
RMF Task Dispatcher
    ↓ patrol task
Fleet Adapter (EasyFullControl)
    ↓ navigate callback (waypoint 순차)
    ↓ REST POST /robot/{id}/cmd
Control Service (REST :8081 + ROS)
    ↓ /robot_{id}/cmd 토픽
ShopPinkki Core (SM + BT Runner)
    ↓ BT4 Nav2GuidingBT
Nav2 (navigate_to_pose action)
    ↓ cmd_vel
Gazebo 시뮬레이션
```

## 실행 방법

```bash
# 터미널 A — 서버 (DB + control_service)
bash scripts/run_server.sh --no-ai

# 터미널 B — 시뮬레이션 (Gazebo + Nav2 x2 + core x2 + RMF)
bash scripts/run_sim.sh
# → tmux 세션 sp_sim: 0:gz  1:core54  2:core18  3:rmf

# Gazebo 로딩 완료 후 (~60초)
# core 로그에서 "Battery 100% >= 80% → IDLE" 확인

# 터미널 C — 테스트
source /opt/ros/jazzy/setup.zsh && source ~/shoppinkki/install/setup.zsh && export ROS_DOMAIN_ID=14

# 1) 두 로봇 TRACKING 모드 진입
curl -s -X POST http://localhost:8081/robot/54/cmd -H "Content-Type: application/json" -d '{"cmd":"enter_simulation"}'
curl -s -X POST http://localhost:8081/robot/18/cmd -H "Content-Type: application/json" -d '{"cmd":"enter_simulation"}'

# 2) RMF task 제출 (구역 기반 — 빈 자리 자동 선택)
python3 scripts/rmf_dispatch.py --robot pinky_54 --zone 육류
python3 scripts/rmf_dispatch.py --robot pinky_18 --zone 가전제품

# 3) 상태 확인
ros2 topic echo /fleet_states
curl -s http://localhost:8081/robots | python3 -m json.tool
```

## 완료 항목

### Phase 0: 사전 정리
- [x] 충전소 yaw 통일 (0.0)
- [x] 로봇 배치 확정: 54→P2(y=-0.899, zone 141), 18→P1(y=-0.606, zone 140)
- [x] seed_data / fleet_config / launch_utils / config.py 동기화

### Phase 1: 단일 로봇 Nav2 이동
- [x] Gazebo 멀티로봇 스폰
- [x] curl → control_service → shoppinkki_core → Nav2 이동 확인
- [x] Nav2GuidingBT 구현 (`bt_guiding.py`)
- [x] navigate_cancel 구현 (`cmd_handler.py` + `bt_guiding.cancel_nav()`)

### Phase 2: RMF Fleet Adapter 연동
- [x] EasyFullControl 로봇 등록 (pinky_54, pinky_18)
- [x] `/fleet_states` 정상 발행
- [x] `use_sim_time` launch argument
- [x] activity identifier 전달 (`handle.update(state, activity)`)
- [x] 모드 전이 기반 도착 감지 (GUIDING→WAITING → execution.finished())
- [x] REST API `/robots`로 실시간 위치 조회 (TF/status 불안정 우회)

### Phase 3: RMF 그래프 경유 이동
- [x] RMF patrol task → navigate 콜백 → waypoint 순차 이동 확인
- [x] 구역 기반 스마트 배정 (`rmf_dispatch.py --zone`)
- [x] holding point 추가 (입구/출구/교차점 13개)
- [x] 같은 목적지 navigate 재호출 시 스킵 (goal 폭주 방지)
- [x] stop() 콜백 무동작화 (RMF replan 시 Nav2 goal 유지)

## 미해결 항목

### 즉시 해결 필요
- [ ] `/clock` 토픽 미발행 — Gazebo Play 상태 확인. use_sim_time 노드 전체 영향
- [ ] inflation_radius 0.08 설정 후 좁은 통로(x=0.0 충전소) 도달 가능 여부 재확인

### Phase 4: 충돌 회피 테스트
- [ ] RMF traffic scheduler가 holding point에서 대기시키는지 검증
- [ ] 대향 테스트: 같은 복도에서 마주칠 때
- [ ] 교차 테스트: 교차점에서 순서 조율
- [ ] 동시 출발: 서로 반대 방향 goal
- [ ] 데드락 방지: 양끝에서 동시 진입

## 주요 파라미터

| 파라미터 | 값 | 파일 |
|----------|-----|------|
| inflation_radius | 0.08 | nav2_params.yaml |
| footprint_padding | 0.0 | nav2_params.yaml |
| costmap_update_timeout | 5.0 | nav2_params.yaml |
| collision_monitor PolygonStop | 전방 12cm, 뒤 2cm | nav2_params.yaml |
| ARRIVE_DIST_M | 0.15 | fleet_adapter.py |
| ARRIVE_YAW_RAD | 0.30 | fleet_adapter.py |
| xy_goal_tolerance | 0.06 | nav2_params.yaml |

## 로봇 배치 (절대 혼동 금지)

| 로봇 | 충전소 | 좌표 | zone_id | charger (fleet_config) |
|-------|--------|------|---------|----------------------|
| 54 | P2 | (0.0, -0.899) | 141 | "P2" |
| 18 | P1 | (0.0, -0.606) | 140 | "P1" |

## 변경된 파일 목록

| 파일 | 변경 내용 |
|------|----------|
| `device/.../bt_guiding.py` | **신규** — Nav2GuidingBT 구현 |
| `device/.../main_node.py` | BT4 연결, navigate_cancel 콜백 |
| `device/.../cmd_handler.py` | navigate_cancel 핸들러 추가 |
| `device/.../bt_runner.py` | BT4 Sequence memory=True |
| `device/.../config.py` | CHARGER_ZONE_IDS 54→141, 18→140 |
| `device/.../nav2_params.yaml` | inflation, padding, timeout, collision_monitor |
| `server/.../fleet_adapter.py` | activity tracking, 모드 감지, REST 위치 조회 |
| `server/.../rmf_fleet.launch.py` | use_sim_time argument |
| `server/.../fleet_config.yaml` | 54→P2, 18→P1 |
| `server/.../shop_nav_graph.yaml` | holding point 추가 |
| `server/control_db/seed_data.sql` | zone name 수정 |
| `scripts/rmf_dispatch.py` | 구역 기반 스마트 배정 |
| `scripts/test_nav.sh` | rmf_dispatch_zone 함수 |
