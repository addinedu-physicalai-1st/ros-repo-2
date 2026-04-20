"""Unit tests for FleetRouter — DB stubbed with an in-memory graph."""

from unittest.mock import patch

import pytest

from control_service.fleet_router import FleetRouter


# Small fixture graph:
#
#   0 ── 1 ── 2
#   │         │
#   3 ──── 4
#
# All lanes bidirectional (seeded as pairs of one-way lanes, like the real
# fleet_lane table).
_WAYPOINTS = [
    {'idx': 0, 'name': 'A', 'x': 0.0, 'y': 0.0, 'theta': 0.0, 'holding_point': True},
    {'idx': 1, 'name': 'B', 'x': 1.0, 'y': 0.0, 'theta': 0.0, 'holding_point': False},
    {'idx': 2, 'name': 'C', 'x': 2.0, 'y': 0.0, 'theta': 0.0, 'holding_point': True},
    {'idx': 3, 'name': 'D', 'x': 0.0, 'y': 1.0, 'theta': 0.0, 'holding_point': False},
    {'idx': 4, 'name': 'E', 'x': 2.0, 'y': 1.0, 'theta': 0.0, 'holding_point': False},
]
_LANES = [
    {'from_idx': 0, 'to_idx': 1}, {'from_idx': 1, 'to_idx': 0},
    {'from_idx': 1, 'to_idx': 2}, {'from_idx': 2, 'to_idx': 1},
    {'from_idx': 0, 'to_idx': 3}, {'from_idx': 3, 'to_idx': 0},
    {'from_idx': 2, 'to_idx': 4}, {'from_idx': 4, 'to_idx': 2},
    {'from_idx': 3, 'to_idx': 4}, {'from_idx': 4, 'to_idx': 3},
]


@pytest.fixture
def router():
    with patch('control_service.fleet_router.db') as mock_db:
        mock_db.get_fleet_waypoints.return_value = _WAYPOINTS
        mock_db.get_fleet_lanes.return_value = _LANES
        yield FleetRouter()


def _names(route: list[dict]) -> list[str]:
    out = []
    for pt in route:
        for wp in _WAYPOINTS:
            if abs(wp['x'] - pt['x']) < 1e-6 and abs(wp['y'] - pt['y']) < 1e-6:
                out.append(wp['name'])
                break
    return out


class TestPlan:
    def test_direct_route(self, router):
        route = router.plan('r1', (0.0, 0.0), 'C')
        assert _names(route) == ['A', 'B', 'C']

    def test_start_equals_dest(self, router):
        route = router.plan('r1', (0.0, 0.0), 'A')
        assert len(route) == 1
        assert _names(route) == ['A']

    def test_unknown_dest(self, router):
        assert router.plan('r1', (0.0, 0.0), 'ZZZ') == []

    def test_starts_from_closest_vertex(self, router):
        # (1.4, 0.0) → closest is B; shortest to C is B→C
        route = router.plan('r1', (1.4, 0.0), 'C')
        assert _names(route) == ['B', 'C']


class TestReservation:
    def test_detour_when_edge_reserved_by_other(self, router):
        # r2 reserves A→B→C, so r1 should detour via A→D→E→C
        r2_route = router.plan('r2', (0.0, 0.0), 'C')
        router.reserve('r2', r2_route)

        r1_route = router.plan('r1', (0.0, 0.0), 'C')
        assert _names(r1_route) == ['A', 'D', 'E', 'C']

    def test_release_clears_reservation(self, router):
        r2_route = router.plan('r2', (0.0, 0.0), 'C')
        router.reserve('r2', r2_route)
        router.release('r2')

        r1_route = router.plan('r1', (0.0, 0.0), 'C')
        assert _names(r1_route) == ['A', 'B', 'C']

    def test_reserve_replaces_prior_reservation(self, router):
        router.reserve('r1', router.plan('r1', (0.0, 0.0), 'C'))
        # Now r1 picks a different route — old reservation must go
        router.reserve('r1', router.plan('r1', (0.0, 0.0), 'D'))

        # r2 should be free to take A→B→C without detour
        r2_route = router.plan('r2', (0.0, 0.0), 'C')
        assert _names(r2_route) == ['A', 'B', 'C']

    def test_own_reservation_does_not_block_self(self, router):
        r1_route = router.plan('r1', (0.0, 0.0), 'C')
        router.reserve('r1', r1_route)
        # Planning again for the same robot should not detour.
        again = router.plan('r1', (0.0, 0.0), 'C')
        assert _names(again) == ['A', 'B', 'C']


class TestNearest:
    def test_find_nearest_waypoint(self, router):
        with patch('control_service.fleet_router.db') as mock_db:
            mock_db.get_fleet_waypoints.return_value = _WAYPOINTS
            mock_db.get_fleet_lanes.return_value = _LANES
            assert FleetRouter.find_nearest_waypoint(1.9, 0.1) == 'C'
            assert FleetRouter.find_nearest_waypoint(-0.2, 1.1) == 'D'


class TestRoutesStorage:
    def test_reserve_populates_routes(self, router):
        r1_route = router.plan('r1', (0.0, 0.0), 'C')
        router.reserve('r1', r1_route)
        assert router._routes.get('r1') == [0, 1, 2]  # A=0, B=1, C=2

    def test_release_clears_routes(self, router):
        router.reserve('r1', router.plan('r1', (0.0, 0.0), 'C'))
        router.release('r1')
        assert 'r1' not in router._routes

    def test_reserve_overwrites_prior_route(self, router):
        router.reserve('r1', router.plan('r1', (0.0, 0.0), 'C'))
        router.reserve('r1', router.plan('r1', (0.0, 0.0), 'D'))
        assert router._routes.get('r1') == [0, 3]  # A=0, D=3


class TestDetectConflict:
    def test_no_conflict_when_no_other_reservation(self, router):
        my_route = router.plan('r1', (0.0, 0.0), 'C')
        assert router.detect_conflict(my_route, 'r1') is None

    def test_no_conflict_disjoint_routes(self, router):
        # r2 reserves A→D; r1 plans A→B→C (no overlap)
        r2_route = router.plan('r2', (0.0, 0.0), 'D')
        router.reserve('r2', r2_route)
        # Explicitly request A→B→C and verify it's NOT flagged as conflict
        # (r2 is on A↔D, not A→B→C)
        explicit = [{'x': 0.0, 'y': 0.0}, {'x': 1.0, 'y': 0.0}, {'x': 2.0, 'y': 0.0}]
        assert router.detect_conflict(explicit, 'r1') is None

    def test_e_share_same_direction(self, router):
        r2_route = router.plan('r2', (0.0, 0.0), 'C')  # A→B→C
        router.reserve('r2', r2_route)
        # r1 plans the exact same edges
        my_route = [{'x': 0.0, 'y': 0.0}, {'x': 1.0, 'y': 0.0}, {'x': 2.0, 'y': 0.0}]
        info = router.detect_conflict(my_route, 'r1')
        assert info is not None
        assert info.partner_id == 'r2'
        assert info.conflict_type == 'E_SHARE'
        assert info.conflict_entry_idx == 0  # edge (A,B) is first conflict

    def test_e_oppose_head_on(self, router):
        # r2 reserves A→B→C (edges (0,1), (1,2))
        r2_route = router.plan('r2', (0.0, 0.0), 'C')
        router.reserve('r2', r2_route)
        # r1 plans the reverse C→B→A (edges (2,1), (1,0))
        my_route = [{'x': 2.0, 'y': 0.0}, {'x': 1.0, 'y': 0.0}, {'x': 0.0, 'y': 0.0}]
        info = router.detect_conflict(my_route, 'r1')
        assert info is not None
        assert info.partner_id == 'r2'
        assert info.conflict_type == 'E_OPPOSE'
        assert info.conflict_entry_idx == 0
