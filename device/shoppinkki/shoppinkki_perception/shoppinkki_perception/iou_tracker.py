"""Lightweight IoU-based multi-object tracker.

Provides stable track_id assignments across frames by matching new detections
to existing tracks via Intersection-over-Union (IoU). Replaces ByteTrack in
the ROS integration context where YOLO runs on a stateless TCP server.

Usage::

    tracker = IouTracker()
    detections = tracker.update(yolo_detections)
    # Each dict in detections now has a 'track_id' field
"""

from __future__ import annotations

from typing import Dict, List, Optional


class IouTracker:
    """Frame-to-frame bbox IoU tracker.

    Parameters
    ----------
    max_age:
        Frames to keep a track alive after last detection.
    min_iou:
        Minimum IoU to consider a detection a match for an existing track.
    """

    def __init__(self, max_age: int = 10, min_iou: float = 0.3) -> None:
        self._max_age = max_age
        self._min_iou = min_iou

        # track_id → {'bbox': dict, 'age': int}
        self._tracks: Dict[int, dict] = {}
        self._next_id: int = 1

    def update(self, detections: List[dict]) -> List[dict]:
        """Assign track_id to each detection.

        Parameters
        ----------
        detections:
            List of bbox dicts from YOLO server, each with at minimum
            ``{'cx', 'cy', 'area', 'confidence', 'x1', 'y1', 'x2', 'y2'}``.

        Returns
        -------
        list
            Same dicts with an additional ``'track_id': int`` field.
        """
        # Age all existing tracks
        for tid in list(self._tracks):
            self._tracks[tid]['age'] += 1

        # Match detections to existing tracks (greedy, best IoU first)
        unmatched_dets = list(range(len(detections)))
        matched_tids: Dict[int, int] = {}  # det_idx → track_id

        if self._tracks and unmatched_dets:
            track_ids = list(self._tracks.keys())
            iou_matrix = [
                [self._iou(detections[di], self._tracks[tid]['bbox'])
                 for tid in track_ids]
                for di in unmatched_dets
            ]

            used_tracks: set = set()
            for _ in range(min(len(unmatched_dets), len(track_ids))):
                best_val = self._min_iou - 1e-9
                best_di = best_ti = -1
                for di in unmatched_dets:
                    if di in matched_tids:
                        continue
                    row = iou_matrix[unmatched_dets.index(di)]
                    for j, tid in enumerate(track_ids):
                        if tid in used_tracks:
                            continue
                        if row[j] > best_val:
                            best_val = row[j]
                            best_di = di
                            best_ti = tid
                if best_di == -1:
                    break
                matched_tids[best_di] = best_ti
                used_tracks.add(best_ti)

        # Update matched tracks; assign new IDs to unmatched
        result = []
        for di, det in enumerate(detections):
            if di in matched_tids:
                tid = matched_tids[di]
                self._tracks[tid] = {'bbox': det, 'age': 0}
            else:
                tid = self._next_id
                self._next_id += 1
                if self._next_id > 10000:
                    self._next_id = 1
                self._tracks[tid] = {'bbox': det, 'age': 0}

            out = dict(det)
            out['track_id'] = tid
            result.append(out)

        # Evict stale tracks
        for tid in list(self._tracks):
            if self._tracks[tid]['age'] > self._max_age:
                del self._tracks[tid]

        return result

    def reset(self) -> None:
        """Clear all tracks (call on session end / doll_detector.reset())."""
        self._tracks.clear()
        self._next_id = 1

    # ── helpers ──────────────────────────────────

    @staticmethod
    def _iou(a: dict, b: dict) -> float:
        """IoU between two bbox dicts that each have x1,y1,x2,y2."""
        ax1 = a.get('x1', 0); ay1 = a.get('y1', 0)
        ax2 = a.get('x2', 1); ay2 = a.get('y2', 1)
        bx1 = b.get('x1', 0); by1 = b.get('y1', 0)
        bx2 = b.get('x2', 1); by2 = b.get('y2', 1)

        ix1 = max(ax1, bx1); iy1 = max(ay1, by1)
        ix2 = min(ax2, bx2); iy2 = min(ay2, by2)

        inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
        if inter == 0:
            return 0.0

        area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
        area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0
