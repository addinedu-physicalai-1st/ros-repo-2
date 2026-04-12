"""BT에서 /cmd_vel 발행 전용 퍼블리셔.

status / alarm / cart 발행은 main_node.py가 직접 처리한다.
이 클래스는 BT1(BTTracking), BT2(BTSearching) 등에서
publish_cmd_vel() 호출 시에만 사용된다.
"""

from __future__ import annotations

from geometry_msgs.msg import Twist
from rclpy.node import Node


class RobotPublisher:
    """geometry_msgs/Twist 를 /robot_{id}/cmd_vel 토픽으로 발행."""

    def __init__(self, node: Node, robot_id: str) -> None:
        self._cmd_vel_pub = node.create_publisher(
            Twist, f'/robot_{robot_id}/cmd_vel', 10)

    def publish_cmd_vel(self, linear_x: float, angular_z: float) -> None:
        msg = Twist()
        msg.linear.x = linear_x
        msg.angular.z = angular_z
        self._cmd_vel_pub.publish(msg)
