"""Detector de posturas usando YOLO + pose estimation.

Detecta personas y determina si una persona está de pie, sentada o
acostada, calculando la altura aparente (bounding box) y la razón de
aspecto (ancho/alto). Una persona acostada tiende a ser mucho más ancha
que alta en la imagen (relación aspecto alta y altura baja).

Estrategia:
  1. Detección de personas (YOLO).
  2. Para cada persona, estimar keypoints de pose.
  3. Clasificar postura según la geometría del bounding box y los keypoints.

Devuelve una lista de detecciones con la postura clasificada.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger("posture_detector")


class PostureDetector:
    """Detecta personas y clasifica su postura en una imagen."""

    def __init__(self, model_path: str = "yolov8n-pose.pt", confidence: float = 0.4) -> None:
        # Importación diferida para no cargar torch si no se usa detección.
        from ultralytics import YOLO

        self.confidence = confidence
        self.model = YOLO(model_path)
        logger.info("Modelo de pose cargado: %s", model_path)

    def detect(self, frame_bgr: np.ndarray) -> list[dict[str, Any]]:
        """Detecta personas y clasifica su postura.

        Args:
            frame_bgr: Imagen en formato BGR (numpy array HxWx3).

        Returns:
            Lista de dicts con: bbox, posture, score, keypoints.
        """
        results = self.model.predict(
            frame_bgr,
            conf=self.confidence,
            classes=[0],  # 0 = persona
            verbose=False,
        )

        detections: list[dict[str, Any]] = []
        for result in results:
            if result.boxes is None or len(result.boxes) == 0:
                continue

            boxes = result.boxes.xyxy.cpu().numpy()
            confs = result.boxes.conf.cpu().numpy()

            # keypoints si el modelo es "-pose"
            keypoints = None
            if result.keypoints is not None and result.keypoints.xy is not None:
                keypoints = result.keypoints.xy.cpu().numpy()

            for i, box in enumerate(boxes):
                x1, y1, x2, y2 = box
                width = float(x2 - x1)
                height = float(y2 - y1)
                score = float(confs[i])

                posture = self._classify_posture(width, height, keypoints, i)

                detections.append(
                    {
                        "bbox": [float(x1), float(y1), float(x2), float(y2)],
                        "posture": posture,
                        "score": score,
                        "keypoints": keypoints[i].tolist() if keypoints is not None else [],
                    }
                )

        return detections

    @staticmethod
    def _classify_posture(
        width: float,
        height: float,
        keypoints: np.ndarray | None,
        index: int,
    ) -> str:
        """Clasifica la postura de una persona según su geometría.

        Heurística simple:
          - aspect_ratio = width / height
          - Una persona de pie es alta y angosta (aspect_ratio bajo).
          - Una persona acostada es ancha y baja (aspect_ratio alto).
        """
        if height <= 0:
            return "unknown"

        aspect_ratio = width / height

        # Si hay keypoints de pose, podemos confirmar "acostada" si la
        # altura del cuerpo (hombros-cadera) es mucho menor que el ancho.
        if keypoints is not None and len(keypoints) > index:
            kp = keypoints[index]
            # YOLO-pose: 5=left_shoulder, 6=right_shoulder, 11=left_hip, 12=right_hip
            if len(kp) >= 13:
                shoulder_y = (kp[5][1] + kp[6][1]) / 2.0
                hip_y = (kp[11][1] + kp[12][1]) / 2.0
                torso_height = abs(hip_y - shoulder_y)
                shoulder_width = abs(kp[6][0] - kp[5][0])
                if torso_height > 0 and shoulder_width / torso_height > 2.5:
                    return "lying_down"

        if aspect_ratio > 1.6:
            return "lying_down"
        if aspect_ratio > 0.9:
            return "sitting"
        return "standing"

    @staticmethod
    def is_abnormal(posture: str) -> bool:
        """Determina si una postura es 'anormal' (acostada)."""
        return posture == "lying_down"