"""Navigation launch file for ShopPinkki.

Starts:
    - map_server + amcl (localization_launch.xml, namespace=robot_<id>)
    - nav2 full stack (navigation_launch.xml, namespace=robot_<id>)
    - boundary_monitor node

Namespace isolation:
    When ROBOT_ID env var is set, all Nav2 nodes run under robot_<id>/ namespace.
    Action server: /robot_<id>/navigate_to_pose  (same as simulation)

Usage:
    ROBOT_ID=18 ros2 launch shoppinkki_nav navigation.launch.py
    ROBOT_ID=54 ros2 launch shoppinkki_nav navigation.launch.py
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction
from launch.launch_description_sources import AnyLaunchDescriptionSource
from launch.actions import IncludeLaunchDescription
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, PushRosNamespace
from nav2_common.launch import RewrittenYaml


def generate_launch_description():
    pkg_share = get_package_share_directory('shoppinkki_nav')
    pinky_nav_dir = get_package_share_directory('pinky_navigation')

    robot_id = os.environ.get('ROBOT_ID', '')
    namespace = f'robot_{robot_id}' if robot_id else ''
    default_params_raw = (
        os.path.join(pkg_share, 'config', f'nav2_params_robot_{robot_id}.yaml')
        if robot_id else
        os.path.join(pkg_share, 'config', 'nav2_params.yaml')
    )

    # RewrittenYaml wraps params under namespace key so nodes at /robot_<id>/controller_server
    # correctly find their parameters (same mechanism as gz_multi_robot.launch.py)
    nav2_params = RewrittenYaml(
        source_file=default_params_raw,
        root_key=namespace,
        param_rewrites={},
        convert_types=True,
    ) if namespace else default_params_raw

    # ── Launch arguments ──────────────────────
    map_arg = DeclareLaunchArgument(
        'map',
        default_value=os.path.join(pkg_share, 'maps', 'shop.yaml'),
        description='Path to map yaml file',
    )
    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value='false',
        description='Use simulation clock',
    )

    # ── Nav2 localization + navigation under namespace ────────────────────────
    nav2 = GroupAction([
        PushRosNamespace(namespace),
        IncludeLaunchDescription(
            AnyLaunchDescriptionSource(
                os.path.join(pinky_nav_dir, 'launch', 'localization_launch.xml')
            ),
            launch_arguments={
                'namespace': namespace,
                'map': LaunchConfiguration('map'),
                'params_file': nav2_params,
                'use_sim_time': LaunchConfiguration('use_sim_time'),
                'use_composition': 'False',
            }.items(),
        ),
        IncludeLaunchDescription(
            AnyLaunchDescriptionSource(
                os.path.join(pinky_nav_dir, 'launch', 'navigation_launch.xml')
            ),
            launch_arguments={
                'params_file': nav2_params,
                'use_sim_time': LaunchConfiguration('use_sim_time'),
                'use_composition': 'False',
                'lifecycle_nodes': (
                    "['controller_server', 'smoother_server', 'planner_server',"
                    " 'behavior_server', 'bt_navigator',"
                    " 'waypoint_follower', 'velocity_smoother']"
                ),
            }.items(),
        ),
    ])

    # ── BoundaryMonitor node ──────────────────
    boundary_monitor_node = Node(
        package='shoppinkki_nav',
        executable='boundary_monitor',
        name='boundary_monitor',
        namespace=namespace,
        output='screen',
        parameters=[{
            'use_sim_time': LaunchConfiguration('use_sim_time'),
        }],
        additional_env={
            'CONTROL_SERVICE_HOST': os.environ.get('CONTROL_SERVICE_HOST', '127.0.0.1'),
            'CONTROL_SERVICE_PORT': os.environ.get('CONTROL_SERVICE_PORT', '8081'),
        },
    )

    return LaunchDescription([
        map_arg,
        use_sim_time_arg,
        nav2,
        boundary_monitor_node,
    ])
