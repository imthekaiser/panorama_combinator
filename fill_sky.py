#!/usr/bin/env python3
import os
import sys
from pathlib import Path

import cv2
import numpy as np


def getenv_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def copy_image(input_path, output_path, message):
    print(message)
    img = cv2.imread(str(input_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise SystemExit(f"Could not read image: {input_path}")

    # Always write 3-channel output to avoid TIFF/alpha/ExtraSamples issues later.
    if len(img.shape) == 2:
        out = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:
        out = img[:, :, :3]
    else:
        out = img[:, :, :3]

    if not cv2.imwrite(str(output_path), out):
        raise SystemExit(f"Failed to write image: {output_path}")


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: fill_sky.py <input_image> <output_image>")

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    black_threshold = getenv_int("SKYFILL_BLACK_THRESHOLD", 10)
    min_missing_px = getenv_int("SKYFILL_MIN_MISSING_PX", 20)
    max_missing_percent = getenv_int("SKYFILL_MAX_MISSING_PERCENT", 40)
    min_sample_brightness = getenv_int("SKYFILL_MIN_SAMPLE_BRIGHTNESS", 18)

    img = cv2.imread(str(input_path), cv2.IMREAD_UNCHANGED)

    if img is None:
        raise SystemExit(f"Could not read image: {input_path}")

    if len(img.shape) == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

    has_alpha = len(img.shape) == 3 and img.shape[2] == 4

    if has_alpha:
        bgr = img[:, :, :3]
        alpha = img[:, :, 3]
    else:
        bgr = img[:, :, :3]
        alpha = None

    # Convert to 8-bit for detection/final JPEG pipeline.
    if bgr.dtype == np.uint16:
        bgr8 = np.clip(bgr / 257, 0, 255).astype(np.uint8)
    elif bgr.dtype == np.float32 or bgr.dtype == np.float64:
        bgr8 = np.clip(bgr, 0, 255).astype(np.uint8)
    else:
        bgr8 = bgr.astype(np.uint8)

    h, w = bgr8.shape[:2]

    brightness = np.mean(bgr8, axis=2)
    max_channel = np.max(bgr8, axis=2)
    channel_std = np.std(bgr8.astype(np.float32), axis=2)

    # Candidate missing pixels:
    # - transparent pixels, if alpha exists
    # - or nearly pure black, flat pixels
    near_black = (max_channel <= black_threshold) & (channel_std <= 4.0)

    if has_alpha:
        alpha_missing = alpha < 10
        candidate = alpha_missing | near_black
        alpha_based_missing = np.any(alpha_missing[0, :])
    else:
        candidate = near_black
        alpha_based_missing = False

    # Only fill pixels connected to the top border.
    # This avoids changing black objects/ground/lights lower in the image.
    num_labels, labels = cv2.connectedComponents(candidate.astype(np.uint8), connectivity=8)

    top_labels = np.unique(labels[0, :])
    top_labels = top_labels[top_labels != 0]

    if len(top_labels) == 0:
        copy_image(input_path, output_path, "No top-connected missing sky detected. Copying image.")
        return

    missing_mask = np.isin(labels, top_labels)

    ys = np.where(missing_mask)[0]
    if len(ys) == 0:
        copy_image(input_path, output_path, "No missing sky pixels found. Copying image.")
        return

    missing_height = int(ys.max()) + 1
    missing_pixels = int(np.count_nonzero(missing_mask))
    missing_percent = 100.0 * missing_height / h

    print(f"Top-connected missing height: {missing_height}px of {h}px ({missing_percent:.2f}%)")
    print(f"Top-connected missing pixels: {missing_pixels}")

    if missing_height < min_missing_px:
        copy_image(input_path, output_path, "Missing area too small. Copying image.")
        return

    if missing_percent > max_missing_percent:
        copy_image(
            input_path,
            output_path,
            f"Missing area is too large ({missing_percent:.2f}%). Copying image to avoid bad fill."
        )
        return

    # Sample real sky below the missing top area.
    # Ignore black pixels so we do not copy remap gaps into the fill.
    sample_start = min(missing_height + 5, h - 1)
    sample_end = min(sample_start + max(80, h // 50), h)

    sample = bgr8[sample_start:sample_end, :, :]
    sample_brightness = np.mean(sample, axis=2)
    sample_max = np.max(sample, axis=2)
    sample_std = np.std(sample.astype(np.float32), axis=2)

    valid_sample_mask = (sample_max > black_threshold + 8) & (sample_std > 1.0)

    valid_count = int(np.count_nonzero(valid_sample_mask))
    total_count = int(valid_sample_mask.size)

    if valid_count < max(100, total_count // 100):
        copy_image(
            input_path,
            output_path,
            "Not enough valid sky pixels below missing area. Copying image."
        )
        return

    valid_pixels = sample[valid_sample_mask]
    median_bgr = np.median(valid_pixels, axis=0).astype(np.float32)
    median_brightness = float(np.mean(median_bgr))

    print(f"Sample band: y={sample_start}..{sample_end}")
    print(f"Valid sample pixels: {valid_count} / {total_count}")
    print(f"Median sampled BGR: {median_bgr}")
    print(f"Median sampled brightness: {median_brightness:.2f}")

    # Night protection:
    # If this is not alpha/transparency-based and the sampled sky is very dark,
    # do not invent a fake sky. Leave the pano as-is.
    if not alpha_based_missing and median_brightness < min_sample_brightness:
        copy_image(
            input_path,
            output_path,
            "Sample sky is dark. Assuming night/dark scene and skipping sky fill."
        )
        return

    # Build a smooth global vertical gradient.
    # No per-column color sampling, so no vertical black seams.
    seam_color = median_bgr

    # Slightly darken/desaturate at the zenith/top.
    gray = float(np.mean(seam_color))
    top_color = seam_color * 0.82 + np.array([gray, gray, gray], dtype=np.float32) * 0.10
    top_color = np.clip(top_color, 0, 255)

    gradient = np.zeros_like(bgr8, dtype=np.float32)

    for y in range(h):
        if y <= missing_height:
            t = y / max(missing_height, 1)
            color = top_color * (1.0 - t) + seam_color * t
        else:
            color = seam_color

        gradient[y, :, 0] = color[0]
        gradient[y, :, 1] = color[1]
        gradient[y, :, 2] = color[2]

    # Create a feathered alpha from the actual missing shape.
    # Fill the missing mask fully, then softly blend around its boundary.
    missing_float = missing_mask.astype(np.float32)

    blur_sigma_x = max(20, w // 500)
    blur_sigma_y = max(10, h // 300)

    feather = cv2.GaussianBlur(missing_float, (0, 0), sigmaX=blur_sigma_x, sigmaY=blur_sigma_y)
    feather = np.maximum(feather, missing_float)

    # Restrict blending mostly to the upper sky band.
    # This avoids changing lower image content.
    band_limit = min(h, missing_height + max(80, h // 80))
    feather[band_limit:, :] = 0.0

    feather = np.clip(feather, 0.0, 1.0)
    feather3 = feather[:, :, None]

    result = bgr8.astype(np.float32) * (1.0 - feather3) + gradient * feather3
    result = np.clip(result, 0, 255).astype(np.uint8)

    # Write 3-channel output. PNG avoids TIFF ExtraSamples issues.
    if not cv2.imwrite(str(output_path), result):
        raise SystemExit(f"Failed to write image: {output_path}")

    print(f"Wrote sky-filled image: {output_path}")


if __name__ == "__main__":
    main()