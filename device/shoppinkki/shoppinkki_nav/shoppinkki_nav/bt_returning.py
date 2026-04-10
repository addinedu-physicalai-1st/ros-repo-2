"""BT 5: RETURNING  (py_trees 기반)

Sequence:
    1. Keepout Filter 활성화
    2. 주차 슬롯 조회 (REST)
    3. Nav2 로 이동
    4. Keepout Filter 비활성화
    5. SUCCESS → enter_charging
"""

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Callable, Optional

import py_trees

from shoppinkki_interfaces import RobotPublisherInterface

logger = logging.getLogger(__name__)


class _Phase(Enum):
    INIT = auto()
    KEEPOUT_ON = auto()
    GET_SLOT = auto()
    NAVIGATING = auto()
    DONE = auto()
    FAILED = auto()


class ReturnToCharger(py_trees.behaviour.Behaviour):
    """충전소 복귀 — 내부 phase 기반 시퀀스."""

    def __init__(
        self,
        name: str = 'ReturnToCharger',
        publisher: RobotPublisherInterface = None,
        get_parking_slot: Optional[Callable[[], Optional[dict]]] = None,
        send_nav_goal: Optional[Callable[[float, float, float], bool]] = None,
        set_keepout_filter: Optional[Callable[[bool], None]] = None,
        on_nav_failed: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(name)
        self._pub = publisher
        self._get_parking_slot = get_parking_slot
        self._send_nav_goal = send_nav_goal
        self._set_keepout_filter = set_keepout_filter
        self._on_nav_failed = on_nav_failed
        self._phase = _Phase.INIT
        self._slot: Optional[dict] = None

    def initialise(self) -> None:
        self._phase = _Phase.INIT
        self._slot = None
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

        if self._phase == _Phase.NAVIGATING:
            return self._tick_navigate()

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
                          'waypoint_y': 0.0, 'waypoint_theta': 1.5708}
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
        self._phase = _Phase.NAVIGATING
        return py_trees.common.Status.RUNNING

    def _tick_navigate(self) -> py_trees.common.Status:
        if self._send_nav_goal is None or self._slot is None:
            logger.warning('ReturnToCharger: no nav client → FAILURE')
            self._set_keepout(False)
            if self._on_nav_failed:
                self._on_nav_failed()
            self._phase = _Phase.FAILED
            return py_trees.common.Status.FAILURE

        x = float(self._slot.get('waypoint_x', 0.0))
        y = float(self._slot.get('waypoint_y', 0.0))
        theta = float(self._slot.get('waypoint_theta', 1.5708))

        logger.info('ReturnToCharger: navigating to (%.2f, %.2f, θ=%.2f)',
                    x, y, theta)
        try:
            success = self._send_nav_goal(x, y, theta)
        except Exception as e:
            logger.error('ReturnToCharger: nav exception: %s', e)
            success = False

        self._set_keepout(False)

        if success:
            logger.info('ReturnToCharger: arrived at charger → SUCCESS')
            self._phase = _Phase.DONE
            return py_trees.common.Status.SUCCESS
        else:
            logger.warning('ReturnToCharger: nav failed → FAILURE')
            if self._on_nav_failed:
                self._on_nav_failed()
            self._phase = _Phase.FAILED
            return py_trees.common.Status.FAILURE

    def _set_keepout(self, enable: bool) -> None:
        if self._set_keepout_filter is not None:
            try:
                self._set_keepout_filter(enable)
            except Exception as e:
                logger.warning('ReturnToCharger: keepout error: %s', e)


def create_returning_tree(
    publisher: RobotPublisherInterface,
    get_parking_slot: Optional[Callable[[], Optional[dict]]] = None,
    send_nav_goal: Optional[Callable[[float, float, float], bool]] = None,
    set_keepout_filter: Optional[Callable[[bool], None]] = None,
    on_nav_failed: Optional[Callable[[], None]] = None,
) -> py_trees.behaviour.Behaviour:
    """BT5 트리를 생성하여 반환."""
    return ReturnToCharger(
        name='BT5_Returning',
        publisher=publisher,
        get_parking_slot=get_parking_slot,
        send_nav_goal=send_nav_goal,
        set_keepout_filter=set_keepout_filter,
        on_nav_failed=on_nav_failed,
    )
