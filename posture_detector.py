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

    def annotate(self, frame_bgr: np.ndarray, detections: list[dict[str, Any]]) -> np.ndarray:
        """Dibuja las cajas, etiquetas y advertencias de postura en la imagen."""
        import cv2

        annotated = frame_bgr.copy()
        for det in detections:
            x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
            posture = det["posture"]
            score = det["score"]

            if posture == "lying_down":
                color = (0, 0, 255)  # Rojo (Peligro)
                label = f"!PELIGRO: ACOSTADA! ({score:.2f})"
            elif posture == "sitting":
                color = (0, 165, 255)  # Naranja
                label = f"Sentada ({score:.2f})"
            else:
                color = (0, 255, 0)  # Verde (Normal)
                label = f"De pie ({score:.2f})"

            # Caja delimitadora
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 3)

            # Fondo para el texto
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(annotated, (x1, max(0, y1 - th - 10)), (x1 + tw + 6, max(th + 10, y1)), color, -1)
            cv2.putText(
                annotated,
                label,
                (x1 + 3, max(th + 2, y1 - 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

            # Dibujar puntos clave si existen
            keypoints = det.get("keypoints", [])
            for kp in keypoints:
                kx, ky = int(kp[0]), int(kp[1])
                if kx > 0 and ky > 0:
                    cv2.circle(annotated, (kx, ky), 4, color, -1)

        return annotated

    @staticmethod
    def _classify_posture(
        width: float,
        height: float,
        keypoints: np.ndarray | None,
        index: int,
    ) -> str:
        """Clasifica la postura analizando la orientación de la columna y la geometría."""
        if height <= 0:
            return "unknown"

        aspect_ratio = width / height

        # Análisis mediante puntos anatómicos (YOLO-pose COCO: 17 keypoints)
        if keypoints is not None and len(keypoints) > index:
            kp = keypoints[index]
            mid_shoulder_x: float | None = None
            mid_shoulder_y: float | None = None

            # 5: hombro izq, 6: hombro der, 11: cadera izq, 12: cadera der
            if len(kp) >= 13:
                s_left, s_right = kp[5], kp[6]
                h_left, h_right = kp[11], kp[12]

                # Verificar hombros
                if s_left[0] > 0 and s_right[0] > 0:
                    mid_shoulder_x = float(s_left[0] + s_right[0]) / 2.0
                    mid_shoulder_y = float(s_left[1] + s_right[1]) / 2.0

                if mid_shoulder_x is not None and h_left[0] > 0 and h_right[0] > 0:
                    mid_hip_x = float(h_left[0] + h_right[0]) / 2.0
                    mid_hip_y = float(h_left[1] + h_right[1]) / 2.0

                    dx = abs(mid_shoulder_x - mid_hip_x)
                    dy = abs(mid_shoulder_y - mid_hip_y)

                    # Si el torso es más horizontal que vertical -> acostada
                    if dx > 1.2 * dy:
                        return "lying_down"

            # 15: tobillo izq, 16: tobillo der
            if len(kp) >= 17 and mid_shoulder_x is not None and mid_shoulder_y is not None:
                a_left, a_right = kp[15], kp[16]
                if a_left[0] > 0 and a_right[0] > 0:
                    mid_ankle_x = float(a_left[0] + a_right[0]) / 2.0
                    mid_ankle_y = float(a_left[1] + a_right[1]) / 2.0

                    body_dx = abs(mid_shoulder_x - mid_ankle_x)
                    body_dy = abs(mid_shoulder_y - mid_ankle_y)
                    if body_dx > 1.1 * body_dy:
                        return "lying_down"

        # Respaldo por relación de aspecto de la caja delimitadora
        if aspect_ratio > 1.35:
            return "lying_down"
        if aspect_ratio > 0.85:
            return "sitting"
        return "standing"

    @staticmethod
    def is_abnormal(posture: str) -> bool:
        """Determina si una postura es 'anormal' o de peligro (persona acostada)."""
        return posture == "lying_down"