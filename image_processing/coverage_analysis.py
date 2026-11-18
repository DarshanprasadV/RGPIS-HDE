
from pathlib import Path
import cv2

project = Path(__file__).resolve().parent.parent

map_path = project / "outputs/cleaned_map.png"
annotation_path = project / "datasets/test/00041000.txt"

cleaned = cv2.imread(
    str(map_path),
    cv2.IMREAD_GRAYSCALE
)

if cleaned is None:
    raise FileNotFoundError("Cleaned map not found")

with open(annotation_path) as file:
    lines = file.readlines()

print("\nDEFECT COVERAGE REPORT")
print("-" * 60)

for index, line in enumerate(lines, start=1):
    if not line.strip():
        continue

    x1, y1, x2, y2, class_id = map(int, line.split())

    region = cleaned[y1:y2, x1:x2]

    white_pixels = cv2.countNonZero(region)

    total_pixels = region.size

    coverage = (
        white_pixels / total_pixels * 100
        if total_pixels > 0 else 0
    )

    print(
        f"Defect {index} | "
        f"Class {class_id} | "
        f"Coverage: {coverage:.2f}%"
    )

print("-" * 60)
