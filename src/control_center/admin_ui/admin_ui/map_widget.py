# Copyright 2024 shoppinkki
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""MapWidget -- shop_map.png 위에 로봇 위치 실시간 표시.

맵 이미지를 90도 CCW 회전하여 가로(landscape)로 표시.

좌표 변환 (90도 CCW 회전 적용):
    Qt rotate(-90) 변환 후 픽셀 매핑:
        px = img_w - (y - origin_y) / resolution * scale
        py = img_h - (x - origin_x) / resolution * scale

    img_w = 원본 PNG height (회전 후 가로)
    img_h = 원본 PNG width  (회전 후 세로)

shop.yaml: resolution=0.01, origin=(-0.293, -1.660)
"""

import math
import os

from PyQt6.QtCore import Qt, QPointF, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor, QFont, QMouseEvent, QPainter, QPen, QPixmap, QPolygonF, QTransform,
)
from PyQt6.QtWidgets import QLabel

MAP_RESOLUTION = 0.01    # m/px  (shop.yaml resolution=0.010)
MAP_ORIGIN_X = -0.293    # m     (shop.yaml origin[0])
MAP_ORIGIN_Y = -1.660    # m     (shop.yaml origin[1])
MAP_SCALE = 4            # PNG = PGM x4

# robot_id별 색상
ROBOT_COLORS = [
    QColor('#27ae60'),  # green
    QColor('#2980b9'),  # blue
    QColor('#8e44ad'),  # purple
    QColor('#e67e22'),  # orange
    QColor('#16a085'),  # teal
    QColor('#c0392b'),  # red
    QColor('#d35400'),  # dark orange
    QColor('#2c3e50'),  # dark navy
    QColor('#f39c12'),  # yellow
    QColor('#1abc9c'),  # emerald
]

ROBOT_ICON_RADIUS = 8
ARROW_LENGTH_PX = 18
BLINK_INTERVAL_MS = 500


class MapWidget(QLabel):
    """맵 오버레이 위젯."""

    map_clicked = pyqtSignal(float, float)  # world x, y

    def __init__(self, parent=None):
        super().__init__(parent)
        self._base_pixmap: QPixmap | None = None
        self._robot_states: dict[str, dict] = {}
        self._robot_color_map: dict[str, QColor] = {}
        self._color_index = 0
        self._goto_marker: tuple[float, float] | None = None
        self._blink_state = False

        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(BLINK_INTERVAL_MS)
        self._blink_timer.timeout.connect(self._on_blink)
        self._blink_timer.start()

        self.setMinimumSize(400, 320)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self._load_map()

    def _load_map(self):
        candidates = []
        try:
            from ament_index_python.packages import get_package_share_directory
            candidates.append(
                os.path.join(get_package_share_directory('admin_ui'), 'assets', 'shop_map.png')
            )
        except Exception:
            pass
        candidates.append(
            os.path.join(os.path.dirname(__file__), '..', 'assets', 'shop_map.png')
        )

        for map_path in candidates:
            if os.path.isfile(map_path):
                pix = QPixmap(map_path)
                if not pix.isNull():
                    # 90도 CCW 회전하여 가로 표시
                    self._base_pixmap = pix.transformed(QTransform().rotate(-90))
                    self.setFixedSize(self._base_pixmap.size())
                    return

    def _get_robot_color(self, robot_id: str) -> QColor:
        if robot_id not in self._robot_color_map:
            self._robot_color_map[robot_id] = ROBOT_COLORS[
                self._color_index % len(ROBOT_COLORS)
            ]
            self._color_index += 1
        return self._robot_color_map[robot_id]

    # ──────────────────────────────────────────────
    # 좌표 변환 (90도 CCW 회전 적용)
    # ──────────────────────────────────────────────
    #
    # Qt rotate(-90) 픽셀 매핑:
    #   원본 (col, row)  →  회전 (row,  W_orig - 1 - col)
    #
    # 원본 PNG 좌표:
    #   col = (x - ox) / r * s
    #   row = H_orig - (y - oy) / r * s
    #
    # 회전 후:
    #   px = row = H_orig - (y - oy) / r * s   →  회전 이미지 width = H_orig
    #   py = W_orig - 1 - col ≈ W_orig - (x - ox) / r * s
    #
    # 즉:
    #   px = img_w - (y - oy) / r * s
    #   py = img_h - (x - ox) / r * s

    def _world_to_pixel(self, x: float, y: float) -> tuple[int, int]:
        """월드 좌표 → 회전된 맵 픽셀 좌표.

        PNG 이미지가 PGM 대비 x축(col) 반전 상태이므로
        py 에서 img_h 감산 없이 직접 매핑.
        """
        img_w = self._base_pixmap.width() if self._base_pixmap else self.width()
        px = int(img_w - (y - MAP_ORIGIN_Y) / MAP_RESOLUTION * MAP_SCALE)
        py = int((x - MAP_ORIGIN_X) / MAP_RESOLUTION * MAP_SCALE)
        return px, py

    def _pixel_to_world(self, px: int, py: int) -> tuple[float, float]:
        """회전된 맵 픽셀 좌표 → 월드 좌표."""
        img_w = self._base_pixmap.width() if self._base_pixmap else self.width()
        y = MAP_ORIGIN_Y + (img_w - px) / MAP_SCALE * MAP_RESOLUTION
        x = MAP_ORIGIN_X + py / MAP_SCALE * MAP_RESOLUTION
        return x, y

    def update_robot(self, robot_id: str, state: dict):
        self._robot_states[robot_id] = state
        self.update()

    def set_goto_marker(self, x: float, y: float):
        self._goto_marker = (x, y)
        self.update()

    def clear_goto_marker(self):
        self._goto_marker = None
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            x, y = self._pixel_to_world(event.pos().x(), event.pos().y())
            self._goto_marker = (x, y)
            self.map_clicked.emit(x, y)
            self.update()
        super().mousePressEvent(event)

    def _on_blink(self):
        self._blink_state = not self._blink_state
        needs_blink = any(
            s.get('mode') in ('LOCKED', 'HALTED') or s.get('is_locked_return')
            for s in self._robot_states.values()
        )
        if needs_blink:
            self.update()

    def _draw_robot(self, painter: QPainter, robot_id: str, state: dict):
        """로봇 아이콘 (원형 + 방향 화살표 + ID 레이블)."""
        pos_x = state.get('pos_x', 0.0)
        pos_y = state.get('pos_y', 0.0)
        yaw = state.get('yaw', 0.0)
        mode = state.get('mode', 'OFFLINE')
        is_locked_return = state.get('is_locked_return', False)

        px, py = self._world_to_pixel(pos_x, pos_y)
        color = self._get_robot_color(robot_id)
        r = ROBOT_ICON_RADIUS

        if mode == 'OFFLINE':
            painter.setPen(QPen(QColor('#aaaaaa'), 2))
            painter.drawLine(px - r, py - r, px + r, py + r)
            painter.drawLine(px + r, py - r, px - r, py + r)
        else:
            # 원형 아이콘
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(px - r, py - r, r * 2, r * 2)

            # 방향 화살표 — 월드 좌표 기반으로 끝점 계산 후 픽셀 변환
            arrow_m = ARROW_LENGTH_PX * MAP_RESOLUTION / MAP_SCALE  # 픽셀 → 미터
            end_x = pos_x + arrow_m * math.cos(yaw)
            end_y = pos_y + arrow_m * math.sin(yaw)
            epx, epy = self._world_to_pixel(end_x, end_y)

            painter.setPen(QPen(color.darker(130), 2))
            painter.drawLine(px, py, epx, epy)

            # 화살촉 (삼각형)
            head_size = 5
            dx, dy = float(epx - px), float(epy - py)
            angle = math.atan2(dy, dx)
            lx = epx - head_size * math.cos(angle - 0.5)
            ly = epy - head_size * math.sin(angle - 0.5)
            rx = epx - head_size * math.cos(angle + 0.5)
            ry = epy - head_size * math.sin(angle + 0.5)

            painter.setBrush(color.darker(130))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(QPolygonF([
                QPointF(epx, epy), QPointF(lx, ly), QPointF(rx, ry),
            ]))

            # 점멸 테두리
            if is_locked_return and self._blink_state:
                painter.setPen(QPen(QColor('#e74c3c'), 3))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(px - r - 3, py - r - 3, (r + 3) * 2, (r + 3) * 2)
            elif mode == 'HALTED' and self._blink_state:
                painter.setPen(QPen(QColor('#ffffff'), 3))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(px - r - 3, py - r - 3, (r + 3) * 2, (r + 3) * 2)

            # robot_id 레이블 (원 위에 중앙 정렬)
            painter.setPen(QColor('#ffffff'))
            font = QFont()
            font.setPointSize(9)
            font.setBold(True)
            painter.setFont(font)
            fm = painter.fontMetrics()
            text_w = fm.horizontalAdvance(robot_id)
            painter.drawText(px - text_w // 2, py - r - 4, robot_id)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._base_pixmap is not None:
            painter.drawPixmap(0, 0, self._base_pixmap)
        else:
            painter.fillRect(self.rect(), QColor('#555555'))
            painter.setPen(QColor('#ffffff'))
            font = QFont()
            font.setPointSize(14)
            painter.setFont(font)
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, '맵 이미지 없음'
            )

        for robot_id, state in self._robot_states.items():
            self._draw_robot(painter, robot_id, state)

        if self._goto_marker is not None:
            mx, my = self._goto_marker
            mpx, mpy = self._world_to_pixel(mx, my)
            painter.setPen(QPen(QColor('#3498db'), 2))
            arm = 10
            painter.drawLine(mpx - arm, mpy, mpx + arm, mpy)
            painter.drawLine(mpx, mpy - arm, mpx, mpy + arm)
            painter.drawEllipse(mpx - 4, mpy - 4, 8, 8)

        painter.end()
