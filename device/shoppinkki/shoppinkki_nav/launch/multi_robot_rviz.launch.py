"""멀티 로봇 RViz 뷰어 — robot_54 네임스페이스 기준.

Navigation 2 RViz 플러그인이 navigate_to_pose / lifecycle_manager_navigation 을
상대 경로로 조회하므로, RViz 노드를 robot_54 네임스페이스에서 실행해야
Nav2 Goal 버튼이 /robot_54/navigate_to_pose 로 연결된다.
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    robot_ns_arg = DeclareLaunchArgument(
        'robot_ns', default_value='robot_54',
        description='Nav2 Goal을 보낼 로봇 네임스페이스 (robot_54 또는 robot_18)',
    )
    robot_ns = LaunchConfiguration('robot_ns')

    rviz_config = os.path.join(
        get_package_share_directory('shoppinkki_nav'),
        'rviz', 'multi_robot_view.rviz',
    )

    # RViz는 글로벌 네임스페이스에서 실행 (namespace 설정 시 segfault 발생)
    # Nav2 Goal은 RViz 대신 CLI 또는 아래 명령어로 사용:
    #   ros2 action send_goal /robot_54/navigate_to_pose nav2_msgs/action/NavigateToPose ...
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        arguments=['-d', rviz_config],
        parameters=[{'use_sim_time': True}],
        output='screen',
    )

    return LaunchDescription([robot_ns_arg, rviz_node])
