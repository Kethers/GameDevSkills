"""
Post-process already-captured screenshots whose projected slide occupies too small
a share of the frame (e.g. a small bright rectangle inside a wide dark auditorium shot).

Detects the slide bounding box (largest bright/edge-rich region), and if it fills less
than --min-frac of the frame, crops to it (16:9, small margin) and rescales to 1920x1080
so the PPT content fills the picture. Writes in place (backs up nothing — re-capture if needed).

Reuses detect_slide_bbox / crop_to_slide from smart_slide_capture.py.

Usage:
  python crop_to_slide.py "<Img_dir>" [--min-frac 0.55] [--files img_01.png img_07.png ...] [--dry-run]
  # no --files -> scans every *.png in Img_dir
Reads/writes with cv2.imdecode/imencode so it works on CJK/non-ASCII paths.
"""
import sys, os, glob, argparse
import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smart_slide_capture import detect_slide_bbox, crop_to_slide  # noqa: E402


def imread_u(p):
    return cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_COLOR)


def imwrite_u(p, img):
    ext = os.path.splitext(p)[1] or ".png"
    ok, buf = cv2.imencode(ext, img)
    if ok:
        buf.tofile(p)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("img_dir")
    ap.add_argument("--min-frac", type=float, default=0.55)
    ap.add_argument("--files", nargs="*", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    files = ([os.path.join(a.img_dir, f) for f in a.files] if a.files
             else sorted(glob.glob(os.path.join(a.img_dir, "*.png"))))
    changed = 0
    for f in files:
        img = imread_u(f)
        if img is None:
            print("skip (unreadable):", os.path.basename(f)); continue
        bb = detect_slide_bbox(img)
        frac = bb[4] if bb else 1.0
        cropped, _ = crop_to_slide(img, min_frac=a.min_frac)
        if cropped is not img:
            print(f"{'WOULD CROP' if a.dry_run else 'CROPPED'} {os.path.basename(f)}  slide was {frac:.0%} of frame")
            if not a.dry_run:
                imwrite_u(f, cropped); changed += 1
        else:
            print(f"keep {os.path.basename(f)}  slide {frac:.0%}")
    print(f"\n{'(dry-run) ' if a.dry_run else ''}cropped {changed} file(s)")


if __name__ == "__main__":
    main()
