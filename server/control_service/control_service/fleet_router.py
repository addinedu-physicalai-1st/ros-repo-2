"""Graph-based routing + lightweight lane reservation.

Replaces Open-RMF traffic_schedule with a minimal in-process coordinator
suitable for a small fleet (2 Pinky robots) in the ShopPinkki mart.

Waypoints & lanes are loaded from the `fleet_waypoint` / `fleet_lane`
tables (seeded from shop_nav_graph.yaml).
"""

from __future__ import annotations

import logging
import math
import threading
from collections import deque
from dataclasses import dataclass
from typing import Optional

from . import db

logger = logging.getLogger(__name__)

# Weight added to an edge that is reserved by another robot.
# Large enough to detour, not infinite so we fall back to the shortest
# path (possibly shared) when no alternative exists.
_RESERVED_EDGE_PENALTY = 1000
# Weight added to an edge whose destination vertex is currently occupied
# by another robot (physical position). Higher than reservation penalty so
# we prefer detouring around stopped/slow robots.
_BLOCKED_VERTEX_PENALTY = 5000


@dataclass
class ConflictInfo:
    """Describes a conflict between the querying robot's planned route
    and another robot's reserved route."""
    partner_id: str
    conflict_entry_idx: int   # index within route_a where conflict starts
    conflict_exit_idx: int    # last vertex index (inclusive) still in conflict
    conflict_type: str        # 'E_SHARE' | 'E_OPPOSE' | 'V_CONVERGE'


class FleetRouter:
    """Thread-safe graph router with per-robot lane reservations.

    Typical flow::

        route = router.plan(robot_id, from_xy=(x, y), dest_name="가전제품1")
        router.reserve(robot_id, route)    # before dispatching to Pi
        ...
        router.release(robot_id)           # when robot arrives / aborts
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # (from_idx, to_idx) -> robot_id
        self._edges: dict[tuple[int, int], str] = {}
        # robot_id -> list of vertex indices along reserved route
        self._routes: dict[str, list[int]] = {}

    # ──────────────────────────────────────────
    # Graph loading
    # ──────────────────────────────────────────

    @staticmethod
    def _load_graph() -> tuple[list[dict], list[dict]]:
        try:
            wps, lanes = db.get_fleet_waypoints(), db.get_fleet_lanes()
            if not wps or not lanes:
                logger.error('Fleet graph is empty (waypoints=%d, lanes=%d) '
                             '— routing will fall back to direct hops',
                             len(wps), len(lanes))
            return wps, lanes
        except Exception:
            logger.exception('Failed to load fleet graph')
            return [], []

    @staticmethod
    def find_nearest_waypoint(x: float, y: float) -> Optional[str]:
        waypoints, _ = FleetRouter._load_graph()
        best, best_d = None, float('inf')
        for w in waypoints:
            d = math.hypot(w['x'] - x, w['y'] - y)
            if d < best_d:
                best_d = d
                best = w['name']
        return best

    # ──────────────────────────────────────────
    # Path planning
    # ──────────────────────────────────────────

    def plan(
        self,
        robot_id: str,
        from_xy: tuple[float, float],
        dest_name: str,
        blocked_vertices: Optional[set[str]] = None,
    ) -> list[dict]:
        """Return a list of ``{x, y}`` waypoints from current pose to dest.

        Edges reserved by *other* robots are heavily penalized so we detour
        when possible; when the only path is blocked we still return it
        (Nav2 will handle local avoidance).

        ``blocked_vertices`` is an optional set of waypoint names that are
        currently occupied by other robots (by live position). Any edge
        whose destination is in that set gets an extra large penalty so we
        route around standing robots instead of trying to pass through them.
        """
        waypoints, lanes = self._load_graph()
        if not waypoints or not lanes:
            return []

        wp_by_idx = {w['idx']: w for w in waypoints}
        wp_by_name = {w['name']: w for w in waypoints}

        dest = wp_by_name.get(dest_name)
        if not dest:
            return []
        dest_idx = dest['idx']

        # Directed adjacency list (lanes table holds unidirectional pairs)
        adj: dict[int, list[int]] = {}
        for lane in lanes:
            adj.setdefault(lane['from_idx'], []).append(lane['to_idx'])

        rx, ry = from_xy
        start_idx = self._closest_idx(waypoints, rx, ry)
        if start_idx is None:
            return []
        if start_idx == dest_idx:
            return [{'x': float(dest['x']), 'y': float(dest['y'])}]

        with self._lock:
            reserved = {e: owner for e, owner in self._edges.items()
                        if owner != robot_id}

        blocked_idx: set[int] = set()
        if blocked_vertices:
            for name in blocked_vertices:
                wp = wp_by_name.get(name)
                if wp is not None and wp['idx'] != dest_idx:
                    # 목적지 자체가 blocked로 들어오면 회피 불가 — 그대로 진행
                    blocked_idx.add(wp['idx'])

        path_idx = self._dijkstra(
            adj, wp_by_idx, start_idx, dest_idx, reserved, blocked_idx)
        if not path_idx:
            # Graph disconnected — fall back to a direct hop
            return [{'x': rx, 'y': ry},
                    {'x': float(dest['x']), 'y': float(dest['y'])}]

        return [{'x': float(wp_by_idx[i]['x']),
                 'y': float(wp_by_idx[i]['y'])} for i in path_idx]

    @staticmethod
    def _closest_idx(waypoints: list[dict], x: float, y: float) -> Optional[int]:
        best, best_d = None, float('inf')
        for w in waypoints:
            d = math.hypot(w['x'] - x, w['y'] - y)
            if d < best_d:
                best_d = d
                best = w['idx']
        return best

    @staticmethod
    def _dijkstra(
        adj: dict[int, list[int]],
        wp_by_idx: dict[int, dict],
        start: int,
        dest: int,
        reserved: dict[tuple[int, int], str],
        blocked_idx: Optional[set[int]] = None,
    ) -> list[int]:
        """Shortest weighted path. Edge cost = euclidean distance +
        penalty when the edge is reserved by another robot or when the
        destination vertex is physically occupied by another robot."""
        import heapq
        blocked_idx = blocked_idx or set()

        dist: dict[int, float] = {start: 0.0}
        prev: dict[int, int] = {}
        pq: list[tuple[float, int]] = [(0.0, start)]

        while pq:
            d, node = heapq.heappop(pq)
            if node == dest:
                break
            if d > dist.get(node, float('inf')):
                continue
            node_wp = wp_by_idx.get(node)
            if not node_wp:
                continue
            for nxt in adj.get(node, []):
                nxt_wp = wp_by_idx.get(nxt)
                if not nxt_wp:
                    continue
                step = math.hypot(nxt_wp['x'] - node_wp['x'],
                                  nxt_wp['y'] - node_wp['y'])
                if (node, nxt) in reserved:
                    step += _RESERVED_EDGE_PENALTY
                if nxt in blocked_idx and nxt != dest:
                    step += _BLOCKED_VERTEX_PENALTY
                nd = d + step
                if nd < dist.get(nxt, float('inf')):
                    dist[nxt] = nd
                    prev[nxt] = node
                    heapq.heappush(pq, (nd, nxt))

        if dest not in dist:
            # Try BFS fallback ignoring reservations
            return FleetRouter._bfs(adj, start, dest)

        # Reconstruct
        path = [dest]
        while path[-1] != start:
            p = prev.get(path[-1])
            if p is None:
                return []
            path.append(p)
        return list(reversed(path))

    @staticmethod
    def _bfs(adj: dict[int, list[int]], start: int, dest: int) -> list[int]:
        q = deque([(start, [start])])
        seen = {start}
        while q:
            n, p = q.popleft()
            if n == dest:
                return p
            for nxt in adj.get(n, []):
                if nxt not in seen:
                    seen.add(nxt)
                    q.append((nxt, p + [nxt]))
        return []

    # ──────────────────────────────────────────
    # Conflict detection
    # ──────────────────────────────────────────

    def detect_conflict(
        self,
        route: list[dict],
        robot_id: str,
    ) -> Optional[ConflictInfo]:
        """``route`` (list of {x,y}) 가 다른 로봇의 예약 경로와 충돌하는지 검사.

        3가지 충돌 유형을 순차 탐지 — 첫 매칭 상대만 반환:
          - E_SHARE   : 같은 directed edge (u,v) 공유
          - E_OPPOSE  : 역방향 edge (u,v) vs (v,u) — 좁은 통로 head-on
          - V_CONVERGE: 서로 다른 edge 로 같은 non-holding intermediate vertex 수렴

        홀딩 포인트(holding_point)로의 수렴은 충돌로 보지 않는다 (대기 가능 지점).
        ``conflict_entry_idx`` 는 route 내 "충돌이 시작되는 vertex 인덱스"
        (loser 가 양보 지점 선택 시 이 인덱스 직전까지 walk-back).
        """
        if not route or len(route) < 2:
            return None

        waypoints, _ = self._load_graph()
        wp_by_idx = {w['idx']: w for w in waypoints}

        route_idx = self._route_to_idx_path(route)
        if len(route_idx) < 2:
            return None

        with self._lock:
            others = {rid: list(path) for rid, path in self._routes.items()
                      if rid != robot_id and len(path) >= 2}

        if not others:
            return None

        for partner_id, partner_path in others.items():
            partner_edges = set(zip(partner_path, partner_path[1:]))
            partner_mids = set(partner_path[1:-1]) if len(partner_path) >= 3 else set()
            for i in range(len(route_idx) - 1):
                u, v = route_idx[i], route_idx[i + 1]
                # E_SHARE
                if (u, v) in partner_edges:
                    exit_i = i + 1
                    while exit_i < len(route_idx) - 1 \
                            and (route_idx[exit_i], route_idx[exit_i + 1]) in partner_edges:
                        exit_i += 1
                    return ConflictInfo(partner_id, i, exit_i, 'E_SHARE')
                # V_CONVERGE: v is intermediate for both, non-holding
                if i < len(route_idx) - 2 and v in partner_mids:
                    wv = wp_by_idx.get(v, {})
                    if not wv.get('holding_point', False):
                        return ConflictInfo(partner_id, i, i + 1, 'V_CONVERGE')
                # E_OPPOSE
                if (v, u) in partner_edges:
                    exit_i = i + 1
                    while exit_i < len(route_idx) - 1 \
                            and (route_idx[exit_i + 1], route_idx[exit_i]) in partner_edges:
                        exit_i += 1
                    return ConflictInfo(partner_id, i, exit_i, 'E_OPPOSE')
        return None

    # ──────────────────────────────────────────
    # Lane reservation
    # ──────────────────────────────────────────

    def reserve(self, robot_id: str, route: list[dict]) -> None:
        """Reserve all edges of ``route`` for ``robot_id``.

        추가로 **최종 목적지 vertex로 들어오는 모든 edge**도 점유로 표시한다.
        (edge 단위 점유만 쓰면 다른 로봇이 "다른 방향에서 같은 vertex로 진입"
         하는 경로를 택할 수 있어서 destination이 실제로 겹친다.)

        Any prior reservations by the same robot are released first.
        ``route`` is a list of ``{x, y}`` dicts (output of :meth:`plan`).
        """
        edges = self._route_to_edges(route)
        # 목적지 vertex로 들어오는 모든 edge
        waypoints, lanes = self._load_graph()
        dest_in_edges: list[tuple[int, int]] = []
        if route and waypoints:
            last = route[-1]
            dest_idx = None
            for w in waypoints:
                if abs(w['x'] - last['x']) < 0.01 and abs(w['y'] - last['y']) < 0.01:
                    dest_idx = w['idx']
                    break
            if dest_idx is not None:
                dest_in_edges = [(lane['from_idx'], lane['to_idx'])
                                 for lane in lanes
                                 if lane['to_idx'] == dest_idx]

        with self._lock:
            self._release_locked(robot_id)
            for e in edges:
                self._edges[e] = robot_id
            for e in dest_in_edges:
                # 이미 누가 잡고 있으면 덮어쓰지 않음 (first-come-first-served)
                self._edges.setdefault(e, robot_id)
            self._routes[robot_id] = self._route_to_idx_path(route)
            total = len(self._edges)
        logger.info(
            'reserve robot=%s route_edges=%d dest_blockers=%d '
            '(route_pts=%d, total_reserved=%d)',
            robot_id, len(edges), len(dest_in_edges), len(route), total)

    def release(self, robot_id: str) -> None:
        with self._lock:
            self._release_locked(robot_id)

    def _release_locked(self, robot_id: str) -> None:
        stale = [e for e, owner in self._edges.items() if owner == robot_id]
        for e in stale:
            del self._edges[e]
        self._routes.pop(robot_id, None)

    @staticmethod
    def _route_to_idx_path(route: list[dict]) -> list[int]:
        """route ({x,y} points) → [vertex_idx, ...] 변환. 매칭 실패 시 스킵."""
        if not route:
            return []
        waypoints, _ = FleetRouter._load_graph()
        if not waypoints:
            return []
        path: list[int] = []
        for pt in route:
            for w in waypoints:
                if abs(w['x'] - pt['x']) < 0.01 and abs(w['y'] - pt['y']) < 0.01:
                    path.append(w['idx'])
                    break
        return path

    @staticmethod
    def _route_to_edges(route: list[dict]) -> list[tuple[int, int]]:
        if not route or len(route) < 2:
            return []
        waypoints, _ = FleetRouter._load_graph()
        if not waypoints:
            return []

        def _idx_at(pt: dict) -> Optional[int]:
            for w in waypoints:
                if abs(w['x'] - pt['x']) < 0.01 and abs(w['y'] - pt['y']) < 0.01:
                    return w['idx']
            return None

        edges: list[tuple[int, int]] = []
        for a, b in zip(route, route[1:]):
            ia, ib = _idx_at(a), _idx_at(b)
            if ia is not None and ib is not None:
                edges.append((ia, ib))
        return edges
