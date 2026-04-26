"""
rendering/analysis.py
─────────────────────
Automated image analysis pipeline for ProductView base images.

Steps:
  1. Perspective / surface angle detection (Canny + Hough lines)
  2. Homography matrix computation for the print area quad
  3. Displacement map generation (luminance-based wrinkle extraction)
"""

import logging
import os
from pathlib import Path

import cv2
import numpy as np
from django.conf import settings
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────

def analyze_view(product_view) -> dict:
    """
    Full analysis pipeline for a ProductView.
    Returns a dict with keys: surface_angle_deg, perspective_matrix, displacement_map_path.
    The caller (Celery task) is responsible for saving results back to the model.
    """
    image_path = product_view.base_image.path
    image = _load_image(image_path)
    if image is None:
        raise ValueError(f"Cannot load image: {image_path}")

    H, W = image.shape[:2]
    logger.info("Analyzing ProductView %s (%dx%d)", product_view.pk, W, H)

    # 1. Detect surface angle
    angle = _detect_surface_angle(image)
    logger.info("  surface_angle_deg = %.2f", angle)

    # 2. Compute perspective homography for the print area
    matrix = _compute_print_area_homography(image, product_view, angle)
    logger.info("  homography matrix computed")

    # 3. Generate displacement map
    disp_map_image = _generate_displacement_map(image)
    logger.info("  displacement map generated")

    # 4. Save displacement map to Django media
    disp_map_path = _save_displacement_map(disp_map_image, product_view.pk)

    return {
        "surface_angle_deg": angle,
        "perspective_matrix": matrix.tolist(),
        "displacement_map_path": disp_map_path,  # relative to MEDIA_ROOT
    }


# ──────────────────────────────────────────────
# Step 1 — Surface Angle Detection
# ──────────────────────────────────────────────

def _detect_surface_angle(image: np.ndarray) -> float:
    """
    Detects the dominant surface angle of the garment in the image.
    Uses Canny edges + Hough line transform on the central portion of the image.
    Returns angle in degrees (positive = clockwise tilt from vertical).
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Focus on central 60% of the image where the garment body typically is
    H, W = gray.shape
    crop = gray[int(H * 0.2):int(H * 0.8), int(W * 0.1):int(W * 0.9)]

    blurred = cv2.GaussianBlur(crop, (5, 5), 0)
    edges = cv2.Canny(blurred, 30, 90)

    # Hough probabilistic lines
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=60, minLineLength=40, maxLineGap=15)

    if lines is None or len(lines) == 0:
        return 0.0

    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        dx = x2 - x1
        dy = y2 - y1
        if abs(dx) < 3:
            continue  # skip near-vertical segments (likely garment edge, not surface tilt)
        angle_rad = np.arctan2(dy, dx)
        angle_deg = np.degrees(angle_rad)
        # Only consider lines close to horizontal (within ±45°)
        if abs(angle_deg) <= 45:
            angles.append(angle_deg)

    if not angles:
        return 0.0

    # Weighted median — more robust than mean for angles
    angles = np.array(angles)
    median_angle = float(np.median(angles))
    return round(median_angle, 2)


# ──────────────────────────────────────────────
# Step 2 — Perspective Homography
# ──────────────────────────────────────────────

def _compute_print_area_homography(
    image: np.ndarray, product_view, surface_angle_deg: float
) -> np.ndarray:
    """
    Computes a 3×3 perspective (homography) matrix that maps a flat rectangle
    to the print area of the product, accounting for the detected surface angle.

    The matrix maps design-space coords → image-space coords.
    """
    x = product_view.print_area_x
    y = product_view.print_area_y
    w = product_view.print_area_w
    h = product_view.print_area_h

    # Source: flat design corners (top-left, top-right, bottom-right, bottom-left)
    src = np.float32([
        [0, 0],
        [w, 0],
        [w, h],
        [0, h],
    ])

    # Destination: print area corners, adjusted for tilt angle
    angle_rad = np.radians(surface_angle_deg)

    # Perspective effect: top edge shifts inward/outward based on angle
    # This creates a mild keystone distortion matching the product tilt
    tilt_px = h * np.sin(angle_rad) * 0.4  # empirically tuned factor

    dst = np.float32([
        [x + tilt_px, y],               # top-left (shifted by tilt)
        [x + w - tilt_px, y],            # top-right
        [x + w, y + h],                  # bottom-right
        [x, y + h],                      # bottom-left
    ])

    matrix, _ = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)

    if matrix is None:
        # Fallback: simple translation + scale (no perspective)
        matrix = np.array([
            [1, 0, x],
            [0, 1, y],
            [0, 0, 1],
        ], dtype=np.float64)

    return matrix


# ──────────────────────────────────────────────
# Step 3 — Displacement Map Generation
# ──────────────────────────────────────────────

def _generate_displacement_map(image: np.ndarray) -> np.ndarray:
    """
    Generates a grayscale displacement map from the base image.

    Technique:
      - Convert to LAB color space → extract L (luminance) channel
      - Compute high-frequency detail via Difference-of-Gaussians (DoG)
        which isolates wrinkles/folds from global shading
      - Normalize to [0, 255]
      - Apply mild blur to smooth the warp field

    Map encoding:
      128 = no displacement (neutral)
      > 128 = positive displacement (design shifts toward light)
      < 128 = negative displacement (design shifts toward shadow/fold)
    """
    # Convert to float [0, 1]
    img_float = image.astype(np.float32) / 255.0

    # To LAB, extract L channel
    lab = cv2.cvtColor(img_float, cv2.COLOR_BGR2Lab)
    L = lab[:, :, 0]  # range [0, 100] in OpenCV float

    # Normalize L to [0, 1]
    L_norm = L / 100.0

    # Difference of Gaussians to extract wrinkle information
    sigma1 = 3   # captures fine wrinkles
    sigma2 = 25  # captures large fold structures

    blur_fine = cv2.GaussianBlur(L_norm, (0, 0), sigma1)
    blur_coarse = cv2.GaussianBlur(L_norm, (0, 0), sigma2)

    # DoG: fine detail (wrinkles) + mid-range (fold contours)
    dog = (blur_fine - blur_coarse)

    # Blend with base luminance for shadow cues
    disp_raw = dog * 0.7 + (L_norm - 0.5) * 0.3

    # Normalize to [0, 255] centered at 128
    disp_norm = cv2.normalize(disp_raw, None, 0, 255, cv2.NORM_MINMAX)
    disp_uint8 = disp_norm.astype(np.uint8)

    # Smooth the displacement field to avoid aliasing artifacts
    disp_smooth = cv2.GaussianBlur(disp_uint8, (7, 7), 2)

    return disp_smooth


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _load_image(path: str) -> np.ndarray | None:
    """Load image via OpenCV, return BGR array or None."""
    img = cv2.imread(str(path))
    if img is None:
        logger.error("cv2.imread failed for %s", path)
    return img


def _save_displacement_map(disp_map: np.ndarray, product_view_pk: int) -> str:
    """
    Save the displacement map PNG to media/products/disp_maps/ and return
    the path relative to MEDIA_ROOT.
    """
    rel_dir = Path("products") / "disp_maps"
    abs_dir = Path(settings.MEDIA_ROOT) / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)

    filename = f"disp_{product_view_pk}.png"
    abs_path = abs_dir / filename
    cv2.imwrite(str(abs_path), disp_map)

    return str(rel_dir / filename)
