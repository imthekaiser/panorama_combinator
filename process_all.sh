#!/usr/bin/env bash
set -Eeuo pipefail

INPUT_ROOT="${INPUT_ROOT:-/app/data/input}"
OUTPUT_ROOT="${OUTPUT_ROOT:-/app/data/output}"
PANO_FOV="${PANO_FOV:-360x180}"

find_images() {
  find -L "$1" -maxdepth 1 -type f \
    \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.tif" -o -iname "*.tiff" \) \
    -print0 | sort -zV
}

process_project() {
  local src_dir="$1"
  local project_name
  local project_out
  local originals_dir
  local work_dir
  local logs_dir
  local process_log
  local count
  local base
  local file
  local tif
  local width
  local height
  local FULL_W
  local FULL_H
  local work_count

  project_name="$(basename "$src_dir")"
  project_out="$OUTPUT_ROOT/$project_name"
  originals_dir="$project_out/originals"
  work_dir="$project_out/work"
  logs_dir="$project_out/logs"
  process_log="$logs_dir/process.log"

  mkdir -p "$project_out" "$originals_dir" "$logs_dir"

  rm -rf "$work_dir"
  mkdir -p "$work_dir"

  {
    echo "===================================================="
    echo "Processing project: $project_name"
    echo "Source: $src_dir"
    echo "Output: $project_out"
    echo "===================================================="

    count=0

    while IFS= read -r -d '' file; do
      base="$(basename "$file")"

      cp -f "$file" "$originals_dir/$base"
      cp -f "$file" "$work_dir/$base"

      count=$((count + 1))
    done < <(find_images "$src_dir")

    echo "Images found: $count"

    if [ "$count" -lt 2 ]; then
      echo "Skipping $project_name because it has fewer than 2 images."
      return 0
    fi

    cd "$work_dir"

    work_count="$(find_images "$work_dir" | tr -cd '\0' | wc -c)"
    echo "Images available in work folder: $work_count"

    if [ "$work_count" -lt 2 ]; then
      echo "No usable images found in work folder."
      return 1
    fi

    mapfile -d '' -t IMAGES < <(find_images "$work_dir")

    echo "Image list passed to pto_gen:"
    printf '  %s\n' "${IMAGES[@]}"

    echo "Generating PTO project..."
    pto_gen -o project.pto "${IMAGES[@]}"

    if [ ! -s project.pto ]; then
      echo "project.pto was not created or is empty."
      return 1
    fi

    echo "Finding control points..."
    cpfind --multirow -o project_cp.pto project.pto

    if [ ! -s project_cp.pto ]; then
      echo "project_cp.pto was not created or is empty."
      return 1
    fi

    echo "Cleaning control points..."
    cpclean -o project_clean.pto project_cp.pto

    if [ ! -s project_clean.pto ]; then
      echo "project_clean.pto was not created or is empty."
      return 1
    fi

    echo "Optimizing project..."
    autooptimiser -a -m -l -s -o project_opt.pto project_clean.pto

    if [ ! -s project_opt.pto ]; then
      echo "project_opt.pto was not created or is empty."
      return 1
    fi

    echo "Creating auto-crop test PTO..."
    pano_modify \
      --projection=2 \
      --fov="$PANO_FOV" \
      --straighten \
      --center \
      --canvas=AUTO \
      --crop=AUTO \
      --output-type=NORMAL \
      --ldr-file=TIF \
      --ldr-compression=LZW \
      -o project_autocrop.pto \
      project_opt.pto

    if [ ! -s project_autocrop.pto ]; then
      echo "project_autocrop.pto was not created or is empty."
      return 1
    fi

    echo "Checking auto-crop..."
    python3 /app/check_pto_crop.py project_autocrop.pto | tee "$project_out/crop_check.env"

    # shellcheck disable=SC1090
    source "$project_out/crop_check.env"

    FULL_W=$(( (CANVAS_W / 2) * 2 ))
    FULL_H=$(( FULL_W / 2 ))

    if [ "$CROP_ISSUE" = "1" ]; then
      echo "Crop issue detected."
      echo "Forcing full 2:1 equirectangular canvas: ${FULL_W}x${FULL_H}"

      pano_modify \
        --projection=2 \
        --fov="$PANO_FOV" \
        --straighten \
        --center \
        --canvas="${FULL_W}x${FULL_H}" \
        --crop="0,${FULL_W},0,${FULL_H}" \
        --output-type=NORMAL \
        --ldr-file=TIF \
        --ldr-compression=LZW \
        -o project_final.pto \
        project_opt.pto
    else
      echo "Auto-crop acceptable."
      cp project_autocrop.pto project_final.pto
    fi

    if [ ! -s project_final.pto ]; then
      echo "project_final.pto was not created or is empty."
      return 1
    fi

    echo "Final crop check..."
    python3 /app/check_pto_crop.py project_final.pto | tee "$project_out/final_crop_check.env"

    echo "Removing old final outputs..."
    rm -f "$project_out"/pano.tif
    rm -f "$project_out"/pano.tiff
    rm -f "$project_out"/pano.jpg
    rm -f "$project_out"/pano*.tif
    rm -f "$project_out"/pano*.tiff

    echo "Stitching panorama..."
    hugin_executor \
      --stitching \
      --prefix="$project_out/pano" \
      project_final.pto \
      2>&1 | tee "$logs_dir/stitch.log"

    tif=""

    if [ -f "$project_out/pano.tif" ]; then
      tif="$project_out/pano.tif"
    elif [ -f "$project_out/pano.tiff" ]; then
      tif="$project_out/pano.tiff"
    else
      tif="$(find "$project_out" -maxdepth 1 -type f \
        \( -name "pano.tif" -o -name "pano.tiff" \) \
        | head -n 1 || true)"
    fi

    if [ -z "$tif" ]; then
      echo "No stitched TIFF output found."
      return 1
    fi

    echo "Stitched TIFF: $tif"

    echo "Converting TIFF to JPEG..."
    vips copy "$tif" "$project_out/pano.jpg[Q=95]"

    if [ ! -s "$project_out/pano.jpg" ]; then
      echo "JPEG output was not created."
      return 1
    fi

    width="$(vipsheader -f width "$project_out/pano.jpg")"
    height="$(vipsheader -f height "$project_out/pano.jpg")"

    echo "Final JPEG dimensions: ${width}x${height}"

    if python3 - "$width" "$height" <<'PY'
import sys
w = int(sys.argv[1])
h = int(sys.argv[2])
ratio = w / h
print(f"JPEG ratio: {ratio:.6f}")
sys.exit(0 if abs(ratio - 2.0) <= 0.02 else 1)
PY
    then
      echo "Adding GPano metadata..."
      exiftool -overwrite_original \
        -XMP-GPano:UsePanoramaViewer=True \
        -XMP-GPano:ProjectionType=equirectangular \
        -XMP-GPano:CroppedAreaImageWidthPixels="$width" \
        -XMP-GPano:CroppedAreaImageHeightPixels="$height" \
        -XMP-GPano:FullPanoWidthPixels="$width" \
        -XMP-GPano:FullPanoHeightPixels="$height" \
        -XMP-GPano:CroppedAreaLeftPixels=0 \
        -XMP-GPano:CroppedAreaTopPixels=0 \
        "$project_out/pano.jpg"
    else
      echo "Skipping GPano metadata because output is not close to 2:1."
    fi

    echo "Project complete: $project_name"
    echo
    ls -lh "$project_out"
    echo

  } 2>&1 | tee "$process_log"
}

main() {
  local found=0
  local failures=0
  local project_dir

  mkdir -p "$INPUT_ROOT" "$OUTPUT_ROOT"

  while IFS= read -r -d '' project_dir; do
    found=1

    if ! process_project "$project_dir"; then
      echo "FAILED project: $(basename "$project_dir")"
      failures=$((failures + 1))
    fi
  done < <(find "$INPUT_ROOT" -mindepth 1 -maxdepth 1 -type d -print0 | sort -zV)

  if [ "$found" -eq 0 ]; then
    echo "No project folders found in $INPUT_ROOT"
    exit 0
  fi

  if [ "$failures" -gt 0 ]; then
    echo "$failures project(s) failed."
    exit 1
  fi

  echo "All projects processed successfully."
}

main "$@"
