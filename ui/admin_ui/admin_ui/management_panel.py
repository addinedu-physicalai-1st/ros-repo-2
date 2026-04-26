"""ManagementPanel -- user & session management for admin UI.

Two QTableWidgets stacked vertically:
1. Users: user_id, created_at, [delete] button
2. Active sessions: session_id, robot_id, user_id, created_at, [terminate] button

Data source: control_service REST API.
Auto-refresh via QTimer (10-second interval).
"""

from __future__ import annotations

import json
import logging
import urllib.request

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class ManagementPanel(QWidget):
    """User and session management panel."""

    user_deleted = pyqtSignal(str)
    session_terminated = pyqtSignal(int)

    def __init__(self, rest_base: str, parent=None):
        super().__init__(parent)
        self._rest_base = rest_base.rstrip('/')
        self._build_ui()

        self._timer = QTimer(self)
        self._timer.setInterval(10_000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        QTimer.singleShot(500, self.refresh)

    # ── UI ────────────────────────────────────

    def _build_ui(self):
        self.setMaximumHeight(280)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel('사용자 / 세션 관리')
        header.setStyleSheet(
            'background-color: #2980b9; color: white; font-weight: bold; '
            'padding: 4px 8px;'
        )
        layout.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter)

        # ── Users section ──
        user_box = QWidget()
        ul = QVBoxLayout(user_box)
        ul.setContentsMargins(2, 2, 2, 1)
        ul.setSpacing(2)

        uh = QHBoxLayout()
        uh.addWidget(QLabel('<b>회원 목록</b>'))
        btn_refresh = QPushButton('새로고침')
        btn_refresh.setFixedWidth(70)
        btn_refresh.clicked.connect(self.refresh)
        uh.addWidget(btn_refresh)
        ul.addLayout(uh)

        self._user_table = QTableWidget(0, 3)
        self._user_table.setHorizontalHeaderLabels(['아이디', '가입일', ''])
        self._user_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._user_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents)
        self._user_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents)
        self._user_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._user_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._user_table.verticalHeader().setVisible(False)
        self._user_table.verticalHeader().setDefaultSectionSize(24)
        ul.addWidget(self._user_table)
        splitter.addWidget(user_box)

        # ── Sessions section ──
        sess_box = QWidget()
        sl = QVBoxLayout(sess_box)
        sl.setContentsMargins(2, 1, 2, 2)
        sl.setSpacing(2)
        sl.addWidget(QLabel('<b>활성 세션</b>'))

        self._session_table = QTableWidget(0, 5)
        self._session_table.setHorizontalHeaderLabels(
            ['세션 ID', '로봇', '사용자', '시작 시간', ''])
        self._session_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self._session_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents)
        self._session_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch)
        self._session_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents)
        self._session_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents)
        self._session_table.verticalHeader().setDefaultSectionSize(24)
        self._session_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._session_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._session_table.verticalHeader().setVisible(False)
        sl.addWidget(self._session_table)
        splitter.addWidget(sess_box)

    # ── Data fetch ────────────────────────────

    def refresh(self):
        self._load_users()
        self._load_sessions()

    def _rest_get(self, path: str):
        try:
            url = f'{self._rest_base}{path}'
            with urllib.request.urlopen(url, timeout=3) as resp:
                return json.loads(resp.read())
        except Exception as e:
            logger.warning('ManagementPanel REST GET %s: %s', path, e)
            return None

    def _rest_delete(self, path: str):
        try:
            url = f'{self._rest_base}{path}'
            req = urllib.request.Request(url, method='DELETE')
            with urllib.request.urlopen(req, timeout=3) as resp:
                return json.loads(resp.read())
        except Exception as e:
            logger.warning('ManagementPanel REST DELETE %s: %s', path, e)
            return None

    def _rest_patch(self, path: str, data: dict):
        try:
            url = f'{self._rest_base}{path}'
            body = json.dumps(data).encode('utf-8')
            req = urllib.request.Request(url, data=body, method='PATCH',
                                        headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=3) as resp:
                return json.loads(resp.read())
        except Exception as e:
            logger.warning('ManagementPanel REST PATCH %s: %s', path, e)
            return None

    # ── Users ─────────────────────────────────

    def _load_users(self):
        data = self._rest_get('/users')
        if data is None:
            return
        self._user_table.setRowCount(len(data))
        for i, u in enumerate(data):
            self._user_table.setItem(i, 0, QTableWidgetItem(u.get('user_id', '')))
            created = str(u.get('created_at', ''))[:19]
            self._user_table.setItem(i, 1, QTableWidgetItem(created))
            btn = QPushButton('삭제')
            btn.setFixedWidth(50)
            uid = u.get('user_id', '')
            btn.clicked.connect(lambda _, uid=uid: self._delete_user(uid))
            self._user_table.setCellWidget(i, 2, btn)

    def _delete_user(self, user_id: str):
        reply = QMessageBox.question(
            self, '사용자 삭제',
            f"'{user_id}' 사용자를 삭제하시겠습니까?\n활성 세션이 있으면 자동 종료됩니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        result = self._rest_delete(f'/user/{user_id}')
        if result and result.get('ok'):
            self.user_deleted.emit(user_id)
            self.refresh()
        else:
            QMessageBox.warning(self, '삭제 실패',
                                result.get('error', '알 수 없는 오류') if result else '서버 연결 실패')

    # ── Sessions ──────────────────────────────

    def _load_sessions(self):
        data = self._rest_get('/sessions')
        if data is None:
            return
        self._session_table.setRowCount(len(data))
        for i, s in enumerate(data):
            self._session_table.setItem(i, 0, QTableWidgetItem(str(s.get('session_id', ''))))
            self._session_table.setItem(i, 1, QTableWidgetItem(s.get('robot_id', '')))
            self._session_table.setItem(i, 2, QTableWidgetItem(s.get('user_id', '')))
            created = str(s.get('created_at', ''))[:19]
            self._session_table.setItem(i, 3, QTableWidgetItem(created))
            btn = QPushButton('종료')
            btn.setFixedWidth(50)
            sid = s.get('session_id')
            btn.clicked.connect(lambda _, sid=sid: self._terminate_session(sid))
            self._session_table.setCellWidget(i, 4, btn)

    def _terminate_session(self, session_id: int):
        reply = QMessageBox.question(
            self, '세션 종료',
            f'세션 #{session_id}을 강제 종료하시겠습니까?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        result = self._rest_patch(f'/session/{session_id}', {'is_active': False})
        if result and result.get('ok'):
            self.session_terminated.emit(session_id)
            self.refresh()
        else:
            QMessageBox.warning(self, '종료 실패',
                                result.get('error', '알 수 없는 오류') if result else '서버 연결 실패')
