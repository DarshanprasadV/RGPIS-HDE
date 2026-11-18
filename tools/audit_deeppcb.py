#!/usr/bin/env python3
"""Audit DeepPCB files and export design-wise splits plus YOLO labels.

The source dataset is read-only. Generated manifests and labels are written
under --output. This script uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import struct
from itertools import combinations
from collections import Counter, defaultdict
from pathlib import Path


CLASS_NAMES = {
    1: "open",
    2: "short",
    3: "mousebite",
    4: "spur",
    5: "copper",
    6: "pin-hole",
}
SPLIT_NAMES = ("train", "val", "test")


def jpeg_size(path: Path) -> tuple[int, int] | None:
    """Read JPEG dimensions without requiring Pillow/OpenCV."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if not data.startswith(b"\xff\xd8"):
        return None
    i = 2
    while i < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        while i < len(data) and data[i] == 0xFF:
            i += 1
        if i >= len(data):
            break
        marker = data[i]
        i += 1
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            continue
        if i + 2 > len(data):
            break
        length = struct.unpack(">H", data[i : i + 2])[0]
        if length < 2 or i + length > len(data):
            break
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            h, w = struct.unpack(">HH", data[i + 3 : i + 7])
            return w, h
        i += length
    return None


def design_for(image: Path, root: Path) -> str:
    rel = image.relative_to(root)
    return rel.parts[0] if rel.parts else "unknown"


def split_designs(image_counts: Counter, seed: int) -> dict[str, str]:
    """Assign whole designs while balancing image totals near 70/15/15."""
    designs = sorted(image_counts)
    n = len(designs)
    if n < 5:
        raise ValueError("At least five distinct board designs are required for this split strategy.")
    # DeepPCB has 11 board designs. Two designs each are reserved for val/test;
    # among those choices select the closest 70/15/15 image-count balance.
    # Seed only breaks exact ties, so the result remains reproducible.
    rng = random.Random(seed)
    total = sum(image_counts.values())
    target = {"train": total * 0.70, "val": total * 0.15, "test": total * 0.15}
    candidates = []
    for val_designs in combinations(designs, 2):
        remaining = [d for d in designs if d not in val_designs]
        for test_designs in combinations(remaining, 2):
            train_designs = [d for d in remaining if d not in test_designs]
            counts = {
                "train": sum(image_counts[d] for d in train_designs),
                "val": sum(image_counts[d] for d in val_designs),
                "test": sum(image_counts[d] for d in test_designs),
            }
            score = sum(((counts[s] - target[s]) / max(1, target[s])) ** 2 for s in SPLIT_NAMES)
            candidates.append((score, rng.random(), val_designs, test_designs))
    _, _, val_designs, test_designs = min(candidates)
    val_set, test_set = set(val_designs), set(test_designs)
    return {d: ("val" if d in val_set else "test" if d in test_set else "train") for d in designs}


def parse_boxes(label_path: Path, width: int, height: int) -> tuple[list[tuple[int, int, int, int, int]], list[str]]:
    boxes = []
    issues = []
    try:
        lines = label_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return boxes, [f"label_unreadable:{exc}"]
    for line_no, line in enumerate(lines, 1):
        if not line.strip():
            continue
        fields = re.split(r"[\s,]+", line.strip())
        if len(fields) != 5:
            issues.append(f"malformed_label_line:{line_no}")
            continue
        try:
            x1, y1, x2, y2, class_id = (int(v) for v in fields)
        except ValueError:
            issues.append(f"noninteger_label_line:{line_no}")
            continue
        if class_id not in CLASS_NAMES:
            issues.append(f"unknown_class:{line_no}:{class_id}")
            continue
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            issues.append(f"box_out_of_bounds:{line_no}")
            continue
        boxes.append((x1, y1, x2, y2, class_id))
    return boxes, issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="DeepPCB PCBData directory")
    parser.add_argument("--output", required=True, type=Path, help="Output audit directory")
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    root = args.source.expanduser().resolve()
    out = args.output.expanduser().resolve()
    if not root.is_dir():
        parser.error(f"source directory does not exist: {root}")
    out.mkdir(parents=True, exist_ok=True)
    # Refresh files owned by this exporter so a changed split cannot leave
    # images or labels in an old split directory.
    for split in SPLIT_NAMES:
        image_dir = out / "yolo" / "images" / split
        if image_dir.exists():
            for item in image_dir.iterdir():
                if item.is_symlink():
                    item.unlink()
        label_dir = out / "yolo" / "labels" / split
        if label_dir.exists():
            for item in label_dir.glob("*.txt"):
                item.unlink()

    test_images = sorted(root.glob("group*/*/*_test.jpg"))
    template_images = sorted(root.glob("group*/*/*_temp.jpg"))
    if not test_images:
        parser.error(f"no *_test.jpg images found under {root}")
    image_by_key = {p.stem.removesuffix("_test"): p for p in test_images}
    template_by_key = {p.stem.removesuffix("_temp"): p for p in template_images}
    label_by_key = {}
    for p in root.glob("group*/*_not/*.txt"):
        label_by_key[p.stem] = p

    designs = sorted({design_for(p, root) for p in test_images})
    design_image_counts = Counter(design_for(p, root) for p in test_images)
    assignment = split_designs(design_image_counts, args.seed)
    issues = []
    class_counts = Counter()
    per_design = defaultdict(Counter)
    split_counts = defaultdict(Counter)
    dimensions = Counter()
    rows = []

    for key, image in image_by_key.items():
        design = design_for(image, root)
        template = template_by_key.get(key)
        label = label_by_key.get(key)
        row_issues = []
        if template is None:
            row_issues.append("missing_template")
        if label is None:
            row_issues.append("missing_label")
        size = jpeg_size(image)
        if size is None:
            row_issues.append("test_image_unreadable_or_not_jpeg")
            width = height = 0
        else:
            width, height = size
            dimensions[f"{width}x{height}"] += 1
        if template is not None:
            tsize = jpeg_size(template)
            if tsize is None:
                row_issues.append("template_unreadable_or_not_jpeg")
            elif size is not None and tsize != size:
                row_issues.append(f"template_dimension_mismatch:{tsize[0]}x{tsize[1]}")
        boxes = []
        if label is not None and width and height:
            boxes, label_issues = parse_boxes(label, width, height)
            row_issues.extend(label_issues)
        split = assignment[design]
        for _, _, _, _, cid in boxes:
            class_counts[cid] += 1
            per_design[design][cid] += 1
            split_counts[split][cid] += 1
        if row_issues:
            issues.extend({"image": image.relative_to(root).as_posix(), "issue": issue} for issue in row_issues)
        rows.append({
            "image_id": key,
            "design": design,
            "split": split,
            "test_image": str(image),
            "template_image": str(template) if template else "",
            "annotation": str(label) if label else "",
            "width": width,
            "height": height,
            "defect_count": len(boxes),
            "issues": ";".join(row_issues),
        })
        # YOLO labels use zero-based IDs. Emit empty files for clean images.
        label_out = out / "yolo" / "labels" / split / f"{key}.txt"
        label_out.parent.mkdir(parents=True, exist_ok=True)
        with label_out.open("w", encoding="utf-8") as stream:
            for x1, y1, x2, y2, cid in boxes:
                xc = (x1 + x2) / (2 * width)
                yc = (y1 + y2) / (2 * height)
                bw = (x2 - x1) / width
                bh = (y2 - y1) / height
                stream.write(f"{cid - 1} {xc:.8f} {yc:.8f} {bw:.8f} {bh:.8f}\n")
        image_link = out / "yolo" / "images" / split / f"{key}.jpg"
        image_link.parent.mkdir(parents=True, exist_ok=True)
        if image_link.exists() and not image_link.is_symlink():
            raise FileExistsError(f"Refusing to replace non-symlink dataset file: {image_link}")
        image_link.symlink_to(image)

    for key in sorted(set(template_by_key) - set(image_by_key)):
        issues.append({"image": str(template_by_key[key].relative_to(root)), "issue": "template_without_test_image"})
    for key in sorted(set(label_by_key) - set(image_by_key)):
        issues.append({"image": str(label_by_key[key].relative_to(root)), "issue": "annotation_without_test_image"})

    with (out / "manifest.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with (out / "issues.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=("image", "issue"))
        writer.writeheader()
        writer.writerows(issues)

    summary = {
        "source_root": str(root),
        "seed": args.seed,
        "split_method": "whole board design directories; exhaustive 2-val/2-test design selection minimizing image-count deviation from 70/15/15; seed breaks ties",
        "test_images": len(test_images),
        "template_images": len(template_images),
        "annotation_files": len(label_by_key),
        "board_designs": len(designs),
        "dimensions": dict(dimensions),
        "issues": len(issues),
        "defect_instances": sum(class_counts.values()),
        "class_map_yolo_zero_based": {str(i - 1): name for i, name in CLASS_NAMES.items()},
        "class_counts": {CLASS_NAMES[i]: class_counts[i] for i in CLASS_NAMES},
        "design_split": {d: assignment[d] for d in designs},
        "design_defect_counts": {d: {CLASS_NAMES[i]: per_design[d][i] for i in CLASS_NAMES} for d in designs},
        "split_image_counts": dict(Counter(r["split"] for r in rows)),
        "split_defect_counts": {s: {CLASS_NAMES[i]: split_counts[s][i] for i in CLASS_NAMES} for s in SPLIT_NAMES},
        "notes": [
            "Image paths in manifest.csv point to the source dataset; YOLO image entries are symlinks, so source images are not copied or modified.",
            "YOLO label files are converted to zero-based class IDs and normalized xywh coordinates.",
            "Design-wise split is deterministic for a fixed seed and balances image counts; class balance should be reviewed before training.",
            "The supplied trainval/test lists are image-level, not design-isolated: seven board design directories occur in both lists.",
            "The supplied trainval.txt/test.txt lists cover 1,500 pairs when their unsuffixed image names are resolved to the *_test.jpg files in this checkout.",
            "One extra *_temp.jpg exists without a matching test image.",
            "DeepPCB README says the dataset is for research use; verify rights before commercial use or redistribution.",
        ],
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    # This layout follows Ultralytics' image/label path convention while
    # avoiding a second copy of the source images.
    yaml = [f"path: {str(out / 'yolo').replace(chr(92), '/')}",
            "train: images/train",
            "val: images/val",
            "test: images/test",
            "names:"]
    yaml.extend(f"  {i - 1}: {name}" for i, name in CLASS_NAMES.items())
    (out / "yolo" / "data.yaml").write_text("\n".join(yaml) + "\n", encoding="utf-8")
    print(json.dumps({"summary": summary, "output": str(out)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
