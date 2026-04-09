"""Launch 유틸리티 — nav2_params.yaml 템플릿 치환.

nav2_params.yaml 의 플레이스홀더를 로봇별 값으로 치환하여
임시 파일 경로를 반환한다.

AMCL 초기 pose 는 control_service REST /zones 에서 가져온다.
서버 미기동 시 (0, 0, 0) fallback — admin_ui "위치 초기화"로 교정.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import urllib.request

from shoppinkki_core.config import CHARGER_ZONE_IDS

logger = logging.getLogger(__name__)

_DEFAULT_POSE = {'x': 0.0, 'y': 0.0, 'yaw': 0.0}


def _fetch_charger_pose(
    robot_id: str,
    host: str = '127.0.0.1',
    port: int = 8081,
) -> dict[str, float]:
    """REST /zones 에서 충전소 waypoint → {'x', 'y', 'yaw'} 반환."""
    zone_id = CHARGER_ZONE_IDS.get(robot_id)
    if zone_id is None:
        return _DEFAULT_POSE

    url = f'http://{host}:{port}/zones'
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            zones = json.loads(resp.read())
        for z in zones:
            if z['zone_id'] == zone_id:
                return {
                    'x': float(z['x']),
                    'y': float(z['y']),
                    'yaw': float(z['theta']),
                }
    except Exception as exc:
        logger.warning('launch_utils: charger pose fetch failed: %s', exc)

    return _DEFAULT_POSE


def resolve_nav2_params(
    template_path: str,
    ns: str,
    robot_id: str | None = None,
) -> str:
    """nav2_params.yaml 템플릿의 플레이스홀더를 치환하고 임시 파일 경로를 반환.

    Parameters
    ----------
    template_path:
        __NS__ 등 플레이스홀더가 포함된 YAML 경로.
    ns:
        로봇 namespace (e.g. ``robot_54``).
    robot_id:
        로봇 번호 (e.g. ``54``). None 이면 ns 에서 추출.
    """
    if robot_id is None:
        robot_id = ns.replace('robot_', '')

    host = os.environ.get('CONTROL_SERVICE_HOST', '127.0.0.1')
    port = int(os.environ.get('CONTROL_SERVICE_PORT', '8081'))
    pose = _fetch_charger_pose(robot_id, host, port)

    with open(template_path) as f:
        content = f.read()

    content = (
        content
        .replace('__NS__', ns)
        .replace('__INIT_X__', str(pose['x']))
        .replace('__INIT_Y__', str(pose['y']))
        .replace('__INIT_YAW__', str(pose['yaw']))
    )

    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.yaml', prefix=f'nav2_{ns}_', delete=False,
    )
    tmp.write(content)
    tmp.close()
    return tmp.name
