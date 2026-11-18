#!/usr/bin/env python3
"""Build a six-class mixed training set with 6,000+ real PCB images.

Reads DeepPCB and DsPCBSD+ without modifying either source. DsPCBSD+ samples
with unsupported defect classes are excluded rather than treated as negatives.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import zipfile
from collections import Counter, defaultdict
from pathlib import Path


CLASS_NAMES = ["open", "short", "mousebite", "spur", "copper", "pin-hole"]
DS_CLASS_TO_YOLO = {"OP": 0, "SH": 1, "MB": 2, "SP": 3, "SC": 4}
SPLITS = ("train", "val", "test")


def clear_owned_outputs(root: Path) -> None:
    if not root.exists():
        return
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deeppcb", type=Path, required=True, help="DeepPCB PCBData source directory")
    parser.add_argument("--deep-manifest", type=Path, required=True, help="Audited DeepPCB manifest.csv")
    parser.add_argument("--deep-yolo", type=Path, required=True, help="Audited DeepPCB YOLO dataset root")
    parser.add_argument("--dspcbsd-zip", type=Path, required=True, help="Official DsPCBSD+ archive")
    parser.add_argument("--output", type=Path, required=True, help="Output mixed YOLO dataset directory")
    parser.add_argument("--overwrite", action="store_true", help="Refresh the generated output directory")
    args = parser.parse_args()

    deep_root = args.deeppcb.expanduser().resolve()
    archive_path = args.dspcbsd_zip.expanduser().resolve()
    out = args.output.expanduser().resolve()
    if not deep_root.is_dir():
        parser.error(f"DeepPCB folder not found: {deep_root}")
    if not archive_path.is_file():
        parser.error(f"DsPCBSD+ archive not found: {archive_path}")
    if out.exists():
        if not args.overwrite:
            parser.error(f"Output already exists; pass --overwrite to refresh it: {out}")
        clear_owned_outputs(out)
    out.mkdir(parents=True, exist_ok=True)
    images_root = out / "yolo" / "images"
    labels_root = out / "yolo" / "labels"
    for split in SPLITS:
        (images_root / split).mkdir(parents=True, exist_ok=True)
        (labels_root / split).mkdir(parents=True, exist_ok=True)

    rows = []
    per_source_classes = defaultdict(Counter)
    exclusions = Counter()

    # Use the repository's audited, design-wise DeepPCB split. Keep its
    # validation and test boards in those sets; only the train rows are mixed.
    audit_manifest = args.deep_manifest.expanduser().resolve()
    deep_yolo = args.deep_yolo.expanduser().resolve()
    if not audit_manifest.is_file():
        parser.error(f"Expected audited DeepPCB manifest beside source: {audit_manifest}")
    with audit_manifest.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            split = row["split"]
            image_id = f"deep_{row['image_id']}"
            source_image = Path(row["test_image"])
            source_label = deep_yolo / "labels" / split / f"{row['image_id']}.txt"
            image_target = images_root / split / f"{image_id}.jpg"
            label_target = labels_root / split / f"{image_id}.txt"
            image_target.symlink_to(source_image)
            shutil.copyfile(source_label, label_target)
            label_lines = [line for line in label_target.read_text(encoding="utf-8").splitlines() if line.strip()]
            class_count = Counter(int(line.split()[0]) for line in label_lines)
            for class_id, count in class_count.items():
                per_source_classes["DeepPCB"][CLASS_NAMES[class_id]] += count
            rows.append({
                "image_id": image_id,
                "source": "DeepPCB",
                "source_partition": "design-wise DeepPCB split",
                "split": split,
                "image": str(image_target),
                "label": str(label_target),
                "width": row["width"],
                "height": row["height"],
                "boxes": len(label_lines),
            })

    ds_added = 0
    ds_box_count = 0
    with zipfile.ZipFile(archive_path) as archive:
        for source_split in ("train", "val"):
            annotation_path = f"Data_COCO/annotations/instances_{source_split}2017.json"
            data = json.loads(archive.read(annotation_path))
            categories = {int(item["id"]): item["name"] for item in data["categories"]}
            annotations_by_image = defaultdict(list)
            for annotation in data["annotations"]:
                annotations_by_image[int(annotation["image_id"])].append(annotation)
            for image_info in data["images"]:
                image_id = int(image_info["id"])
                annotations = annotations_by_image.get(image_id, [])
                category_names = {categories[int(a["category_id"])] for a in annotations}
                if not annotations:
                    exclusions["empty_annotation"] += 1
                    continue
                unsupported = category_names - set(DS_CLASS_TO_YOLO)
                if unsupported:
                    exclusions["contains_unsupported_classes"] += 1
                    continue

                width, height = int(image_info["width"]), int(image_info["height"])
                normalized_boxes = []
                malformed = False
                for annotation in annotations:
                    category = categories[int(annotation["category_id"])]
                    x, y, bw, bh = (float(v) for v in annotation["bbox"])
                    if bw <= 0 or bh <= 0 or x < 0 or y < 0 or x + bw > width + 1 or y + bh > height + 1:
                        malformed = True
                        break
                    x2, y2 = min(width, x + bw), min(height, y + bh)
                    x, y = max(0.0, x), max(0.0, y)
                    bw, bh = x2 - x, y2 - y
                    if bw <= 0 or bh <= 0:
                        malformed = True
                        break
                    xc, yc = (x + bw / 2) / width, (y + bh / 2) / height
                    normalized_boxes.append((DS_CLASS_TO_YOLO[category], xc, yc, bw / width, bh / height))
                if malformed:
                    exclusions["invalid_bbox"] += 1
                    continue

                filename = Path(image_info["file_name"]).name
                source_image_path = f"Data_COCO/{source_split}2017/{filename}"
                image_key = f"dsp_{source_split}_{Path(filename).stem}"
                image_target = images_root / "train" / f"{image_key}.jpg"
                label_target = labels_root / "train" / f"{image_key}.txt"
                image_target.write_bytes(archive.read(source_image_path))
                label_target.write_text(
                    "".join(f"{cid} {xc:.8f} {yc:.8f} {bw:.8f} {bh:.8f}\n" for cid, xc, yc, bw, bh in normalized_boxes),
                    encoding="utf-8",
                )
                ds_added += 1
                ds_box_count += len(normalized_boxes)
                for cid, *_ in normalized_boxes:
                    per_source_classes["DsPCBSD+"][CLASS_NAMES[cid]] += 1
                rows.append({
                    "image_id": image_key,
                    "source": "DsPCBSD+",
                    "source_partition": source_split,
                    "split": "train",
                    "image": str(image_target),
                    "label": str(label_target),
                    "width": width,
                    "height": height,
                    "boxes": len(normalized_boxes),
                })

    with (out / "manifest.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = ["image_id", "source", "source_partition", "split", "image", "label", "width", "height", "boxes"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    train_images = sum(row["split"] == "train" for row in rows)
    val_images = sum(row["split"] == "val" for row in rows)
    test_images = sum(row["split"] == "test" for row in rows)
    summary = {
        "dataset": "DeepPCB + DsPCBSD+ real-image six-class mix",
        "training_images": train_images,
        "validation_images": val_images,
        "test_images": test_images,
        "dspcbsd_images_added": ds_added,
        "dspcbsd_boxes_added": ds_box_count,
        "exclusions": dict(exclusions),
        "class_names": CLASS_NAMES,
        "dspcbsd_to_yolo_class_mapping": {name: DS_CLASS_TO_YOLO[name] for name in DS_CLASS_TO_YOLO},
        "per_source_class_counts": {source: dict(counts) for source, counts in per_source_classes.items()},
        "evaluation_note": "DeepPCB's existing design-held-out val/test splits are preserved. All compatible DsPCBSD+ images from its supplied train and val partitions are used for training; no DsPCBSD+ image is treated as an evaluation image.",
        "license_note": "DsPCBSD+ is CC BY 4.0 and requires attribution. DeepPCB README restricts dataset use to research; the mixed dataset therefore remains research-only unless rights are separately granted.",
        "excluded_classes": ["HB (hole breakout)", "CS (conductor scratch)", "CFO (conductor foreign object)", "BMFO (base material foreign object)"],
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    yaml_lines = [f"path: {str(out / 'yolo').replace(chr(92), '/')}", "train: images/train", "val: images/val", "test: images/test", "names:"]
    yaml_lines.extend(f"  {index}: {name}" for index, name in enumerate(CLASS_NAMES))
    (out / "yolo" / "data.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
