from __future__ import annotations

import argparse
import io
import json
import math
import random
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps
import pymupdf


@dataclass
class DistortionConfig:
    """Configuration controlling visual scanner degradation and text perturbation."""

    # Photometric adjustments (brightness & contrast)
    brightness_min: float = 0.70
    brightness_max: float = 1.30
    contrast_min: float = 0.60
    contrast_max: float = 1.80
    prob_shadow: float = 0.45
    shadow_darkness: float = 0.35

    # Geometric & orientation distortions
    prob_flip_180: float = 0.20
    prob_rotate_90: float = 0.10
    prob_skew: float = 0.80
    max_skew_deg: float = 2.50

    # Sensor & physical paper artifacts
    prob_noise: float = 0.60
    noise_amount: float = 0.006
    prob_streaks: float = 0.25
    max_streaks: int = 2
    prob_blur: float = 0.35
    blur_radius: float = 0.75
    prob_paper_tint: float = 0.50
    prob_jpeg: float = 0.75
    jpeg_quality_min: int = 35
    jpeg_quality_max: int = 75

    # Rendering & Text layer preservation
    render_dpi: int = 150
    preserve_text_layer: bool = True
    prob_ocr_noise: float = 0.30
    ocr_error_rate: float = 0.02

    # Bad fit to page options (shrunk page with border from scanning/printing scaling)
    prob_bad_fit: float = 0.45
    bad_fit_scale_min: float = 0.72
    bad_fit_scale_max: float = 0.92
    bad_fit_offset_mode: str = "random"  # "random", "center", "top_left"
    bad_fit_border_style: str = "random"  # "random", "white", "scanner_gray", "paper_tint"
    bad_fit_edge_line: bool = True


# Common Polish OCR misrecognitions and character confusions
OCR_CONFUSIONS: dict[str, list[str]] = {
    "ą": ["a", "on", "an"],
    "ę": ["e", "en", "em"],
    "ł": ["l", "t", "1"],
    "Ł": ["L", "T"],
    "ó": ["o", "u"],
    "ś": ["s", "si"],
    "ć": ["c", "ci"],
    "ż": ["z", "zi"],
    "ź": ["z", "zi"],
    "ń": ["n", "ni"],
    "m": ["rn", "nn"],
    "cl": ["d"],
    "vv": ["w"],
    "0": ["O", "o"],
    "O": ["0"],
    "1": ["l", "I", "|"],
    "l": ["1", "I", "|"],
    "I": ["1", "l"],
    ":": [";", "."],
    ";": [":", ","],
    "-": ["—", "–"],
    ".": [","],
}


def adjust_brightness(image: Image.Image, factor: float) -> Image.Image:
    """Scale image luminance."""
    enhancer = ImageEnhance.Brightness(image)
    return enhancer.enhance(factor)


def adjust_contrast(image: Image.Image, factor: float) -> Image.Image:
    """Scale image contrast."""
    enhancer = ImageEnhance.Contrast(image)
    return enhancer.enhance(factor)


def apply_shadow_gradient(
    image: Image.Image,
    rng: random.Random,
    max_darkness: float = 0.35,
) -> Image.Image:
    """Simulate uneven scanner lid lighting or hand/phone shadow gradient."""
    width, height = image.size
    gradient = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(gradient)

    side = rng.choice(["top", "bottom", "left", "right", "corner"])
    steps = 100
    if side == "top":
        for i in range(steps):
            alpha = int(255 * (1.0 - max_darkness * (1.0 - i / steps)))
            y = int(height * 0.35 * (i / steps))
            draw.line([(0, y), (width, y)], fill=alpha)
    elif side == "bottom":
        for i in range(steps):
            alpha = int(255 * (1.0 - max_darkness * (i / steps)))
            y = int(height * 0.65 + height * 0.35 * (i / steps))
            draw.line([(0, y), (width, y)], fill=alpha)
    elif side == "left":
        for i in range(steps):
            alpha = int(255 * (1.0 - max_darkness * (1.0 - i / steps)))
            x = int(width * 0.30 * (i / steps))
            draw.line([(x, 0), (x, height)], fill=alpha)
    elif side == "right":
        for i in range(steps):
            alpha = int(255 * (1.0 - max_darkness * (i / steps)))
            x = int(width * 0.70 + width * 0.30 * (i / steps))
            draw.line([(x, 0), (x, height)], fill=alpha)
    else:  # corner
        diag_len = math.hypot(width * 0.4, height * 0.4)
        for i in range(steps):
            alpha = int(255 * (1.0 - max_darkness * (1.0 - i / steps)))
            r = int(diag_len * (i / steps))
            draw.ellipse([(-r, -r), (r, r)], outline=alpha)

    gradient = gradient.filter(ImageFilter.GaussianBlur(radius=width * 0.05))
    img_arr = np.array(image, dtype=np.float32)
    grad_arr = np.array(gradient, dtype=np.float32)[:, :, np.newaxis] / 255.0
    result = np.clip(img_arr * grad_arr, 0, 255).astype(np.uint8)
    return Image.fromarray(result)


def apply_skew(
    image: Image.Image,
    angle: float,
    fill_color: tuple[int, int, int] = (255, 255, 255),
) -> Image.Image:
    """Apply slight rotation simulating crooked sheet feeding in scanner ADF."""
    return image.rotate(
        angle,
        resample=Image.Resampling.BILINEAR,
        expand=False,
        fillcolor=fill_color,
    )


def apply_orientation(
    image: Image.Image,
    mode: str,
) -> Image.Image:
    """Rotate image by 180 (upside down) or 90/270 degrees."""
    if mode == "flip_180":
        return image.transpose(Image.Transpose.ROTATE_180)
    elif mode == "rot_90_cw":
        return image.transpose(Image.Transpose.ROTATE_270)
    elif mode == "rot_90_ccw":
        return image.transpose(Image.Transpose.ROTATE_90)
    return image


def add_salt_and_pepper_noise(
    image: Image.Image,
    amount: float,
    rng: random.Random,
) -> Image.Image:
    """Simulate dust particles, toner specks, and dirty scanner glass."""
    arr = np.array(image)
    total_pixels = arr.shape[0] * arr.shape[1]
    num_noise = int(total_pixels * amount)

    # Dark specks (dust, toner spray)
    ys_dark = [rng.randint(0, arr.shape[0] - 1) for _ in range(num_noise // 2)]
    xs_dark = [rng.randint(0, arr.shape[1] - 1) for _ in range(num_noise // 2)]
    dark_vals = np.array([rng.randint(20, 90) for _ in range(len(ys_dark))], dtype=np.uint8)
    for y, x, val in zip(ys_dark, xs_dark, dark_vals):
        arr[y, x] = val

    # Light specks (sensor dropouts)
    ys_light = [rng.randint(0, arr.shape[0] - 1) for _ in range(num_noise // 2)]
    xs_light = [rng.randint(0, arr.shape[1] - 1) for _ in range(num_noise // 2)]
    for y, x in zip(ys_light, xs_light):
        arr[y, x] = 250

    return Image.fromarray(arr)


def add_scanner_streaks(
    image: Image.Image,
    num_streaks: int,
    rng: random.Random,
) -> Image.Image:
    """Simulate vertical streaks caused by dust on scanner slit glass during ADF feed."""
    arr = np.array(image, dtype=np.float32)
    height, width = arr.shape[:2]

    for _ in range(num_streaks):
        x = rng.randint(int(width * 0.05), int(width * 0.95))
        streak_width = rng.randint(1, 3)
        darkness = rng.uniform(0.70, 0.90)
        x_end = min(width, x + streak_width)
        arr[:, x:x_end] *= darkness

    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def apply_paper_tint(
    image: Image.Image,
    rng: random.Random,
) -> Image.Image:
    """Blend faint warm or recycled paper background tint."""
    tints = [
        (250, 248, 240),  # warm off-white
        (245, 245, 240),  # cream
        (240, 242, 245),  # light cool gray
        (248, 244, 235),  # aged document
    ]
    tint = rng.choice(tints)
    tint_layer = Image.new("RGB", image.size, color=tint)
    return Image.blend(image, tint_layer, alpha=0.15)


def apply_jpeg_compression(
    image: Image.Image,
    quality: int,
) -> Image.Image:
    """Simulate scanner internal firmware JPEG compression artifacts."""
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    return Image.open(buffer).copy()


def apply_bad_fit_to_page(
    image: Image.Image,
    scale: float,
    offset_mode: str,
    border_style: str,
    add_edge_line: bool,
    rng: random.Random,
) -> tuple[Image.Image, dict[str, Any]]:
    """
    Simulate poorly adjusted print/scan sizing ('fit to page' double scaling).
    Scales down the page content and surrounds it with a wide border margin.
    """
    orig_w, orig_h = image.size
    new_w = max(10, int(orig_w * scale))
    new_h = max(10, int(orig_h * scale))

    shrunk_img = image.resize((new_w, new_h), resample=Image.Resampling.BILINEAR)

    max_dx = max(0, orig_w - new_w)
    max_dy = max(0, orig_h - new_h)

    if offset_mode == "center":
        dx = max_dx // 2
        dy = max_dy // 2
    elif offset_mode == "top_left":
        dx = int(max_dx * rng.uniform(0.1, 0.3))
        dy = int(max_dy * rng.uniform(0.1, 0.3))
    else:  # "random" / asymmetric margins
        dx = int(max_dx * rng.uniform(0.15, 0.85)) if max_dx > 0 else 0
        dy = int(max_dy * rng.uniform(0.15, 0.85)) if max_dy > 0 else 0

    # Border color selection (simulating white margins, scanner bed gray, or cream paper)
    if border_style == "white":
        border_color = (255, 255, 255)
    elif border_style == "scanner_gray":
        val = rng.randint(225, 240)
        border_color = (val, val, val)
    elif border_style == "paper_tint":
        border_color = rng.choice([
            (250, 248, 242),
            (246, 245, 240),
            (242, 240, 235),
        ])
    else:  # "random"
        choice = rng.choice(["white", "scanner_gray", "paper_tint"])
        if choice == "white":
            border_color = (255, 255, 255)
        elif choice == "scanner_gray":
            val = rng.randint(225, 240)
            border_color = (val, val, val)
        else:
            border_color = rng.choice([
                (250, 248, 242),
                (246, 245, 240),
                (242, 240, 235),
            ])

    canvas = Image.new("RGB", (orig_w, orig_h), color=border_color)

    # Draw faint edge line / shadow around the shrunk page simulating physical photocopy / scanner edge
    if add_edge_line:
        draw = ImageDraw.Draw(canvas)
        edge_col = (
            max(0, border_color[0] - 30),
            max(0, border_color[1] - 30),
            max(0, border_color[2] - 30),
        )
        draw.rectangle([dx - 1, dy - 1, dx + new_w, dy + new_h], outline=edge_col, width=1)

    canvas.paste(shrunk_img, (dx, dy))

    return canvas, {
        "scale": scale,
        "dx_ratio": (dx / orig_w) if orig_w > 0 else 0.0,
        "dy_ratio": (dy / orig_h) if orig_h > 0 else 0.0,
        "border_color": border_color,
        "offset_mode": offset_mode,
        "border_style": border_style,
    }


def inject_ocr_noise(
    text: str,
    error_rate: float,
    rng: random.Random,
) -> str:
    """Introduce realistic OCR transcription errors into text strings."""
    if not text or error_rate <= 0:
        return text

    chars = list(text)
    result = []
    i = 0
    while i < len(chars):
        char = chars[i]
        # Check two-character substitutions
        two_char = "".join(chars[i : i + 2])
        if two_char in OCR_CONFUSIONS and rng.random() < error_rate * 2:
            replacement = rng.choice(OCR_CONFUSIONS[two_char])
            result.append(replacement)
            i += 2
            continue

        if char in OCR_CONFUSIONS and rng.random() < error_rate:
            replacement = rng.choice(OCR_CONFUSIONS[char])
            result.append(replacement)
        elif rng.random() < (error_rate * 0.2):
            # Rare character drop
            pass
        else:
            result.append(char)
        i += 1

    return "".join(result)


def augment_page(
    page: pymupdf.Page,
    config: DistortionConfig,
    rng: random.Random,
) -> tuple[Image.Image, dict[str, Any]]:
    """Render and apply all configured scanner degradations to a single PDF page."""
    pix = page.get_pixmap(dpi=config.render_dpi)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    metadata: dict[str, Any] = {}

    # 0. Bad fit to page (shrink content with border around it from scanning/printing)
    if rng.random() < config.prob_bad_fit:
        scale = rng.uniform(config.bad_fit_scale_min, config.bad_fit_scale_max)
        img, bf_meta = apply_bad_fit_to_page(
            img,
            scale=scale,
            offset_mode=config.bad_fit_offset_mode,
            border_style=config.bad_fit_border_style,
            add_edge_line=config.bad_fit_edge_line,
            rng=rng,
        )
        metadata["bad_fit"] = {
            "scale": round(bf_meta["scale"], 3),
            "dx_ratio": round(bf_meta["dx_ratio"], 4),
            "dy_ratio": round(bf_meta["dy_ratio"], 4),
            "offset_mode": bf_meta["offset_mode"],
            "border_style": bf_meta["border_style"],
        }

    # 1. Orientation & Flipping
    orientation_mode = "normal"
    if rng.random() < config.prob_flip_180:
        orientation_mode = "flip_180"
    elif rng.random() < config.prob_rotate_90:
        orientation_mode = rng.choice(["rot_90_cw", "rot_90_ccw"])

    if orientation_mode != "normal":
        img = apply_orientation(img, orientation_mode)
    metadata["orientation"] = orientation_mode

    # 2. Skew / Crooked feed
    skew_angle = 0.0
    if rng.random() < config.prob_skew:
        skew_angle = rng.uniform(-config.max_skew_deg, config.max_skew_deg)
        img = apply_skew(img, skew_angle)
    metadata["skew_angle"] = round(skew_angle, 2)

    # 3. Brightness & Contrast
    brightness_factor = rng.uniform(config.brightness_min, config.brightness_max)
    contrast_factor = rng.uniform(config.contrast_min, config.contrast_max)
    img = adjust_brightness(img, brightness_factor)
    img = adjust_contrast(img, contrast_factor)
    metadata["brightness"] = round(brightness_factor, 2)
    metadata["contrast"] = round(contrast_factor, 2)

    # 4. Shadow Gradient
    if rng.random() < config.prob_shadow:
        img = apply_shadow_gradient(img, rng, max_darkness=config.shadow_darkness)
        metadata["shadow"] = True

    # 5. Paper Tint
    if rng.random() < config.prob_paper_tint:
        img = apply_paper_tint(img, rng)
        metadata["paper_tint"] = True

    # 6. Salt-and-pepper / Dust
    if rng.random() < config.prob_noise:
        img = add_salt_and_pepper_noise(img, config.noise_amount, rng)
        metadata["noise"] = True

    # 7. Scanner vertical streaks
    if rng.random() < config.prob_streaks:
        num_streaks = rng.randint(1, config.max_streaks)
        img = add_scanner_streaks(img, num_streaks, rng)
        metadata["streaks"] = num_streaks

    # 8. Blur / Defocus
    if rng.random() < config.prob_blur:
        img = img.filter(ImageFilter.GaussianBlur(radius=config.blur_radius))
        metadata["blur"] = True

    # 9. JPEG Compression Artifacts
    if rng.random() < config.prob_jpeg:
        quality = rng.randint(config.jpeg_quality_min, config.jpeg_quality_max)
        img = apply_jpeg_compression(img, quality)
        metadata["jpeg_quality"] = quality

    return img, metadata


def get_unicode_font_path() -> str | None:
    """Find a system font that supports full Polish unicode diacritics."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    return None


def augment_pdf(
    input_pdf_path: Path,
    output_pdf_path: Path,
    config: DistortionConfig | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """
    Augment a PDF document by converting its pages to distorted scanner images
    and compiling them back into a valid PDF, preserving searchable text layer.
    """
    if config is None:
        config = DistortionConfig()

    rng = random.Random(seed)
    input_pdf_path = Path(input_pdf_path)
    output_pdf_path = Path(output_pdf_path)

    if not input_pdf_path.is_file():
        raise FileNotFoundError(f"Source PDF does not exist: {input_pdf_path}")

    output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
    unicode_font = get_unicode_font_path()

    with pymupdf.open(input_pdf_path) as src_doc:
        new_doc = pymupdf.open()
        pages_metadata = []

        for page_idx in range(len(src_doc)):
            src_page = src_doc[page_idx]
            page_rect = src_page.rect

            # Degrade page image
            degraded_img, page_meta = augment_page(src_page, config, rng)
            pages_metadata.append(page_meta)

            # Convert degraded image to JPEG bytes
            img_buffer = io.BytesIO()
            degraded_img.save(img_buffer, format="JPEG", quality=85)
            img_bytes = img_buffer.getvalue()

            # Determine new page dimensions based on orientation
            orientation = page_meta.get("orientation", "normal")
            if orientation in ("rot_90_cw", "rot_90_ccw"):
                new_width, new_height = page_rect.height, page_rect.width
            else:
                new_width, new_height = page_rect.width, page_rect.height

            new_page = new_doc.new_page(width=new_width, height=new_height)
            target_rect = pymupdf.Rect(0, 0, new_width, new_height)

            # Insert degraded image as page background
            new_page.insert_image(target_rect, stream=img_bytes)

            # Embed searchable text layer if requested
            if config.preserve_text_layer:
                fontname = None
                if unicode_font:
                    try:
                        new_page.insert_font(fontname="unicode_font", fontfile=unicode_font)
                        fontname = "unicode_font"
                    except Exception:
                        fontname = None

                blocks = src_page.get_text("blocks")
                apply_ocr_noise = rng.random() < config.prob_ocr_noise

                for block in blocks:
                    # block: (x0, y0, x1, y1, text, block_no, block_type)
                    if block[6] != 0:  # text block
                        continue
                    x0, y0, x1, y1, block_text = block[0], block[1], block[2], block[3], block[4]
                    if not block_text.strip():
                        continue

                    if apply_ocr_noise:
                        block_text = inject_ocr_noise(
                            block_text, config.ocr_error_rate, rng
                        )

                    base_fontsize = 9
                    if "bad_fit" in page_meta:
                        bf = page_meta["bad_fit"]
                        scale = bf["scale"]
                        dx = page_rect.width * bf["dx_ratio"]
                        dy = page_rect.height * bf["dy_ratio"]
                        x0 = dx + x0 * scale
                        y0 = dy + y0 * scale
                        x1 = dx + x1 * scale
                        y1 = dy + y1 * scale
                        base_fontsize = max(6, int(round(9 * scale)))

                    # Transform bounding box if flipped or rotated
                    if orientation == "flip_180":
                        bx0 = page_rect.width - x1
                        by0 = page_rect.height - y1
                        bx1 = page_rect.width - x0
                        by1 = page_rect.height - y0
                        text_rect = pymupdf.Rect(bx0, by0, bx1, by1)
                    elif orientation == "rot_90_cw":
                        bx0 = page_rect.height - y1
                        by0 = x0
                        bx1 = page_rect.height - y0
                        by1 = x1
                        text_rect = pymupdf.Rect(bx0, by0, bx1, by1)
                    elif orientation == "rot_90_ccw":
                        bx0 = y0
                        by0 = page_rect.width - x1
                        bx1 = y1
                        by1 = page_rect.width - x0
                        text_rect = pymupdf.Rect(bx0, by0, bx1, by1)
                    else:
                        text_rect = pymupdf.Rect(x0, y0, x1, y1)

                    # render_mode=3 corresponds to invisible text (searchable text layer)
                    text_kwargs = {"render_mode": 3, "fontsize": base_fontsize}
                    if fontname:
                        text_kwargs["fontname"] = fontname

                    # Use insert_text at baseline to avoid bounding-box clipping failures
                    point = (
                        max(0, min(new_width - 20, text_rect.x0)),
                        max(10, min(new_height - 10, text_rect.y0 + base_fontsize)),
                    )
                    try:
                        new_page.insert_text(
                            point,
                            block_text,
                            **text_kwargs,
                        )
                    except Exception:
                        pass

        new_doc.save(output_pdf_path)
        new_doc.close()

    return {
        "input_pdf": str(input_pdf_path),
        "output_pdf": str(output_pdf_path),
        "pages": pages_metadata,
    }


def augment_case(
    case_dir: Path,
    output_case_dir: Path,
    config: DistortionConfig | None = None,
    suffix: str = "_aug1",
    seed: int | None = None,
) -> list[Path]:
    """
    Augment an entire case directory, preserving JSON labels and directory structure.
    """
    if config is None:
        config = DistortionConfig()

    case_dir = Path(case_dir)
    output_case_dir = Path(output_case_dir)
    output_case_dir.mkdir(parents=True, exist_ok=True)

    created_files: list[Path] = []
    case_seed = seed if seed is not None else random.randint(0, 1_000_000)

    # Copy / augment PDF and JSON pairs
    pdf_files = sorted(case_dir.glob("*.pdf"))
    for idx, pdf_path in enumerate(pdf_files):
        out_pdf_path = output_case_dir / pdf_path.name
        augment_pdf(pdf_path, out_pdf_path, config=config, seed=case_seed + idx * 31)
        created_files.append(out_pdf_path)

    # Copy all matching JSON files to output case folder
    for json_path in case_dir.glob("*.json"):
        out_json_path = output_case_dir / json_path.name
        shutil.copy2(json_path, out_json_path)
        created_files.append(out_json_path)

    return created_files


def augment_dataset(
    input_dir: Path,
    output_dir: Path,
    num_variants: int = 1,
    config: DistortionConfig | None = None,
    include_originals: bool = True,
    seed: int = 42,
) -> dict[str, int]:
    """
    Augment all cases in a dataset directory to increase training set size.
    """
    if config is None:
        config = DistortionConfig()

    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    case_dirs = sorted(p for p in input_dir.iterdir() if p.is_dir())
    if not case_dirs:
        raise ValueError(f"No case subdirectories found in: {input_dir}")

    stats = {"cases_original": len(case_dirs), "cases_augmented": 0, "total_cases": 0}

    for case_dir in case_dirs:
        # Copy original if requested
        if include_originals:
            dest_orig = output_dir / case_dir.name
            if not dest_orig.exists():
                shutil.copytree(case_dir, dest_orig)

        # Generate augmented variants
        for variant_idx in range(1, num_variants + 1):
            variant_name = f"{case_dir.name}_aug{variant_idx}"
            dest_variant = output_dir / variant_name
            variant_seed = seed + hash(case_dir.name) % 10000 + variant_idx * 1337
            augment_case(case_dir, dest_variant, config=config, seed=variant_seed)
            stats["cases_augmented"] += 1

    stats["total_cases"] = len(list(output_dir.iterdir()))
    return stats


def get_preset_config(preset: str) -> DistortionConfig:
    """Return preset distortion configurations."""
    if preset == "mild":
        return DistortionConfig(
            brightness_min=0.85,
            brightness_max=1.15,
            contrast_min=0.80,
            contrast_max=1.30,
            prob_shadow=0.20,
            prob_flip_180=0.05,
            prob_rotate_90=0.02,
            prob_skew=0.50,
            max_skew_deg=1.2,
            prob_noise=0.30,
            prob_streaks=0.10,
            prob_blur=0.15,
            prob_paper_tint=0.30,
            prob_ocr_noise=0.10,
            prob_bad_fit=0.25,
            bad_fit_scale_min=0.85,
            bad_fit_scale_max=0.95,
        )
    elif preset == "severe":
        return DistortionConfig(
            brightness_min=0.55,
            brightness_max=1.45,
            contrast_min=0.45,
            contrast_max=2.20,
            prob_shadow=0.60,
            shadow_darkness=0.50,
            prob_flip_180=0.35,
            prob_rotate_90=0.20,
            prob_skew=0.95,
            max_skew_deg=4.0,
            prob_noise=0.80,
            noise_amount=0.012,
            prob_streaks=0.40,
            max_streaks=3,
            prob_blur=0.50,
            blur_radius=1.2,
            prob_paper_tint=0.75,
            prob_ocr_noise=0.50,
            ocr_error_rate=0.04,
            prob_bad_fit=0.70,
            bad_fit_scale_min=0.65,
            bad_fit_scale_max=0.85,
        )
    # Default: "realistic"
    return DistortionConfig()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Data augmentation tool for scanned document PDFs (UZP Odwołania2JSON)."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input-file", type=Path, help="Single PDF file to augment.")
    group.add_argument("--case-dir", type=Path, help="Single case folder to augment.")
    group.add_argument("--dataset-dir", type=Path, help="Directory containing multiple case folders.")

    parser.add_argument("--output", type=Path, help="Output destination (file or directory).")
    parser.add_argument("--output-dir", type=Path, help="Output directory for case or dataset augmentation.")
    parser.add_argument(
        "--preset",
        choices=["mild", "realistic", "severe"],
        default="realistic",
        help="Distortion preset (default: realistic).",
    )
    parser.add_argument(
        "--copies",
        type=int,
        default=1,
        help="Number of augmented copies per case (default: 1).",
    )
    parser.add_argument("--dpi", type=int, default=150, help="Rendering resolution (DPI).")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility.")
    parser.add_argument(
        "--no-text-layer",
        action="store_true",
        help="Do not embed searchable text layer (image-only scanned PDF).",
    )

    # Bad fit to page options
    parser.add_argument(
        "--bad-fit",
        action="store_true",
        help="Force bad-fit-to-page scaling on all pages (prob_bad_fit=1.0).",
    )
    parser.add_argument(
        "--no-bad-fit",
        action="store_true",
        help="Disable bad-fit-to-page scaling (prob_bad_fit=0.0).",
    )
    parser.add_argument(
        "--prob-bad-fit",
        type=float,
        default=None,
        help="Probability of applying bad fit to page (0.0 to 1.0).",
    )
    parser.add_argument(
        "--bad-fit-scale-min",
        type=float,
        default=None,
        help="Minimum scale factor for bad fit (e.g. 0.70).",
    )
    parser.add_argument(
        "--bad-fit-scale-max",
        type=float,
        default=None,
        help="Maximum scale factor for bad fit (e.g. 0.92).",
    )
    parser.add_argument(
        "--bad-fit-border",
        choices=["random", "white", "scanner_gray", "paper_tint"],
        default=None,
        help="Border style for bad fit (default: random).",
    )
    parser.add_argument(
        "--bad-fit-offset",
        choices=["random", "center", "top_left"],
        default=None,
        help="Offset positioning for bad fit (default: random).",
    )

    args = parser.parse_args()
    config = get_preset_config(args.preset)
    config.render_dpi = args.dpi
    if args.no_text_layer:
        config.preserve_text_layer = False

    # Apply bad fit overrides if specified
    if args.bad_fit:
        config.prob_bad_fit = 1.0
    elif args.no_bad_fit:
        config.prob_bad_fit = 0.0
    elif args.prob_bad_fit is not None:
        config.prob_bad_fit = args.prob_bad_fit

    if args.bad_fit_scale_min is not None:
        config.bad_fit_scale_min = args.bad_fit_scale_min
    if args.bad_fit_scale_max is not None:
        config.bad_fit_scale_max = args.bad_fit_scale_max
    if args.bad_fit_border is not None:
        config.bad_fit_border_style = args.bad_fit_border
    if args.bad_fit_offset is not None:
        config.bad_fit_offset_mode = args.bad_fit_offset
        config.preserve_text_layer = False

    if args.input_file:
        out_path = args.output or args.input_file.with_name(f"{args.input_file.stem}_distorted.pdf")
        meta = augment_pdf(args.input_file, out_path, config=config, seed=args.seed)
        print(f"Augmented PDF written to: {out_path}")
        print(f"Applied distortions: {json.dumps(meta['pages'], indent=2)}")

    elif args.case_dir:
        out_dir = args.output_dir or args.case_dir.with_name(f"{args.case_dir.name}_aug1")
        created = augment_case(args.case_dir, out_dir, config=config, seed=args.seed)
        print(f"Augmented case written to: {out_dir} ({len(created)} files created)")

    elif args.dataset_dir:
        out_dir = args.output_dir or args.dataset_dir.parent / "raw_augmented"
        stats = augment_dataset(
            args.dataset_dir,
            out_dir,
            num_variants=args.copies,
            config=config,
            seed=args.seed,
        )
        print(f"Dataset augmentation complete: {stats}")
        print(f"Output directory: {out_dir}")


if __name__ == "__main__":
    main()
