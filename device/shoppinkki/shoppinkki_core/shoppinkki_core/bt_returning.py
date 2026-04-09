"""BT5 — RETURNING: Nav2로 충전소까지 자율 주행."""

from __future__ import annotations

import math
from typing import Optional

from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node

from shoppinkki_interfaces import BTStatus


class Nav2ReturningBT:
    """NavBTInterface implementation — sends Nav2 goal to charger on start()."""

    def __init__(self, node: Node, action_client: ActionClient,
                 charger_x: float, charger_y: float, charger_yaw: float) -> None:
        self._node = node
        self._client = action_client
        self._cx = charger_x
        self._cy = charger_y
        self._cyaw = charger_yaw
        self._goal_handle = None
        self._result_future = None
        self._done: Optional[bool] = None  # None=running, True=success, False=fail

    def start(self) -> None:
        self._done = None
        self._goal_handle = None
        self._result_future = None

        if not self._client.server_is_ready():
            self._node.get_logger().warning('BT5: Nav2 action server not ready')
            self._done = False
            return

        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = 'map'
        goal.pose.header.stamp = self._node.get_clock().now().to_msg()
        goal.pose.pose.position.x = self._cx
        goal.pose.pose.position.y = self._cy
        goal.pose.pose.orientation.z = math.sin(self._cyaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(self._cyaw / 2.0)

        future = self._client.send_goal_async(goal)
        future.add_done_callback(self._goal_response_cb)
        self._node.get_logger().info(
            'BT5: RETURNING goal sent → (%.2f, %.2f)' % (self._cx, self._cy))

    def stop(self) -> None:
        if self._goal_handle is not None:
            self._goal_handle.cancel_goal_async()
            self._node.get_logger().info('BT5: RETURNING goal cancelled')
        self._goal_handle = None
        self._result_future = None
        self._done = None

    def tick(self) -> BTStatus:
        if self._done is True:
            return BTStatus.SUCCESS
        if self._done is False:
            return BTStatus.FAILURE
        return BTStatus.RUNNING

    def _goal_response_cb(self, future) -> None:
        goal_handle = future.result()
        if not goal_handle.accepted:
            self._node.get_logger().warning('BT5: Nav2 goal rejected')
            self._done = False
            return
        self._goal_handle = goal_handle
        self._result_future = goal_handle.get_result_async()
        self._result_future.add_done_callback(self._result_cb)

    def _result_cb(self, future) -> None:
        result = future.result()
        status = result.status
        if status == GoalStatus.STATUS_SUCCEEDED:
            self._node.get_logger().info('BT5: arrived at charger')
            self._done = True
        else:
            self._node.get_logger().warning('BT5: Nav2 failed (status=%d)' % status)
            self._done = False
