#!/usr/bin/env python3
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: check_pto_crop.py <project.pto>")

pto = sys.argv[1]

p_line = None
with open(pto, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        if line.startswith("p "):
            p_line = line.strip()
            break

if not p_line:
    raise SystemExit("No panorama p-line found in PTO file")

def get_token(prefix):
    for tok in p_line.split():
        if tok.startswith(prefix):
            return tok[len(prefix):]
    return None

w = int(float(get_token("w")))
h = int(float(get_token("h")))

s = get_token("S")
if s:
    left, right, top, bottom = [int(float(x)) for x in s.split(",")]
else:
    left, right, top, bottom = 0, w, 0, h

crop_w = right - left
crop_h = bottom - top

canvas_ratio = w / h if h else 0
crop_ratio = crop_w / crop_h if crop_h else 0

full_canvas = left == 0 and top == 0 and right == w and bottom == h
ratio_ok = abs(crop_ratio - 2.0) <= 0.02
canvas_ratio_ok = abs(canvas_ratio - 2.0) <= 0.02

crop_issue = (not full_canvas) or (not ratio_ok)

print(f'CANVAS_W={w}')
print(f'CANVAS_H={h}')
print(f'CROP_LEFT={left}')
print(f'CROP_RIGHT={right}')
print(f'CROP_TOP={top}')
print(f'CROP_BOTTOM={bottom}')
print(f'CROP_W={crop_w}')
print(f'CROP_H={crop_h}')
print(f'CANVAS_RATIO="{canvas_ratio:.6f}"')
print(f'CROP_RATIO="{crop_ratio:.6f}"')
print(f'FULL_CANVAS={1 if full_canvas else 0}')
print(f'RATIO_OK={1 if ratio_ok else 0}')
print(f'CANVAS_RATIO_OK={1 if canvas_ratio_ok else 0}')
print(f'CROP_ISSUE={1 if crop_issue else 0}')