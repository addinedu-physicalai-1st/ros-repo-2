"""BT 3: WAITING  (py_trees 기반)

Stand still. Pedestrian 감지 시 측면 회피.
WAITING_TIMEOUT 초과 시 FAILURE.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Callable, List, Optional, Tuple

import py_trees

from shoppinkki_interfaces import RobotPublisherInterface
from shoppinkki_core.config import MIN_DIST, WAITING_TIMEOUT

AVOIDANCE_STEP = 0.30

logger = logging.getLogger(__name__)


class WaitAndAvoid(py_trees.behaviour.Behaviour):
    """정지 대기 + 보행자 회피."""

    def __init__(
        self,
        name: str = 'WaitAndAvoid',
        publisher: RobotPublisherInterface = None,
        get_scan: Optional[Callable[[], List[float]]] = None,
        send_nav_goal: Optional[Callable[[float, float, float], bool]] = None,
        get_pose: Optional[Callable[[], Tuple[float, float, float]]] = None,
    ) -> None:
        super().__init__(name)
        self._pub = publisher
        self._get_scan = get_scan
        self._send_nav_goal = send_nav_goal
        self._get_pose = get_pose
        self._start_time: float = 0.0
        self._avoiding: bool = False

    def initialise(self) -> None:
        self._start_time = time.monotonic()
        self._avoiding = False
        self._pub.publish_cmd_vel(0.0, 0.0)
        logger.info('WaitAndAvoid: started (timeout=%ds)', WAITING_TIMEOUT)

    def update(self) -> py_trees.common.Status:
        elapsed = time.monotonic() - self._start_time
        if elapsed >= WAITING_TIMEOUT:
            logger.info('WaitAndAvoid: timeout after %.0fs → FAILURE', elapsed)
            return py_trees.common.Status.FAILURE

        if not self._avoiding and self._pedestrian_nearby():
            self._do_lateral_avoidance()

        return py_trees.common.Status.RUNNING

    def terminate(self, new_status: py_trees.common.Status) -> None:
        self._pub.publish_cmd_vel(0.0, 0.0)

    def _pedestrian_nearby(self) -> bool:
        if self._get_scan is None:
            return False
        try:
            distances = self._get_scan()
            if not distances:
                return False
            n = len(distances)
            step = n / 360.0
            front_arc = (
                list(range(0, int(90 * step)))
                + list(range(int(270 * step), n))
            )
            valid = [distances[i] for i in front_arc if distances[i] > 0.01]
            return bool(valid) and min(valid) < MIN_DIST
        except Exception as e:
            logger.debug('WaitAndAvoid: scan error: %s', e)
            return False

    def _do_lateral_avoidance(self) -> None:
        if self._send_nav_goal is None or self._get_pose is None:
            return
        try:
            x, y, theta = self._get_pose()
            dx = math.cos(theta + math.pi / 2) * AVOIDANCE_STEP
            dy = math.sin(theta + math.pi / 2) * AVOIDANCE_STEP
            if self._get_scan is not None:
                distances = self._get_scan()
                n = len(distances)
                step = n / 360.0
                left_min = min(
                    distances[int(60 * step)], distances[int(90 * step)])
                right_min = min(
                    distances[int(270 * step)], distances[int(300 * step)])
                if right_min > left_min:
                    dx, dy = -dx, -dy
            goal_x, goal_y = x + dx, y + dy
            logger.info('WaitAndAvoid: avoidance → (%.2f, %.2f)', goal_x, goal_y)
            self._avoiding = True
            self._send_nav_goal(goal_x, goal_y, theta)
        except Exception as e:
            logger.debug('WaitAndAvoid: avoidance error: %s', e)
        finally:
            self._avoiding = False
            self._pub.publish_cmd_vel(0.0, 0.0)


def create_waiting_tree(
    publisher: RobotPublisherInterface,
    get_scan: Optional[Callable[[], List[float]]] = None,
    send_nav_goal: Optional[Callable[[float, float, float], bool]] = None,
    get_pose: Optional[Callable[[], Tuple[float, float, float]]] = None,
) -> py_trees.behaviour.Behaviour:
    """BT3 트리를 생성하여 반환."""
    return WaitAndAvoid(
        name='BT3_Waiting',
        publisher=publisher,
        get_scan=get_scan,
        send_nav_goal=send_nav_goal,
        get_pose=get_pose,
    )
