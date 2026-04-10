"""RobotPublisherInterface 구현체 — BT에서 /cmd_vel 발행용."""

from __future__ import annotations

from typing import List

from geometry_msgs.msg import Twist
from rclpy.node import Node


class RobotPublisher:
    """ROS 2 토픽을 통해 로봇 명령을 발행하는 구현체.

    BT1(BTTracking), BT2(BTSearching) 등에서 publish_cmd_vel() 호출 시
    geometry_msgs/Twist 를 /robot_{id}/cmd_vel 토픽으로 발행한다.
    """

    def __init__(self, node: Node, robot_id: str) -> None:
        self._node = node
        self._cmd_vel_pub = node.create_publisher(
            Twist, f'/robot_{robot_id}/cmd_vel', 10)

    def publish_cmd_vel(self, linear_x: float, angular_z: float) -> None:
        msg = Twist()
        msg.linear.x = linear_x
        msg.angular.z = angular_z
        self._cmd_vel_pub.publish(msg)

    # ── 아래 메서드들은 BT1/BT2에서 사용하지 않음 (프로토콜 충족용) ──

    def publish_status(self, mode, pos_x, pos_y, battery, is_locked_return):
        pass

    def publish_alarm(self, event):
        pass

    def publish_cart(self, items):
        pass
