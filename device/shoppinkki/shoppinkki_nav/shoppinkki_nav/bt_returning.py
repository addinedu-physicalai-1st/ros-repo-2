"""BT 5: RETURNING  (py_trees 기반)

Sequence:
    1. Keepout Filter 활성화
    2. 주차 슬롯 조회 (REST)
    3. (하단 구역이면) 하단_복도 경유
    4. 충전소까지 직행
    5. Keepout Filter 비활성화
    6. SUCCESS → enter_charging
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import urllib.parse
import urllib.request
from enum import Enum, auto
from typing import Callable, Optional

import py_trees

from shoppinkki_interfaces import RobotPublisherInterface

logger = logging.getLogger(__name__)

# 경유 노드 좌표
EXIT2_NODE: tuple[float, float, float] = (0.0, -1.402, 0.0)       # 출구2
LOWER_CORRIDOR_NODE: tuple[float, float, float] = (0.0, -1.137, 0.0)  # 하단_복도
# 결제구역/출구 근처(좁은 세로 통로)일 때만 출구2 → 하단_복도 경유.
# 같은 y여도 동쪽(x ≥ LOWER_AREA_THRESHOLD_X)에 있으면 복도가 아니라 매장
# 안쪽이므로 그래프 라우팅이 가능.
LOWER_AREA_THRESHOLD_Y: float = -1.2
LOWER_AREA_THRESHOLD_X: float = 0.3

# 하단_복도 → 충전소 graph route (노드간 순차 이동)
ROUTE_LOWER_TO_P1: list[tuple[float, float, float]] = [
    (0.245, -1.137, 0.0),   # 하단_입구
    (0.245, -0.899, 0.0),   # 3열_입구
    (0.245, -0.606, 0.0),   # 2열_입구
    (0.0,   -0.606, 0.0),   # P1
]
ROUTE_LOWER_TO_P2: list[tuple[float, float, float]] = [
    (0.245, -1.137, 0.0),   # 하단_입구
    (0.245, -0.899, 0.0),   # 3열_입구
    (0.0,   -0.899, 0.0),   # P2
]



class _Phase(Enum):
    INIT = auto()
    KEEPOUT_ON = auto()
    GET_SLOT = auto()
    PRE_NAVIGATE = auto()  # 하단_복도까지 (하단 구역일 때만)
    DOCKING = auto()       # 충전소까지 직행
    DONE = auto()
    FAILED = auto()


class ReturnToCharger(py_trees.behaviour.Behaviour):
    """충전소 복귀 — 충전소 직행."""

    def __init__(
        self,
        name: str = 'ReturnToCharger',
        publisher: RobotPublisherInterface = None,
        robot_id: str = '54',
        get_parking_slot: Optional[Callable[[], Optional[dict]]] = None,
        send_nav_goal: Optional[Callable[[float, float, float], bool]] = None,
        set_nav2_mode: Optional[Callable[[str], None]] = None,
        set_keepout_filter: Optional[Callable[[bool], None]] = None,
        set_inflation: Optional[Callable[[bool], None]] = None,
        get_current_pose: Optional[Callable[[], tuple[float, float, float]]] = None,
        on_nav_failed: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(name)
        self._pub = publisher
        self._robot_id = robot_id
        self._get_parking_slot = get_parking_slot
        self._send_nav_goal = send_nav_goal
        self._set_nav2_mode = set_nav2_mode
        self._set_keepout_filter = set_keepout_filter
        self._set_inflation = set_inflation
        self._get_current_pose = get_current_pose
        self._on_nav_failed = on_nav_failed
        self._phase = _Phase.INIT
        self._slot: Optional[dict] = None
        self._pre_nav_thread: Optional[threading.Thread] = None
        self._pre_nav_done: bool = False
        self._pre_nav_success: bool = False
        self._dock_thread: Optional[threading.Thread] = None
        self._dock_done: bool = False
        self._dock_success: bool = False

    def initialise(self) -> None:
        self._phase = _Phase.INIT
        self._slot = None
        self._pre_nav_thread = None
        self._pre_nav_done = False
        self._pre_nav_success = False
        self._dock_thread = None
        self._dock_done = False
        self._dock_success = False
        logger.info('ReturnToCharger: started')

    def update(self) -> py_trees.common.Status:
        if self._phase == _Phase.INIT:
            self._phase = _Phase.KEEPOUT_ON
            return py_trees.common.Status.RUNNING

        if self._phase == _Phase.KEEPOUT_ON:
            logger.info('ReturnToCharger: activating Keepout Filter')
            self._set_keepout(True)
            self._phase = _Phase.GET_SLOT
            return py_trees.common.Status.RUNNING

        if self._phase == _Phase.GET_SLOT:
            return self._tick_get_slot()

        if self._phase == _Phase.PRE_NAVIGATE:
            return self._tick_pre_navigate()

        if self._phase == _Phase.DOCKING:
            return self._tick_docking()

        if self._phase == _Phase.DONE:
            return py_trees.common.Status.SUCCESS

        if self._phase == _Phase.FAILED:
            return py_trees.common.Status.FAILURE

        return py_trees.common.Status.RUNNING

    def terminate(self, new_status: py_trees.common.Status) -> None:
        self._pub.publish_cmd_vel(0.0, 0.0)

    # ── Phase handlers ────────────────────────

    def _tick_get_slot(self) -> py_trees.common.Status:
        if self._get_parking_slot is None:
            logger.warning('ReturnToCharger: no slot provider → default P1')
            self._slot = {'zone_id': 140, 'waypoint_x': 0.0,
                          'waypoint_y': -0.606, 'waypoint_theta': 0.0}
        else:
            try:
                self._slot = self._get_parking_slot()
            except Exception as e:
                logger.error('ReturnToCharger: parking slot error: %s', e)
                self._slot = None

        if self._slot is None:
            logger.warning('ReturnToCharger: no available slot → FAILURE')
            self._set_keepout(False)
            if self._on_nav_failed:
                self._on_nav_failed()
            self._phase = _Phase.FAILED
            return py_trees.common.Status.FAILURE

        logger.info('ReturnToCharger: slot=%s', self._slot.get('zone_id'))
        # 항상 fleet 그래프 경로로 충전소까지 이동 (직선 금지 — 선반 충돌 방지)
        self._phase = _Phase.PRE_NAVIGATE
        return py_trees.common.Status.RUNNING

    def _fetch_fleet_route(
        self, from_x: float, from_y: float, dest_name: str,
    ) -> list[tuple[float, float, float]]:
        """control_service REST로 fleet 경로 질의 → [(x,y,theta), ...]."""
        host = os.environ.get('CONTROL_SERVICE_HOST', '127.0.0.1')
        port = os.environ.get('REST_PORT', '8081')
        qs = urllib.parse.urlencode({
            'from_x': from_x, 'from_y': from_y,
            'dest': dest_name, 'robot_id': self._robot_id,
        })
        url = f'http://{host}:{port}/fleet/route?{qs}'
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            logger.warning('ReturnToCharger: fleet route REST 실패: %s', e)
            return []
        route = data.get('route') or []
        # 중간점 theta = 이동 방향, 최종 theta = 충전소 저장 orientation
        out: list[tuple[float, float, float]] = []
        for i, pt in enumerate(route):
            px = float(pt['x']); py = float(pt['y'])
            if i == len(route) - 1:
                # 마지막 = 충전소. slot에 저장된 theta 사용 (fleet route엔 theta 없음)
                theta = float(self._slot.get('waypoint_theta', 0.0)) if self._slot else 0.0
            else:
                nx, ny = float(route[i + 1]['x']), float(route[i + 1]['y'])
                dx, dy = nx - px, ny - py
                theta = math.atan2(dy, dx) if (abs(dx) > 1e-3 or abs(dy) > 1e-3) else 0.0
            out.append((px, py, round(theta, 4)))
        return out

    def _tick_pre_navigate(self) -> py_trees.common.Status:
        """fleet_router 경로로 충전소까지 순차 이동.

        단, 출구/결제구역 근처(y < LOWER_AREA_THRESHOLD_Y)에서 복귀 시에는
        그래프상 노드가 없는 좁은 통로(출구2 → 하단_복도)를 거쳐야 하므로
        inflation OFF로 고정 경유점을 먼저 통과한 뒤, 하단_복도부터 그래프
        경로로 충전소까지 간다.
        """
        if self._send_nav_goal is None or self._slot is None:
            self._fail()
            return py_trees.common.Status.FAILURE

        if self._pre_nav_thread is None:
            charger_name = 'P2' if self._robot_id == '54' else 'P1'
            cx, cy = 0.0, -0.606
            if self._get_current_pose:
                try:
                    cx, cy, _ = self._get_current_pose()
                except Exception:
                    pass

            in_lower_area = (cy < LOWER_AREA_THRESHOLD_Y
                             and cx < LOWER_AREA_THRESHOLD_X)
            if in_lower_area:
                logger.info(
                    'ReturnToCharger: (%.2f,%.2f) 출구 좁은 통로 → 출구2/하단_복도 경유',
                    cx, cy,
                )
                # 좁은 출구 통로는 inflation OFF + 고정 좌표로 통과
                corridor_pts = [EXIT2_NODE, LOWER_CORRIDOR_NODE]
                fleet_start = (LOWER_CORRIDOR_NODE[0], LOWER_CORRIDOR_NODE[1])
            else:
                corridor_pts = []
                fleet_start = (cx, cy)

            # 하단_복도(혹은 현재 위치)부터 충전소까지 fleet 그래프 경로
            route_pts = self._fetch_fleet_route(fleet_start[0], fleet_start[1],
                                                 charger_name)
            if not route_pts:
                logger.warning('ReturnToCharger: fleet route fetch 실패 → 충전소 직행')
                route_pts = [(
                    float(self._slot.get('waypoint_x', 0.0)),
                    float(self._slot.get('waypoint_y', -0.606)),
                    float(self._slot.get('waypoint_theta', 0.0)),
                )]

            logger.info('ReturnToCharger: corridor=%d + fleet=%d → 충전소',
                        len(corridor_pts), len(route_pts))

            if self._set_nav2_mode:
                self._set_nav2_mode('returning')

            def _run():
                try:
                    # Phase 1: 고정 corridor (좁은 출구 통로) — inflation OFF
                    if corridor_pts:
                        if self._set_inflation:
                            self._set_inflation(False)
                        for i, (gx, gy, gt) in enumerate(corridor_pts):
                            logger.info('ReturnToCharger: corridor [%d/%d] → (%.2f, %.2f)',
                                        i + 1, len(corridor_pts), gx, gy)
                            if not self._send_nav_goal(gx, gy, gt):
                                logger.warning('ReturnToCharger: corridor nav failed')
                                self._pre_nav_success = False
                                return

                    # Phase 2: fleet 그래프 경로 — inflation ON
                    if self._set_inflation:
                        self._set_inflation(True)
                    for i, (gx, gy, gt) in enumerate(route_pts):
                        logger.info('ReturnToCharger: fleet [%d/%d] → (%.2f, %.2f)',
                                    i + 1, len(route_pts), gx, gy)
                        if not self._send_nav_goal(gx, gy, gt):
                            logger.warning('ReturnToCharger: fleet nav failed at [%d]',
                                           i + 1)
                            self._pre_nav_success = False
                            return
                    self._pre_nav_success = True
                except Exception as e:
                    logger.error('ReturnToCharger: sequential nav exception: %s', e)
                    self._pre_nav_success = False
                finally:
                    self._set_keepout(False)
                    self._pre_nav_done = True

            self._pre_nav_thread = threading.Thread(target=_run, daemon=True)
            self._pre_nav_thread.start()
            return py_trees.common.Status.RUNNING

        if not self._pre_nav_done:
            return py_trees.common.Status.RUNNING

        if self._pre_nav_success:
            logger.info('ReturnToCharger: 충전소 도착 → SUCCESS')
            if self._set_nav2_mode:
                self._set_nav2_mode('guiding')
            self._phase = _Phase.DONE
            return py_trees.common.Status.SUCCESS
        else:
            logger.warning('ReturnToCharger: 순차 네비게이션 실패')
            if self._set_nav2_mode:
                self._set_nav2_mode('guiding')
            self._fail()
            return py_trees.common.Status.FAILURE

    def _tick_docking(self) -> py_trees.common.Status:
        """충전소까지 직행 (하단 구역이 아닌 경우)."""
        if self._send_nav_goal is None or self._slot is None:
            self._fail()
            return py_trees.common.Status.FAILURE

        if self._dock_thread is None:
            charger_x = float(self._slot.get('waypoint_x', 0.0))
            charger_y = float(self._slot.get('waypoint_y', 0.0))
            charger_theta = float(self._slot.get('waypoint_theta', 0.0))
            logger.info('ReturnToCharger: 충전소 직행 → (%.2f, %.2f)',
                        charger_x, charger_y)
            if self._set_nav2_mode:
                self._set_nav2_mode('returning')

            def _run():
                try:
                    self._dock_success = self._send_nav_goal(
                        charger_x, charger_y, charger_theta)
                except Exception as e:
                    logger.error('ReturnToCharger: docking exception: %s', e)
                    self._dock_success = False
                finally:
                    self._set_keepout(False)
                    self._dock_done = True

            self._dock_thread = threading.Thread(target=_run, daemon=True)
            self._dock_thread.start()
            return py_trees.common.Status.RUNNING

        if not self._dock_done:
            return py_trees.common.Status.RUNNING

        if self._dock_success:
            logger.info('ReturnToCharger: 충전소 도착 → SUCCESS')
            if self._set_nav2_mode:
                self._set_nav2_mode('guiding')
            self._phase = _Phase.DONE
            return py_trees.common.Status.SUCCESS
        else:
            logger.warning('ReturnToCharger: 도킹 실패')
            if self._set_nav2_mode:
                self._set_nav2_mode('guiding')
            self._fail()
            return py_trees.common.Status.FAILURE

    def _fail(self) -> None:
        self._set_keepout(False)
        if self._on_nav_failed:
            self._on_nav_failed()
        self._phase = _Phase.FAILED

    def _set_keepout(self, enable: bool) -> None:
        if self._set_keepout_filter is not None:
            try:
                self._set_keepout_filter(enable)
            except Exception as e:
                logger.warning('ReturnToCharger: keepout error: %s', e)


def create_returning_tree(
    publisher: RobotPublisherInterface,
    robot_id: str = '54',
    get_parking_slot: Optional[Callable[[], Optional[dict]]] = None,
    send_nav_goal: Optional[Callable[[float, float, float], bool]] = None,
    set_nav2_mode: Optional[Callable[[str], None]] = None,
    set_keepout_filter: Optional[Callable[[bool], None]] = None,
    set_inflation: Optional[Callable[[bool], None]] = None,
    get_current_pose: Optional[Callable[[], tuple[float, float, float]]] = None,
    on_nav_failed: Optional[Callable[[], None]] = None,
) -> py_trees.behaviour.Behaviour:
    """BT5 트리를 생성하여 반환."""
    return ReturnToCharger(
        name='BT5_Returning',
        publisher=publisher,
        robot_id=robot_id,
        get_parking_slot=get_parking_slot,
        send_nav_goal=send_nav_goal,
        set_nav2_mode=set_nav2_mode,
        set_keepout_filter=set_keepout_filter,
        set_inflation=set_inflation,
        get_current_pose=get_current_pose,
        on_nav_failed=on_nav_failed,
    )
