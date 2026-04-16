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

import logging
import math
import threading
from enum import Enum, auto
from typing import Callable, Optional

import py_trees

from shoppinkki_interfaces import RobotPublisherInterface

logger = logging.getLogger(__name__)

# 경유 노드 좌표
EXIT2_NODE: tuple[float, float, float] = (0.0, -1.402, 0.0)       # 출구2
LOWER_CORRIDOR_NODE: tuple[float, float, float] = (0.0, -1.137, 0.0)  # 하단_복도
# 이 y좌표 이하면 결제구역/출구 근처 → 출구2 → 하단_복도 경유
LOWER_AREA_THRESHOLD_Y: float = -1.2

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
        # 결제구역/출구 근처(y < threshold)일 때만 하단_복도 경유
        if self._get_current_pose:
            _, cy, _ = self._get_current_pose()
            if cy < LOWER_AREA_THRESHOLD_Y:
                logger.info('ReturnToCharger: y=%.2f < %.2f → 하단_복도 경유',
                            cy, LOWER_AREA_THRESHOLD_Y)
                self._phase = _Phase.PRE_NAVIGATE
                return py_trees.common.Status.RUNNING
        logger.info('ReturnToCharger: 하단_복도 스킵 → 충전소 직행')
        self._phase = _Phase.DOCKING
        return py_trees.common.Status.RUNNING

    def _tick_pre_navigate(self) -> py_trees.common.Status:
        """출구2 → 하단_복도 (inflation OFF) → graph route → 충전소 순차 이동."""
        if self._send_nav_goal is None or self._slot is None:
            self._fail()
            return py_trees.common.Status.FAILURE

        if self._pre_nav_thread is None:
            charger_y = float(self._slot.get('waypoint_y', -0.606))
            # 충전소에 따라 하단_복도 이후 경로 선택
            if charger_y < -0.75:
                route_after = ROUTE_LOWER_TO_P2
            else:
                route_after = ROUTE_LOWER_TO_P1

            # 전체 경로: 출구2 → 하단_복도 (inflation OFF) + 이후 경로 (inflation ON) + 충전소
            corridor_pts = [EXIT2_NODE, LOWER_CORRIDOR_NODE]
            charger_pt = (
                float(self._slot.get('waypoint_x', 0.0)),
                float(self._slot.get('waypoint_y', -0.606)),
                float(self._slot.get('waypoint_theta', 0.0)),
            )
            # route_after 마지막이 충전소이므로 charger_pt는 별도 추가 불필요
            after_pts = list(route_after)

            logger.info('ReturnToCharger: 출구2 → 하단_복도 → %d pts → 충전소',
                        len(after_pts))

            if self._set_nav2_mode:
                self._set_nav2_mode('returning')
            if self._set_inflation:
                self._set_inflation(False)

            def _run():
                try:
                    # Phase 1: 출구2 → 하단_복도 (inflation OFF)
                    for i, (gx, gy, gt) in enumerate(corridor_pts):
                        logger.info('ReturnToCharger: corridor [%d/%d] → (%.2f, %.2f)',
                                    i + 1, len(corridor_pts), gx, gy)
                        if not self._send_nav_goal(gx, gy, gt):
                            logger.warning('ReturnToCharger: corridor nav failed')
                            self._pre_nav_success = False
                            return

                    # Phase 2: inflation ON → graph route to charger
                    if self._set_inflation:
                        self._set_inflation(True)
                    logger.info('ReturnToCharger: inflation ON → graph route %d pts',
                                len(after_pts))

                    for i, (gx, gy, gt) in enumerate(after_pts):
                        # 마지막 waypoint (충전소)는 returning 모드로
                        if i == len(after_pts) - 1:
                            if self._set_nav2_mode:
                                self._set_nav2_mode('returning')
                        logger.info('ReturnToCharger: route [%d/%d] → (%.2f, %.2f)',
                                    i + 1, len(after_pts), gx, gy)
                        if not self._send_nav_goal(gx, gy, gt):
                            logger.warning('ReturnToCharger: route nav failed at [%d]',
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
