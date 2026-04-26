"""
rendering/compositor.py
───────────────────────
Core image compositing pipeline.

Pipeline per render:
  1. Load base image (product photo) and design (user upload, RGBA)
  2. Resize design to fit print area, adding transparent padding
  3. Perspective warp design using stored homography matrix
  4. Displacement warp to bend design along fabric folds
  5. Multiply blend → fabric texture/shadows show through design
  6. Soft-light luminance pass → final lighting integration
  7. Composite back onto full-size base image
"""

import logging
from pathlib import Path

import cv2
import numpy as np
from django.conf import settings

logger = logging.getLogger(__name__)

RENDERING_CFG = getattr(settings, "RENDERING", {})
DISP_SCALE = RENDERING_CFG.get("DISPLACEMENT_SCALE", 14)
LIGHTING_ALPHA = RENDERING_CFG.get("LIGHTING_BLEND_ALPHA", 0.38)
PREVIEW_SCALE = RENDERING_CFG.get("PREVIEW_SCALE", 0.5)

# Project-level media directory (where product images ship with the codebase)
_PROJECT_MEDIA = Path(settings.BASE_DIR) / "media"


def _resolve_media_path(field_path: str) -> str:
    """
    Resolve a Django FileField .path to an actual readable file.

    On Vercel/serverless, MEDIA_ROOT is /tmp/media (writable but empty on cold
    start).  Product base images and displacement maps actually live in the
    project's media/ directory.  This helper checks MEDIA_ROOT first, then
    falls back to the in-project media directory.
    """
    p = Path(field_path)
    if p.is_file():
        return str(p)

    # Try the project's bundled media directory instead
    # field_path is usually <MEDIA_ROOT>/<relative>, so strip the MEDIA_ROOT prefix
    try:
        rel = p.relative_to(settings.MEDIA_ROOT)
    except ValueError:
        # Not under MEDIA_ROOT — just return as-is
        return str(p)

    fallback = _PROJECT_MEDIA / rel
    if fallback.is_file():
        logger.debug("Resolved media fallback: %s → %s", p, fallback)
        return str(fallback)

    # Neither location has the file — return the original and let the caller error
    return str(p)


# ──────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────

def render(product_view, design_path: str, output_path: str, opacity: float = 1.0) -> str:
    """
    Composite a design onto a product base image.

    Args:
        product_view: ProductView model instance (must have analysis_status='done')
        design_path:  Absolute path to the user's uploaded design image
        output_path:  Absolute path where the result PNG should be saved
        opacity:      Design layer opacity (0.0–1.0)

    Returns:
        output_path (str) on success.

    Raises:
        RuntimeError on any unrecoverable error.
    """
    # 1. Load images
    base_bgr = _load_bgr(_resolve_media_path(product_view.base_image.path))
    design_rgba = _load_rgba(design_path)

    H_base, W_base = base_bgr.shape[:2]

    # 2. Resize design to fit print area
    pw, ph = product_view.print_area_w, product_view.print_area_h
    design_resized = _resize_design_to_print_area(design_rgba, pw, ph)

    # 3. Perspective warp design onto full canvas
    matrix = np.array(product_view.perspective_matrix, dtype=np.float64)
    design_warped = _perspective_warp(design_resized, matrix, W_base, H_base)

    # 4. Displacement warp (fabric conformation)
    if product_view.displacement_map:
        disp_map = _load_gray(_resolve_media_path(product_view.displacement_map.path))
    else:
        disp_map = None

    design_displaced = _apply_displacement(design_warped, disp_map, DISP_SCALE)

    # 5. Extract design's own alpha channel pre-displacement (kept separate)
    design_alpha = design_displaced[:, :, 3].astype(np.float32) / 255.0
    design_alpha *= opacity  # apply user-defined opacity

    design_rgb = design_displaced[:, :, :3].astype(np.float32)

    # 6. Multiply blend — fabric texture penetrates through design
    base_float = base_bgr.astype(np.float32)
    multiplied = _multiply_blend(design_rgb, base_float)

    # 7. Soft-light luminance pass — reintegrate lighting from base image
    result_float = _soft_light_pass(multiplied, base_float, LIGHTING_ALPHA)

    # 8. Composite design over base using alpha mask
    result = _alpha_composite(base_float, result_float, design_alpha)

    # 9. Save output
    result_uint8 = np.clip(result, 0, 255).astype(np.uint8)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    success = cv2.imwrite(str(output_path), result_uint8)
    if not success:
        raise RuntimeError(f"cv2.imwrite failed for {output_path}")

    logger.info("Render complete → %s", output_path)
    return output_path


def render_preview(product_view, design_path: str, output_path: str, opacity: float = 1.0) -> str:
    """
    Synchronous fast preview at PREVIEW_SCALE resolution.
    Skips displacement warp for speed.
    """
    base_bgr = _load_bgr(_resolve_media_path(product_view.base_image.path))
    design_rgba = _load_rgba(design_path)

    H_base, W_base = base_bgr.shape[:2]
    scale = PREVIEW_SCALE
    base_bgr = cv2.resize(base_bgr, (int(W_base * scale), int(H_base * scale)))
    H_base, W_base = base_bgr.shape[:2]

    # Scale the print area coordinates
    pw = int(product_view.print_area_w * scale)
    ph = int(product_view.print_area_h * scale)

    # Scale the homography matrix
    S = np.diag([scale, scale, 1.0])
    matrix = S @ np.array(product_view.perspective_matrix, dtype=np.float64)

    design_resized = _resize_design_to_print_area(design_rgba, pw, ph)
    design_warped = _perspective_warp(design_resized, matrix, W_base, H_base)

    design_alpha = design_warped[:, :, 3].astype(np.float32) / 255.0 * opacity
    design_rgb = design_warped[:, :, :3].astype(np.float32)
    base_float = base_bgr.astype(np.float32)

    multiplied = _multiply_blend(design_rgb, base_float)
    result_float = _soft_light_pass(multiplied, base_float, LIGHTING_ALPHA * 0.8)
    result = _alpha_composite(base_float, result_float, design_alpha)

    result_uint8 = np.clip(result, 0, 255).astype(np.uint8)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), result_uint8)
    return output_path


# ──────────────────────────────────────────────
# Step 2 — Resize design to print area
# ──────────────────────────────────────────────

def _resize_design_to_print_area(design_rgba: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    """
    Resize design (RGBA) to fit inside target_w × target_h, maintaining aspect ratio.
    Adds transparent padding to reach exact target dimensions.
    """
    dh, dw = design_rgba.shape[:2]
    scale = min(target_w / dw, target_h / dh)
    new_w = int(dw * scale)
    new_h = int(dh * scale)

    resized = cv2.resize(design_rgba, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

    # Pad to exact target size with transparent pixels
    canvas = np.zeros((target_h, target_w, 4), dtype=np.uint8)
    x_off = (target_w - new_w) // 2
    y_off = (target_h - new_h) // 2
    canvas[y_off:y_off + new_h, x_off:x_off + new_w] = resized

    return canvas


# ──────────────────────────────────────────────
# Step 3 — Perspective Warp
# ──────────────────────────────────────────────

def _perspective_warp(
    design_rgba: np.ndarray, matrix: np.ndarray, canvas_w: int, canvas_h: int
) -> np.ndarray:
    """
    Apply homography to warp design_rgba onto a canvas of size (canvas_w, canvas_h).
    Preserves RGBA channels (warped separately for accuracy).
    """
    flags = cv2.INTER_LANCZOS4
    border = cv2.BORDER_CONSTANT

    rgb = cv2.warpPerspective(design_rgba[:, :, :3], matrix, (canvas_w, canvas_h), flags=flags, borderMode=border)
    alpha = cv2.warpPerspective(design_rgba[:, :, 3], matrix, (canvas_w, canvas_h), flags=flags, borderMode=border)

    result = np.dstack([rgb, alpha])
    return result


# ──────────────────────────────────────────────
# Step 4 — Displacement Warp
# ──────────────────────────────────────────────

def _apply_displacement(
    design_rgba: np.ndarray, disp_map: np.ndarray | None, scale: float
) -> np.ndarray:
    """
    Warp design pixels using the displacement map to simulate fabric folds.

    disp_map: grayscale uint8 centered at 128
      > 128 → shift right/down
      < 128 → shift left/up
    """
    if disp_map is None:
        return design_rgba

    H, W = design_rgba.shape[:2]

    # Resize displacement map to match the canvas
    if disp_map.shape[:2] != (H, W):
        disp_map = cv2.resize(disp_map, (W, H), interpolation=cv2.INTER_LINEAR)

    # Build base coordinate grids
    grid_x, grid_y = np.meshgrid(np.arange(W), np.arange(H))

    # Displacement field: normalized [-1, 1] then scaled to pixels
    flow = (disp_map.astype(np.float32) - 128.0) / 128.0  # [-1, 1]
    flow_x = flow * scale          # horizontal warp magnitude
    flow_y = flow * scale * 0.6    # vertical warp (less — fabric folds mostly horizontally)

    map_x = (grid_x + flow_x).astype(np.float32)
    map_y = (grid_y + flow_y).astype(np.float32)

    # Remap each channel
    channels = []
    for c in range(4):  # RGBA
        warped_c = cv2.remap(
            design_rgba[:, :, c],
            map_x, map_y,
            interpolation=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
        channels.append(warped_c)

    return np.dstack(channels)


# ──────────────────────────────────────────────
# Step 5 — Multiply Blend
# ──────────────────────────────────────────────

def _multiply_blend(design_rgb: np.ndarray, base_rgb: np.ndarray) -> np.ndarray:
    """
    Photoshop-style Multiply blend: result = design × base / 255.
    This makes the fabric texture and shadows penetrate through the design.
    Both inputs are float32 arrays in [0, 255].
    """
    multiplied = (design_rgb * base_rgb) / 255.0
    return multiplied


# ──────────────────────────────────────────────
# Step 6 — Soft-Light Luminance Pass
# ──────────────────────────────────────────────

def _soft_light_pass(
    design_float: np.ndarray, base_float: np.ndarray, alpha: float
) -> np.ndarray:
    """
    Blend the lighting from the base image back onto the composited design
    using a soft-light formula, controlled by alpha (0.0 = skip, 1.0 = full).

    Soft-light formula (Pegtop / W3C):
      if base <= 128:  result = design - (255 - 2*base) * design * (255 - design) / 255²
      else:            result = design + (2*base - 255) * (D - design*D/255) / 255
    where D = sqrt(design/255)*255
    """
    if alpha <= 0:
        return design_float

    d = design_float / 255.0  # [0,1]
    b = base_float / 255.0    # [0,1]

    # W3C soft-light formula
    D_sqrt = np.sqrt(d)
    mask_low = b <= 0.5
    soft = np.where(
        mask_low,
        d - (1 - 2 * b) * d * (1 - d),
        d + (2 * b - 1) * (D_sqrt - d),
    )
    soft = np.clip(soft, 0, 1) * 255.0

    # Blend between multiply result and soft-light result
    result = design_float * (1 - alpha) + soft * alpha
    return result


# ──────────────────────────────────────────────
# Step 7 — Alpha Composite
# ──────────────────────────────────────────────

def _alpha_composite(
    base_float: np.ndarray, design_float: np.ndarray, alpha_mask: np.ndarray
) -> np.ndarray:
    """
    Porter-Duff over composite: result = design × α + base × (1 − α)
    alpha_mask: (H, W) float32 in [0, 1]
    """
    # Expand alpha to 3 channels
    alpha_3 = alpha_mask[:, :, np.newaxis]
    result = design_float * alpha_3 + base_float * (1 - alpha_3)
    return result


# ──────────────────────────────────────────────
# Image loaders
# ──────────────────────────────────────────────

def _load_bgr(path: str) -> np.ndarray:
    img = cv2.imread(str(path))
    if img is None:
        raise RuntimeError(f"Cannot load image: {path}")
    return img


def _load_rgba(path: str) -> np.ndarray:
    """Load image as RGBA (converts if necessary)."""
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise RuntimeError(f"Cannot load design image: {path}")
    if img.ndim == 2:
        # Grayscale → RGBA
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    elif img.shape[2] == 3:
        # BGR → BGRA (add opaque alpha)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    return img


def _load_gray(path: str) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise RuntimeError(f"Cannot load grayscale image: {path}")
    return img
