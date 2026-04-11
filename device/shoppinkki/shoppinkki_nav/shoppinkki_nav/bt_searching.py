"""BT 2: SEARCHING  (py_trees 기반)

Rotate in place to re-locate the owner doll.

트리 구조:
    BT2_Searching (Selector, memory=False)
    ├─ CheckRedetected         ← get_latest() != None → SUCCESS (인형 재발견!)
    ├─ CheckTimeout            ← SEARCH_TIMEOUT 초과 → FAILURE
    └─ RotateInPlace (Sequence, memory=False)
       ├─ CheckDirection       ← LiDAR 장애물 → 방향 전환, 양쪽 막힘 → FAILURE
       └─ Rotate               ← cmd_vel 회전 발행 → RUNNING
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


# ── Shared state ─────────────────────────────────────────────

class _SearchCtx:
    """BT2 내부 Behaviour 간 공유 컨텍스트."""

    def __init__(self, detector, publisher, get_scan):
        self.detector = detector
        self.publisher = publisher
        self.get_scan = get_scan
        self.direction: float = 1.0   # +1=CCW, -1=CW
        self.start_time: float = 0.0


# ── Leaf Behaviours ──────────────────────────────────────────

class CheckRedetected(py_trees.behaviour.Behaviour):
    """인형 재발견 확인.

    감지됨 → SUCCESS (BTRunner 가 TRACKING 복귀)
    미감지 → FAILURE (다음 자식으로)
    """

    def __init__(self, name: str, ctx: _SearchCtx) -> None:
        super().__init__(name)
        self._ctx = ctx

    def update(self) -> py_trees.common.Status:
        if self._ctx.detector.get_latest() is not None:
            logger.info('CheckRedetected: doll re-detected → SUCCESS')
            self._ctx.publisher.publish_cmd_vel(0.0, 0.0)
            return py_trees.common.Status.SUCCESS
        return py_trees.common.Status.FAILURE


class CheckTimeout(py_trees.behaviour.Behaviour):
    """탐색 타임아웃 확인.

    SEARCH_TIMEOUT 초과 → FAILURE (BTRunner 가 WAITING 전환)
    아직 시간 남음 → FAILURE (다음 자식으로)
    """

    def __init__(self, name: str, ctx: _SearchCtx) -> None:
        super().__init__(name)
        self._ctx = ctx

    def initialise(self) -> None:
        if self._ctx.start_time == 0.0:
            self._ctx.start_time = time.monotonic()

    def update(self) -> py_trees.common.Status:
        elapsed = time.monotonic() - self._ctx.start_time
        if elapsed >= SEARCH_TIMEOUT:
            logger.info('CheckTimeout: timeout after %.1fs → FAILURE', elapsed)
            self._ctx.publisher.publish_cmd_vel(0.0, 0.0)
            # Selector 에서 FAILURE → 전체 BT2 FAILURE
            return py_trees.common.Status.FAILURE
        return py_trees.common.Status.FAILURE  # 시간 남음 → 다음 자식으로


class CheckDirection(py_trees.behaviour.Behaviour):
    """LiDAR 장애물 확인 + 회전 방향 결정.

    현재 방향 막힘 → 반대로 전환
    양쪽 다 막힘 → FAILURE
    통과 → SUCCESS (Rotate 실행)
    """

    def __init__(self, name: str, ctx: _SearchCtx) -> None:
        super().__init__(name)
        self._ctx = ctx

    def update(self) -> py_trees.common.Status:
        if self._ctx.get_scan is None:
            return py_trees.common.Status.SUCCESS

        if self._is_blocked(self._ctx.direction):
            if self._is_blocked(-self._ctx.direction):
                logger.info('CheckDirection: both directions blocked → FAILURE')
                self._ctx.publisher.publish_cmd_vel(0.0, 0.0)
                return py_trees.common.Status.FAILURE
            self._ctx.direction = -self._ctx.direction
            logger.info('CheckDirection: switched to %s',
                        'CCW' if self._ctx.direction > 0 else 'CW')

        return py_trees.common.Status.SUCCESS

    def _is_blocked(self, direction: float) -> bool:
        try:
            distances = self._ctx.get_scan()
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
            logger.debug('CheckDirection: scan error: %s', e)
            return False


class Rotate(py_trees.behaviour.Behaviour):
    """제자리 회전 cmd_vel 발행.

    항상 RUNNING 반환 (탐색 지속).
    """

    def __init__(self, name: str, ctx: _SearchCtx) -> None:
        super().__init__(name)
        self._ctx = ctx

    def update(self) -> py_trees.common.Status:
        self._ctx.publisher.publish_cmd_vel(
            0.0, ANGULAR_Z_SEARCH * self._ctx.direction)
        return py_trees.common.Status.RUNNING

    def terminate(self, new_status: py_trees.common.Status) -> None:
        self._ctx.publisher.publish_cmd_vel(0.0, 0.0)


# ── Tree factory ─────────────────────────────────────────────

def create_searching_tree(
    doll_detector: DollDetectorInterface,
    publisher: RobotPublisherInterface,
    get_scan: Optional[Callable[[], List[float]]] = None,
) -> py_trees.behaviour.Behaviour:
    """BT2 트리를 생성하여 반환.

    BT2_Searching (Selector, memory=False)
    ├─ CheckRedetected
    ├─ CheckTimeout
    └─ RotateInPlace (Sequence, memory=False)
       ├─ CheckDirection
       └─ Rotate
    """
    ctx = _SearchCtx(doll_detector, publisher, get_scan)

    rotate_seq = py_trees.composites.Sequence(
        name='RotateInPlace', memory=False)
    rotate_seq.add_children([
        CheckDirection('CheckDirection', ctx),
        Rotate('Rotate', ctx),
    ])

    root = py_trees.composites.Selector(name='BT2_Searching', memory=False)
    root.add_children([
        CheckRedetected('CheckRedetected', ctx),
        CheckTimeout('CheckTimeout', ctx),
        rotate_seq,
    ])

    return root
