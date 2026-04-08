"""CNN ReID feature extractor for owner-doll identification.

Ported from owner_detection/reid_engine.py (joey_detection branch, commit 625025ab).

Architecture:
    - Primary:  MobileNetV3-Small (ImageNet pre-trained), classifier head removed
                → 1024-dim L2-normalised feature vector
    - Fallback: 6-float colour statistics (mean+std per BGR channel) when torch
                is not available (e.g. Raspberry Pi without GPU drivers installed)

Usage::

    engine = ReIDEngine()
    feat = engine.extract_features(roi_bgr)   # np.ndarray shape (D,)
    sim  = engine.compute_similarity(feat1, feat2)  # float in [-1, 1]
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np

logger = logging.getLogger(__name__)

# ── Optional heavy imports ─────────────────────────────────────────────────────

try:
    import torch
    import torch.nn as nn
    import torchvision.models as models
    import torchvision.transforms as T
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False
    logger.warning('ReIDEngine: torch not available — falling back to colour stats')


class ReIDEngine:
    """Extract L2-normalised CNN features from a BGR ROI image.

    Parameters
    ----------
    device:
        Torch device string ('cpu', 'cuda'). Defaults to 'cuda' if available,
        else 'cpu'.
    """

    def __init__(self, device: str | None = None) -> None:
        self._use_cnn = _TORCH_AVAILABLE
        self._feat_dim = 1024 if _TORCH_AVAILABLE else 6

        if self._use_cnn:
            self._device = torch.device(
                device if device else ('cuda' if torch.cuda.is_available() else 'cpu')
            )
            # MobileNetV3-Small: lightweight, Pi 5 compatible
            backbone = models.mobilenet_v3_small(
                weights=models.MobileNet_V3_Small_Weights.IMAGENET1K_V1
            )
            # Remove the classifier → output of adaptive_avg_pool (1024-dim)
            self._model = nn.Sequential(*list(backbone.children())[:-1])
            self._model.to(self._device)
            self._model.eval()

            self._transform = T.Compose([
                T.ToPILImage(),
                T.Resize((224, 224)),
                T.ToTensor(),
                T.Normalize(mean=[0.485, 0.456, 0.406],
                            std=[0.229, 0.224, 0.225]),
            ])
            logger.info('ReIDEngine: MobileNetV3-Small loaded on %s', self._device)
        else:
            self._device = None
            self._model = None
            self._transform = None
            logger.info('ReIDEngine: colour-stats fallback mode')

    @property
    def feat_dim(self) -> int:
        return self._feat_dim

    def extract_features(self, roi_bgr) -> np.ndarray:
        """Extract L2-normalised feature vector from a BGR image ROI.

        Parameters
        ----------
        roi_bgr:
            numpy ndarray (H, W, 3) in BGR colour order (OpenCV convention).

        Returns
        -------
        np.ndarray
            1-D float32 array, L2-normalised.  Shape: (feat_dim,).
        """
        if roi_bgr is None or roi_bgr.size == 0:
            return np.zeros(self._feat_dim, dtype=np.float32)

        if self._use_cnn:
            return self._cnn_features(roi_bgr)
        return self._colour_stats(roi_bgr)

    def compute_similarity(self, feat_a: np.ndarray, feat_b: np.ndarray) -> float:
        """Cosine similarity between two L2-normalised feature vectors.

        Returns float in [-1, 1].  Both inputs must be L2-normalised.
        """
        try:
            return float(np.dot(feat_a, feat_b))
        except Exception:
            return 0.0

    # ── private ───────────────────────────────────────────────────────────────

    def _cnn_features(self, roi_bgr) -> np.ndarray:
        try:
            import cv2
            rgb = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2RGB)
            tensor = self._transform(rgb).unsqueeze(0).to(self._device)
            with torch.no_grad():
                feat = self._model(tensor)
            feat = feat.squeeze().cpu().numpy().astype(np.float32)
            # L2 normalise
            norm = np.linalg.norm(feat)
            if norm > 1e-8:
                feat = feat / norm
            return feat
        except Exception as e:
            logger.debug('ReIDEngine: CNN inference failed: %s', e)
            return np.zeros(self._feat_dim, dtype=np.float32)

    def _colour_stats(self, roi_bgr) -> np.ndarray:
        """6-float fallback: mean + std per BGR channel."""
        try:
            import cv2
            small = cv2.resize(roi_bgr, (32, 64))
            feats: List[float] = []
            for c in range(3):
                ch = small[:, :, c].astype(np.float32) / 255.0
                feats.append(float(np.mean(ch)))
                feats.append(float(np.std(ch)))
            arr = np.array(feats, dtype=np.float32)
            norm = np.linalg.norm(arr)
            if norm > 1e-8:
                arr = arr / norm
            return arr
        except Exception:
            return np.zeros(self._feat_dim, dtype=np.float32)
