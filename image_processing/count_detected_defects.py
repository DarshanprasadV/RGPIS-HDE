
from pathlib import Path
import cv2
import numpy as np

project = Path(__file__).resolve().parent.parent

map_path = project / "outputs/cleaned_map.png"
annotation_path = project / "datasets/test/00041000.txt"

cleaned = cv2.imread(
    str(map_path),
    cv2.IMREAD_GRAYSCALE
)

if cleaned is None:
    raise FileNotFoundError("Cleaned difference map not found.")

detected = 0
total = 0

with open(annotation_path, "r") as file:
    for line in file:
        if not line.strip():
            continue

        x1, y1, x2, y2, class_id = map(int, line.split())

        # Extract pixels inside the annotated region
        region = cleaned[y1:y2, x1:x2]

        # Count white pixels
        white_pixels = cv2.countNonZero(region)

        total += 1

        if white_pixels > 0:
            detected += 1
            status = "Candidate present"
        else:
            status = "No candidate pixels"

        print(
            f"Defect {total} | Class {class_id} | "
            f"White pixels: {white_pixels} | {status}"
        )

print("\nTotal labelled defects:", total)
print("Boxes containing white pixels:", detected)

if total:
    print(
        "Annotation-box coverage:",
        f"{detected / total * 100:.2f}%"
    )
