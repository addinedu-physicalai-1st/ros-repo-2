"""Namespace-aware bringup node.

pinky_bringup.Pinky 를 상속하여 odom TF / odom 메시지의 frame_id 에
robot namespace prefix 를 적용한다.

기존 pinky_pro 코드를 수정하지 않고, frame_prefix 파라미터 하나만 추가.

Usage:
    ROBOT_ID=54 ros2 run shoppinkki_core ns_bringup --ros-args \
        -p frame_prefix:=robot_54/
"""

from __future__ import annotations

from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from tf_transformations import quaternion_from_euler

from pinky_bringup.bringup import Pinky

import rclpy


class NsPinky(Pinky):
    """Pinky subclass that prepends frame_prefix to odom frame IDs."""

    def __init__(self) -> None:
        super().__init__()

        self.declare_parameter('frame_prefix', '')
        self._fp = self.get_parameter('frame_prefix').get_parameter_value().string_value

        self._odom_frame = self._fp + 'odom'
        self._child_frame = self._fp + 'base_footprint'

        if self._fp:
            self.get_logger().info(
                f'NsPinky: frame_prefix="{self._fp}" '
                f'→ odom="{self._odom_frame}", child="{self._child_frame}"')

    # ── Override: TF broadcast ────────────────────────────────────────────────
    def _publish_tf(self, current_time) -> None:
        t = TransformStamped()
        t.header.stamp = current_time.to_msg()
        t.header.frame_id = self._odom_frame
        t.child_frame_id = self._child_frame
        t.transform.translation.x = self.x
        t.transform.translation.y = self.y
        q = quaternion_from_euler(0, 0, self.theta)
        t.transform.rotation.x = q[0]
        t.transform.rotation.y = q[1]
        t.transform.rotation.z = q[2]
        t.transform.rotation.w = q[3]
        self.tf_broadcaster.sendTransform(t)

    # ── Override: Odometry message ────────────────────────────────────────────
    def _publish_odometry(self, current_time, v_x, vth) -> None:
        msg = Odometry()
        msg.header.stamp = current_time.to_msg()
        msg.header.frame_id = self._odom_frame
        msg.child_frame_id = self._child_frame
        msg.pose.pose.position.x = self.x
        msg.pose.pose.position.y = self.y
        q = quaternion_from_euler(0, 0, self.theta)
        msg.pose.pose.orientation.x = q[0]
        msg.pose.pose.orientation.y = q[1]
        msg.pose.pose.orientation.z = q[2]
        msg.pose.pose.orientation.w = q[3]
        msg.twist.twist.linear.x = v_x
        msg.twist.twist.angular.z = vth
        self.odom_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = NsPinky()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.driver.terminate()
            node.destroy_node()
        rclpy.shutdown()
