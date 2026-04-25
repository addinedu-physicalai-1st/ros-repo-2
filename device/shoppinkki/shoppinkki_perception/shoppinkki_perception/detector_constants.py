"""shoppinkki_perception 튜닝 가능 임계값 / 매직 넘버.

doll_detector / hw_controller 등에서 import해서 사용한다. 값 조정 시 이 파일만 수정.
"""

import os

# ── YOLO / 등록 임계값 ─────────────────────────────────────────────────────────
MIN_CONFIDENCE: float = float(os.environ.get('MIN_CONFIDENCE', '0.42'))
"""YOLO 최소 신뢰도. env로 오버라이드 가능."""

REGISTRATION_MIN_CONFIDENCE: float = 0.20
"""등록 단계 추가 신뢰도 임계값."""

REGISTRATION_MIN_AREA_RATIO: float = 0.005
"""등록 단계 bbox 최소 화면 점유율."""

REGISTRATION_SNAPSHOT_COOLDOWN: float = 0.4
"""등록 스냅샷 최소 간격 (초)."""

REGISTRATION_STABLE_FRAMES: int = 1
"""동일 후보 연속 감지 필요 프레임 수."""

# ── ReID / 매칭 임계값 ────────────────────────────────────────────────────────
REID_THRESHOLD: float = float(os.environ.get('REID_THRESHOLD', '0.48'))
"""ReID 코사인 유사도 임계값. env로 오버라이드 가능."""

HSV_THRESHOLD: float = 0.38
"""HSV 히스토그램 상관계수 임계값."""

VERIFY_FRAMES: int = 5
"""safe_id 잠금에 필요한 연속 매칭 횟수."""

# ── 자동 보정 ─────────────────────────────────────────────────────────────────
CALIBRATION_ADD_THRESHOLD: float = 0.94
"""이 이상 유사도면 이미 갤러리에 커버된 것으로 간주 → 추가 안 함."""

CALIBRATION_INTERVAL: int = 30
"""자동 보정 프레임 간격."""

MAX_GALLERY_SIZE: int = 50
"""갤러리(인형 피처 벡터 모음) 최대 크기."""

# ── 등록 화면 타원 가이드 (HWController LCD와 좌표 통일) ─────────────────────
REGISTRATION_BASE_WIDTH: float = 320.0
"""등록 ellipse 정의 기준 해상도 (가로). 실제 카메라 프레임 폭에 비례 스케일."""

REGISTRATION_BASE_HEIGHT: float = 240.0
"""등록 ellipse 정의 기준 해상도 (세로)."""

REGISTRATION_ELLIPSE_RX: float = 140.0
"""기준 해상도(320x240)에서의 ellipse x 반지름."""

REGISTRATION_ELLIPSE_RY: float = 210.0
"""기준 해상도(320x240)에서의 ellipse y 반지름."""

REGISTRATION_ELLIPSE_MIN_R: float = 20.0
"""스케일된 ellipse 반지름의 최솟값 (작은 프레임 방어)."""

# ── HSV "빨간색" 검출 (인형 색상 통계) ────────────────────────────────────────
# Hue는 0 / 180 부근에서 wrap-around되므로 두 범위로 나눠 OR 마스크.
RED_HUE_LOWER_RANGE: tuple[int, int] = (0, 10)
"""빨간색으로 분류할 Hue 첫 번째 범위 (양 끝 포함)."""

RED_HUE_UPPER_RANGE: tuple[int, int] = (165, 180)
"""빨간색으로 분류할 Hue 두 번째 범위."""

RED_SATURATION_MIN: int = 70
"""빨강 분류 최소 Saturation. 무채색(흰/검/회) 제외."""

RED_VALUE_MIN: int = 50
"""빨강 분류 최소 Value. 너무 어두운 영역 제외."""
