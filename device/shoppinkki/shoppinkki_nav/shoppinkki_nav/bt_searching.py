"""BT 2: SEARCHING  (py_trees 기반)

Rotate in place to re-locate the owner doll.

Behaviour:
    - Spins CCW at ANGULAR_Z_SEARCH rad/s.
    - doll_detector.get_latest() 가 Detection 반환 → SUCCESS
    - SEARCH_TIMEOUT 초과 → FAILURE
    - LiDAR 양쪽 막힘 → FAILURE
"""

from __future__ import annotations

import logging
import time
from typing import Callable, List, Optional

import py_trees

from shoppinkki_interfaces import DollDetectorInterface, RobotPublisherInterface

try:
    from shoppinkki_core.config import ANGULAR_Z_MAX, MIN_DIST, SEARCH_TIMEOUT
except ImportError:
    ANGULAR_Z_MAX = 1.0
    MIN_DIST = 0.25
    SEARCH_TIMEOUT = 30.0

logger = logging.getLogger(__name__)

ANGULAR_Z_SEARCH = 0.5  # rad/s rotation speed during search


class RotateSearch(py_trees.behaviour.Behaviour):
    """제자리 회전으로 인형을 재탐색."""

    def __init__(
        self,
        name: str = 'RotateSearch',
        doll_detector: DollDetectorInterface = None,
        publisher: RobotPublisherInterface = None,
        get_scan: Optional[Callable[[], List[float]]] = None,
    ) -> None:
        super().__init__(name)
        self._detector = doll_detector
        self._pub = publisher
        self._get_scan = get_scan
        self._direction: float = 1.0
        self._start_time: float = 0.0

    def initialise(self) -> None:
        self._direction = 1.0
        self._start_time = time.monotonic()
        logger.info('RotateSearch: started (timeout=%.1fs)', SEARCH_TIMEOUT)

    def update(self) -> py_trees.common.Status:
        elapsed = time.monotonic() - self._start_time

        if elapsed >= SEARCH_TIMEOUT:
            logger.info('RotateSearch: timeout after %.1fs → FAILURE', elapsed)
            self._pub.publish_cmd_vel(0.0, 0.0)
            return py_trees.common.Status.FAILURE

        if self._detector.get_latest() is not None:
            logger.info('RotateSearch: doll re-detected → SUCCESS')
            self._pub.publish_cmd_vel(0.0, 0.0)
            return py_trees.common.Status.SUCCESS

        # Obstacle check
        if self._get_scan is not None:
            blocked = self._is_blocked(self._direction)
            if blocked:
                if self._is_blocked(-self._direction):
                    logger.info('RotateSearch: both directions blocked → FAILURE')
                    self._pub.publish_cmd_vel(0.0, 0.0)
                    return py_trees.common.Status.FAILURE
                self._direction = -self._direction
                logger.info('RotateSearch: switched rotation direction')

        self._pub.publish_cmd_vel(0.0, ANGULAR_Z_SEARCH * self._direction)
        return py_trees.common.Status.RUNNING

    def terminate(self, new_status: py_trees.common.Status) -> None:
        self._pub.publish_cmd_vel(0.0, 0.0)

    def _is_blocked(self, direction: float) -> bool:
        try:
            distances = self._get_scan()
            if not distances:
                return False
            n = len(distances)
            step = n / 360.0
            if direction > 0:
                start_idx = int(45 * step)
                end_idx = int(135 * step)
            else:
                start_idx = int(225 * step)
                end_idx = int(315 * step)
            arc = [distances[i % n] for i in range(start_idx, end_idx)]
            valid = [d for d in arc if d > 0.01]
            return bool(valid) and min(valid) < MIN_DIST
        except Exception as e:
            logger.debug('RotateSearch: scan check error: %s', e)
            return False


def create_searching_tree(
    doll_detector: DollDetectorInterface,
    publisher: RobotPublisherInterface,
    get_scan: Optional[Callable[[], List[float]]] = None,
) -> py_trees.behaviour.Behaviour:
    """BT2 트리를 생성하여 반환."""
    return RotateSearch(
        name='BT2_Searching',
        doll_detector=doll_detector,
        publisher=publisher,
        get_scan=get_scan,
    )
