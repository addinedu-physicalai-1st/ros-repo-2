"""shop_nav_graph.yaml → /building_map 퍼블리셔.

rmf_visualization navgraph_visualizer 가 /building_map 토픽을 구독하므로,
building_map_server 대신 이 노드가 직접 BuildingMap 메시지를 발행한다.

사용법:
    ros2 run shoppinkki_rmf building_map_publisher
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

from rmf_building_map_msgs.msg import (
    BuildingMap,
    GraphEdge,
    GraphNode,
    Graph,
    Level,
    Param,
)

from ament_index_python.packages import get_package_share_directory


def _make_param(name: str, value) -> Param:
    p = Param()
    p.name = name
    if isinstance(value, bool):
        p.type = Param.TYPE_BOOL
        p.value_bool = value
    elif isinstance(value, int):
        p.type = Param.TYPE_INT
        p.value_int = value
    elif isinstance(value, float):
        p.type = Param.TYPE_DOUBLE
        p.value_float = value
    elif isinstance(value, str):
        p.type = Param.TYPE_STRING
        p.value_string = value
    return p


class BuildingMapPublisher(Node):

    def __init__(self):
        super().__init__('building_map_publisher')

        pkg = get_package_share_directory('shoppinkki_rmf')
        default_path = os.path.join(pkg, 'maps', 'shop_nav_graph.yaml')

        self.declare_parameter('nav_graph_file', default_path)
        nav_graph_file = self.get_parameter('nav_graph_file').value

        self.get_logger().info(f'Loading nav graph: {nav_graph_file}')

        with open(nav_graph_file) as f:
            data = yaml.safe_load(f)

        msg = self._build_msg(data)

        qos = QoSProfile(
            depth=1,
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
        )
        pub = self.create_publisher(BuildingMap, '/building_map', qos)
        pub.publish(msg)
        self.get_logger().info(
            f'Published BuildingMap: {msg.name}, '
            f'level={msg.levels[0].name}, '
            f'vertices={len(msg.levels[0].nav_graphs[0].vertices)}, '
            f'edges={len(msg.levels[0].nav_graphs[0].edges)}'
        )

    def _build_msg(self, data: dict) -> BuildingMap:
        bm = BuildingMap()
        bm.name = data.get('building_name', 'ShopPinkki')

        for level_name, level_data in data.get('levels', {}).items():
            level = Level()
            level.name = level_name
            level.elevation = 0.0

            graph = Graph()
            graph.name = '0'

            for v in level_data.get('vertices', []):
                node = GraphNode()
                node.x = float(v[0])
                node.y = float(v[1])
                params_dict = v[2] if len(v) > 2 else {}
                node.name = params_dict.get('name', '')
                for k, val in params_dict.items():
                    if k == 'name':
                        continue
                    node.params.append(_make_param(k, val))
                graph.vertices.append(node)

            for lane in level_data.get('lanes', []):
                edge = GraphEdge()
                edge.v1_idx = int(lane[0])
                edge.v2_idx = int(lane[1])
                lane_params = lane[2] if len(lane) > 2 else {}
                is_bidir = lane_params.get('is_bidirectional', True)
                edge.edge_type = (
                    GraphEdge.EDGE_TYPE_BIDIRECTIONAL
                    if is_bidir
                    else GraphEdge.EDGE_TYPE_UNIDIRECTIONAL
                )
                for k, val in lane_params.items():
                    if k == 'is_bidirectional':
                        continue
                    edge.params.append(_make_param(k, val))
                graph.edges.append(edge)

            level.nav_graphs.append(graph)
            bm.levels.append(level)

        return bm


def main():
    rclpy.init()
    node = BuildingMapPublisher()
    rclpy.spin(node)
    rclpy.shutdown()


if __name__ == '__main__':
    main()
