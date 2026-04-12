"""nav_graph.yaml → RViz2 MarkerArray 직접 퍼블리셔.

rmf_visualization navgraph_visualizer 대신 직접 마커를 그린다.
웨이포인트(구, 텍스트) + lane(선)을 /navgraph_markers 토픽으로 발행.

사용법:
    ros2 run shoppinkki_rmf navgraph_marker_publisher
    # RViz2에서 /navgraph_markers (MarkerArray) 추가
"""

import os

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)
import yaml

from visualization_msgs.msg import Marker, MarkerArray
from std_msgs.msg import ColorRGBA
from geometry_msgs.msg import Point

from ament_index_python.packages import get_package_share_directory


class NavGraphMarkerPublisher(Node):

    def __init__(self):
        super().__init__('navgraph_marker_publisher')

        pkg = get_package_share_directory('shoppinkki_rmf')
        default_path = os.path.join(pkg, 'maps', 'shop_nav_graph.yaml')
        self.declare_parameter('nav_graph_file', default_path)
        nav_graph_file = self.get_parameter('nav_graph_file').value

        with open(nav_graph_file) as f:
            data = yaml.safe_load(f)

        qos = QoSProfile(
            depth=1,
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._pub = self.create_publisher(MarkerArray, '/navgraph_markers', qos)

        markers = self._build_markers(data)
        self._pub.publish(markers)
        self.get_logger().info(
            f'Published {len(markers.markers)} markers to /navgraph_markers'
        )

        # 주기적 재발행 (RViz 재접속 대비)
        self.create_timer(5.0, lambda: self._pub.publish(markers))

    def _build_markers(self, data: dict) -> MarkerArray:
        ma = MarkerArray()
        mid = 0

        for level_name, level_data in data.get('levels', {}).items():
            vertices = level_data.get('vertices', [])
            lanes = level_data.get('lanes', [])

            # ── 웨이포인트 구 ──
            for i, v in enumerate(vertices):
                x, y = float(v[0]), float(v[1])
                params = v[2] if len(v) > 2 else {}
                name = params.get('name', f'v{i}')
                is_charger = params.get('is_charger', False)
                is_holding = params.get('is_holding_point', False)
                is_pickup = params.get('pickup_zone', False)

                # 구 마커
                m = Marker()
                m.header.frame_id = 'map'
                m.ns = 'waypoints'
                m.id = mid
                mid += 1
                m.type = Marker.SPHERE
                m.action = Marker.ADD
                m.pose.position.x = x
                m.pose.position.y = y
                m.pose.position.z = 0.02
                m.pose.orientation.w = 1.0
                s = 0.04
                m.scale.x = s
                m.scale.y = s
                m.scale.z = s

                if is_charger:
                    m.color = ColorRGBA(r=0.0, g=1.0, b=0.0, a=1.0)  # 초록
                elif is_holding:
                    m.color = ColorRGBA(r=1.0, g=0.5, b=0.0, a=1.0)  # 주황
                elif is_pickup:
                    m.color = ColorRGBA(r=0.2, g=0.6, b=1.0, a=1.0)  # 파랑
                else:
                    m.color = ColorRGBA(r=0.8, g=0.8, b=0.8, a=1.0)  # 회색

                ma.markers.append(m)

                # 텍스트 라벨
                t = Marker()
                t.header.frame_id = 'map'
                t.ns = 'labels'
                t.id = mid
                mid += 1
                t.type = Marker.TEXT_VIEW_FACING
                t.action = Marker.ADD
                t.pose.position.x = x
                t.pose.position.y = y
                t.pose.position.z = 0.06
                t.pose.orientation.w = 1.0
                t.scale.z = 0.025
                t.color = ColorRGBA(r=1.0, g=1.0, b=1.0, a=1.0)
                t.text = name
                ma.markers.append(t)

            # ── lane 선 ──
            for lane in lanes:
                v1_idx, v2_idx = int(lane[0]), int(lane[1])
                lane_params = lane[2] if len(lane) > 2 else {}
                is_bidir = lane_params.get('is_bidirectional', True)

                v1 = vertices[v1_idx]
                v2 = vertices[v2_idx]

                lm = Marker()
                lm.header.frame_id = 'map'
                lm.ns = 'lanes'
                lm.id = mid
                mid += 1
                lm.type = Marker.LINE_STRIP
                lm.action = Marker.ADD
                lm.scale.x = 0.005  # 선 두께
                lm.pose.orientation.w = 1.0

                p1 = Point(x=float(v1[0]), y=float(v1[1]), z=0.01)
                p2 = Point(x=float(v2[0]), y=float(v2[1]), z=0.01)
                lm.points.append(p1)
                lm.points.append(p2)

                if is_bidir:
                    lm.color = ColorRGBA(r=0.4, g=0.4, b=0.9, a=0.6)  # 파란 반투명
                else:
                    lm.color = ColorRGBA(r=0.9, g=0.4, b=0.4, a=0.6)  # 빨간 반투명

                ma.markers.append(lm)

        return ma


def main():
    rclpy.init()
    node = NavGraphMarkerPublisher()
    rclpy.spin(node)
    rclpy.shutdown()


if __name__ == '__main__':
    main()
