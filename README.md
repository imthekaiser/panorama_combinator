# panorama_combinator

Simple Docker tool for stitching panorama image sets.

Built around DJI Matrice 4T panorama folders, but it may work with other image sets also.

## What It Does

This project takes folders of panorama images, stitches them with Hugin tools, and outputs a finished panorama image.

Each input folder is treated as one panorama project.

## Limitations

This is still in Beta status.  Works almost every time for me on the low resolution dji panoramas.  But the 144 image High Resolution Panorama is still giving me problems and still needs troubleshooting.

## Requirements

* Docker
* Docker Compose

## Folder Setup

Create these folders in the project directory:

```bash
mkdir -p data/input
mkdir -p data/output
```

Put each panorama image set in its own folder under `data/input`.

Example:

```text
data/
  input/
    001_0001/
      image1.jpg
      image2.jpg
      image3.jpg
    001_0002/
      image1.jpg
      image2.jpg
      image3.jpg
  output/
```

Supported input formats:

```text
.jpg
.jpeg
.tif
.tiff
```

## How To Run

From the project folder:

```bash
docker compose up --build
```

The container will process every folder inside:

```text
data/input/
```

## Output

Finished files are written to:

```text
data/output/
```

Example:

```text
data/output/001_0001/pano.jpg
```

Each project output folder may also include:

```text
originals/
work/
logs/
crop_check.env
final_crop_check.env
pano.tif
pano.jpg
```

The main final image is:

```text
pano.jpg
```

## Settings

The default panorama field of view is:

```text
PANO_FOV=360x180
```

For full spherical panoramas, leave it as:

```text
360x180
```

## Notes

* Use one folder per panorama.
* Keep the original image filenames from the drone when possible.
* The tool expects at least 2 images in a project folder.
* If stitching fails, check the log file in the matching output folder:

```text
data/output/<project-name>/logs/process.log
```

## Basic Troubleshooting

### No project folders found

Make sure your images are inside a subfolder under `data/input`.

Wrong:

```text
data/input/image1.jpg
data/input/image2.jpg
```

Correct:

```text
data/input/001_0001/image1.jpg
data/input/001_0001/image2.jpg
```

### No usable images found

Make sure the images are `.jpg`, `.jpeg`, `.tif`, or `.tiff`.

### Output is missing sky or ground

This usually means the source images do not cover the full sphere. The tool can create a 360x180 panorama canvas, but it cannot invent missing image data.

You may need to:

* capture more sky/ground images
* patch the missing area manually
* use a smaller field of view
* accept a blank or filled area in the final panorama