# 15:10 crop + hex guide

## Web version

Available in your browser, no installation needed: [https://kislac.github.io/hex_picture_editor/](https://kislac.github.io/hex_picture_editor/)

## Installation

```powershell
python -m pip install -r .\requirements.txt
```

## Usage (Desktop Python)

```powershell
python .\picture_edit.py
```

## Features

- `Open images…`: Select one or more images
- Drag the 15:10 frame to position it
- `Crop size` slider: adjust the frame size (fixed aspect, can be larger than the image)
- `Hex rotate 30°`: toggle hex rotation (pointy bottom / flat bottom)
- `Export crop…`: crops and saves as PNG (no resizing, pixel size is preserved)

If the 15:10 frame extends beyond the image, the exported area outside the image will be white.
When resizing/moving/rotating, the hex guide will never extend outside the original image.

Note: The hex is only a visual guide; the saved image is always a rectangle (15:10).
