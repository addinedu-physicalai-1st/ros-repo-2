"""ShopPinkki Open-RMF Fleet Adapter.

rmf_adapter Python API (Jazzy) 기반.
두 Pinky 로봇(#54, #18)을 RMF EasyFullControl에 등록하고
경로 충돌을 자동 조정.

실행:
    ros2 run shoppinkki_rmf fleet_adapter \\
        --ros-args -p config_file:=<path>/fleet_config.yaml

의존:
    sudo apt install ros-jazzy-rmf-fleet-adapter ros-jazzy-rmf-fleet-adapter-python
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from typing import Dict, Optional

import numpy as np
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

import rmf_adapter as adpt
import rmf_adapter.easy_full_control as efc
import rmf_adapter.graph as rmf_graph
import rmf_adapter.vehicletraits as traits
import rmf_adapter.geometry as geometry
import rmf_adapter.battery as battery
import requests

logger = logging.getLogger(__name__)


# ── Nav Graph 빌드 ─────────────────────────────────────────────────────────────

def _build_nav_graph(nav_data: dict) -> rmf_graph.Graph:
    """shop_nav_graph.yaml dict → rmf_adapter.graph.Graph 변환."""
    g = rmf_graph.Graph()
    levels = nav_data.get('levels', [])
    if not levels:
        raise ValueError('nav_graph에 level이 없습니다')

    level = levels[0]
    map_name = level['name']

    for v in level.get('vertices', []):
        wp = g.add_waypoint(map_name, [v['x'], v['y']])
        params = v.get('params', {})
        if params.get('is_charger', {}).get('value'):
            wp.set_charger(True)
        if params.get('is_parking_spot', {}).get('value') or \
           params.get('is_holding_point', {}).get('value'):
            wp.set_holding_point(True)
        name = v.get('name', '')
        if name:
            g.add_key(name, wp.index)

    for edge in level.get('edges', []):
        v1, v2 = edge['v1_idx'], edge['v2_idx']
        if edge.get('bidirectional', True):
            g.add_bidir_lane(v1, v2)
        else:
            g.add_lane(v1, v2)

    logger.info('Nav graph 로드: %d 웨이포인트, %d 레인',
                g.num_waypoints, g.num_lanes)
    return g


# ── 단일 로봇 어댑터 ────────────────────────────────────────────────────────────

class RobotAdapter:
    """한 로봇의 상태 추적 + RMF ↔ control_service 명령 중계."""

    ARRIVE_DIST_M = 0.15
    ARRIVE_YAW_RAD = 0.30

    def __init__(self, robot_id: str, ctrl_host: str, ctrl_port: int) -> None:
        self.robot_id = robot_id
        self._rest_base = f'http://{ctrl_host}:{ctrl_port}'

        self._x = 0.0
        self._y = 0.0
        self._yaw = 0.0
        self._battery = 1.0
        self._mode = 'CHARGING'

        self._handle: Optional[adpt.easy_full_control.EasyRobotUpdateHandle] = None
        self._handle_lock = threading.Lock()

        self._nav_cancel = threading.Event()
        self._nav_thread: Optional[threading.Thread] = None

    # ── 상태 수신 ──────────────────────────────────────────────────────────────

    def on_status(self, data: dict) -> None:
        """/robot_<id>/status JSON 수신 시 호출."""
        self._x = float(data.get('pos_x', self._x))
        self._y = float(data.get('pos_y', self._y))
        self._yaw = float(data.get('yaw', self._yaw))
        batt_pct = float(data.get('battery', self._battery * 100))
        self._battery = max(0.0, min(1.0, batt_pct / 100.0))
        self._mode = data.get('mode', self._mode)

        with self._handle_lock:
            if self._handle is not None:
                state = efc.RobotState(
                    map='L1',
                    position=np.array([self._x, self._y, self._yaw]),
                    battery_soc=self._battery,
                )
                try:
                    self._handle.update(state, None)
                except Exception as e:
                    logger.debug('[%s] handle.update 오류: %s', self.robot_id, e)

    def set_handle(self, handle) -> None:
        with self._handle_lock:
            self._handle = handle

    @property
    def position(self):
        return (self._x, self._y, self._yaw)

    # ── RMF 콜백 생성 ──────────────────────────────────────────────────────────

    def make_callbacks(self) -> efc.RobotCallbacks:

        def navigate(dest: efc.Destination, execution: efc.CommandExecution) -> None:
            self._cancel_nav()
            x, y = dest.xy
            yaw = dest.yaw
            zone_idx = dest.graph_index

            logger.info('[%s] navigate → (%.3f, %.3f, yaw=%.2f) idx=%s',
                        self.robot_id, x, y, yaw, zone_idx)

            self._send_cmd({
                'cmd': 'navigate_to',
                'zone_id': int(zone_idx) if zone_idx is not None else 0,
                'x': round(float(x), 4),
                'y': round(float(y), 4),
                'theta': round(float(yaw), 4),
            })

            self._nav_cancel.clear()
            self._nav_thread = threading.Thread(
                target=self._wait_arrive,
                args=(float(x), float(y), float(yaw), execution.finished),
                daemon=True,
            )
            self._nav_thread.start()

        def stop(activity) -> None:
            self._cancel_nav()
            logger.info('[%s] stop → WAITING', self.robot_id)
            self._send_cmd({'cmd': 'mode', 'value': 'WAITING'})

        def action_executor(category: str, desc, execution) -> None:
            logger.info('[%s] action: %s', self.robot_id, category)
            execution.finished()

        return efc.RobotCallbacks(
            navigate=navigate,
            stop=stop,
            action_executor=action_executor,
        )

    # ── 내부 헬퍼 ──────────────────────────────────────────────────────────────

    def _send_cmd(self, payload: dict) -> None:
        url = f'{self._rest_base}/robot/{self.robot_id}/cmd'
        try:
            resp = requests.post(url, json=payload, timeout=3.0)
            if resp.status_code != 200:
                logger.warning('[%s] cmd 응답 %d: %s',
                               self.robot_id, resp.status_code, resp.text[:80])
        except Exception as e:
            logger.error('[%s] cmd 전송 실패: %s', self.robot_id, e)

    def _cancel_nav(self) -> None:
        self._nav_cancel.set()
        if self._nav_thread and self._nav_thread.is_alive():
            self._nav_thread.join(timeout=2.0)

    def _wait_arrive(
        self, gx: float, gy: float, gyaw: float,
        done_cb, timeout_s: float = 120.0
    ) -> None:
        deadline = time.monotonic() + timeout_s
        while not self._nav_cancel.is_set():
            dx = self._x - gx
            dy = self._y - gy
            dist = math.sqrt(dx * dx + dy * dy)
            dyaw = abs(((self._yaw - gyaw + math.pi) % (2 * math.pi)) - math.pi)

            if dist <= self.ARRIVE_DIST_M and dyaw <= self.ARRIVE_YAW_RAD:
                logger.info('[%s] 도착 (dist=%.3f, dyaw=%.3f)',
                            self.robot_id, dist, dyaw)
                done_cb()
                return

            if time.monotonic() >= deadline:
                logger.warning('[%s] navigate timeout', self.robot_id)
                done_cb()
                return

            time.sleep(0.5)


# ── Fleet Adapter ROS 노드 ──────────────────────────────────────────────────────

class PinkyFleetAdapter(Node):
    """두 Pinky 로봇을 RMF에 등록하는 메인 노드."""

    def __init__(self, config: dict, nav_graph: rmf_graph.Graph) -> None:
        super().__init__('pinky_fleet_adapter')

        fleet_cfg = config.get('fleet', {})
        ctrl_cfg = config.get('control_service', {})
        ctrl_host = ctrl_cfg.get('host', '127.0.0.1')
        ctrl_port = int(ctrl_cfg.get('http_port', 8081))

        # 로봇 어댑터 + status 구독
        self._robots: Dict[str, RobotAdapter] = {}
        for r in fleet_cfg.get('robots', []):
            rid = str(r['id'])
            robot = RobotAdapter(rid, ctrl_host, ctrl_port)
            self._robots[rid] = robot
            self.create_subscription(
                String, f'/robot_{rid}/status',
                lambda msg, rid=rid: self._on_status(rid, msg),
                10,
            )

        # RMF Adapter 초기화
        self._easy_fleet = self._init_rmf(fleet_cfg, nav_graph)

        # 로봇 등록
        if self._easy_fleet is not None:
            for r in fleet_cfg.get('robots', []):
                self._register_robot(str(r['id']), r, nav_graph)

        self.get_logger().info(
            'PinkyFleetAdapter 준비: %s', list(self._robots.keys())
        )

    # ── RMF 초기화 ─────────────────────────────────────────────────────────────

    def _init_rmf(self, fleet_cfg: dict, nav_graph: rmf_graph.Graph):
        try:
            fleet_name = fleet_cfg.get('name', 'pinky_fleet')
            limits_cfg = fleet_cfg.get('limits', {})
            profile_cfg = fleet_cfg.get('profile', {})
            lin = limits_cfg.get('linear', {})
            ang = limits_cfg.get('angular', {})

            vehicle_traits = traits.VehicleTraits(
                linear=traits.Limits(
                    lin.get('velocity', 0.3),
                    lin.get('acceleration', 0.5),
                ),
                angular=traits.Limits(
                    ang.get('velocity', 1.0),
                    ang.get('acceleration', 1.5),
                ),
                profile=traits.Profile(
                    geometry.SimpleCircle(profile_cfg.get('footprint', 0.06))
                ),
            )

            bat = battery.BatterySystem.make(10.0, 10.0, 5.0)
            mech = battery.MechanicalSystem.make(12.0, 0.5, 0.5)
            motion_sink = battery.SimpleMotionPowerSink(bat, mech)
            ambient_sink = battery.SimpleDevicePowerSink(
                bat, battery.PowerSystem.make(20.0))
            tool_sink = battery.SimpleDevicePowerSink(
                bat, battery.PowerSystem.make(10.0))

            known_configs = {
                f'pinky_{r["id"]}': efc.RobotConfiguration(
                    compatible_chargers=[r.get('initial_waypoint', 'P1')]
                )
                for r in fleet_cfg.get('robots', [])
            }

            fleet_config = efc.FleetConfiguration(
                fleet_name=fleet_name,
                transformations_to_robot_coordinates=None,
                known_robot_configurations=known_configs,
                traits=vehicle_traits,
                graph=nav_graph,
                battery_system=bat,
                motion_sink=motion_sink,
                ambient_sink=ambient_sink,
                tool_sink=tool_sink,
                recharge_threshold=0.05,
                recharge_soc=1.0,
                account_for_battery_drain=False,
                task_categories={},
                action_categories={},
                finishing_request='charge',
                skip_rotation_commands=True,
                server_uri=None,
            )

            adpt.init_rclcpp()
            adapter = adpt.Adapter.make(fleet_name)
            if adapter is None:
                self.get_logger().error('adpt.Adapter.make 실패')
                return None

            easy_fleet = adapter.add_easy_fleet(fleet_config)
            adapter.start()
            self.get_logger().info('RMF Adapter 시작: %s', fleet_name)
            return easy_fleet

        except Exception as e:
            self.get_logger().error('RMF 초기화 실패: %s', e, exc_info=True)
            return None

    # ── 로봇 등록 ───────────────────────────────────────────────────────────────

    def _register_robot(
        self, robot_id: str, robot_cfg: dict, nav_graph: rmf_graph.Graph
    ) -> None:
        robot = self._robots[robot_id]
        wp_name = robot_cfg.get('initial_waypoint', 'P1')

        wp = nav_graph.find_waypoint(wp_name)
        if wp is None:
            self.get_logger().error('웨이포인트 없음: %s', wp_name)
            return

        loc = wp.location
        yaw = float(robot_cfg.get('initial_orientation', 0.0))

        state = efc.RobotState(
            map='L1',
            position=np.array([loc[0], loc[1], yaw]),
            battery_soc=1.0,
        )
        robot_config = efc.RobotConfiguration(
            compatible_chargers=[wp_name]
        )
        callbacks = robot.make_callbacks()

        handle = self._easy_fleet.add_robot(
            f'pinky_{robot_id}', state, robot_config, callbacks
        )
        robot.set_handle(handle)

        self.get_logger().info(
            '로봇 등록: pinky_%s @ %s (%.3f, %.3f)',
            robot_id, wp_name, loc[0], loc[1],
        )

    # ── ROS 콜백 ────────────────────────────────────────────────────────────────

    def _on_status(self, robot_id: str, msg: String) -> None:
        try:
            data = json.loads(msg.data)
            self._robots[robot_id].on_status(data)
        except Exception as e:
            self.get_logger().warning('status 파싱 오류: %s', e)


# ── 진입점 ─────────────────────────────────────────────────────────────────────

def main(args=None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    )

    rclpy.init(args=args)

    # config_file 파라미터
    tmp = rclpy.create_node('_rmf_param_reader')
    tmp.declare_parameter('config_file', '')
    config_file = tmp.get_parameter('config_file').get_parameter_value().string_value
    tmp.destroy_node()

    if not config_file:
        try:
            from ament_index_python.packages import get_package_share_directory
            pkg = get_package_share_directory('shoppinkki_rmf')
        except Exception:
            pkg = os.path.join(os.path.dirname(__file__), '..', '..')
        config_file = os.path.join(pkg, 'config', 'fleet_config.yaml')

    # config 로드
    import yaml
    try:
        with open(config_file) as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logger.error('config 로드 실패: %s', e)
        rclpy.shutdown()
        return

    # nav graph 로드
    graph_rel = config.get('fleet', {}).get('nav_graph', 'shop_nav_graph.yaml')
    try:
        from ament_index_python.packages import get_package_share_directory
        pkg = get_package_share_directory('shoppinkki_rmf')
    except Exception:
        pkg = os.path.join(os.path.dirname(__file__), '..', '..')
    graph_path = os.path.join(pkg, 'maps', graph_rel)

    try:
        with open(graph_path) as f:
            nav_data = yaml.safe_load(f)
        nav_graph = _build_nav_graph(nav_data)
    except Exception as e:
        logger.error('nav graph 로드 실패: %s', e)
        rclpy.shutdown()
        return

    node = PinkyFleetAdapter(config, nav_graph)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
