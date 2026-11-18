
from pathlib import Path
import cv2
import matplotlib.pyplot as plt

project = Path(__file__).resolve().parent.parent

# Load the cleaned difference map
map_path = project / "outputs/cleaned_map.png"
cleaned = cv2.imread(str(map_path), cv2.IMREAD_GRAYSCALE)

# Annotation file
annotation_path = project / "datasets/test/00041000.txt"

if cleaned is None:
    raise FileNotFoundError("Cleaned map not found.")

if not annotation_path.exists():
    raise FileNotFoundError("Annotation file not found.")

# Convert map to colour so we can draw red boxes
result = cv2.cvtColor(cleaned, cv2.COLOR_GRAY2BGR)

# Read the actual defect coordinates
with open(annotation_path, "r") as file:
    lines = file.readlines()

# Draw annotation boxes
for line in lines:
    x1, y1, x2, y2, class_id = map(int, line.split())

    cv2.rectangle(
        result,
        (x1, y1),
        (x2, y2),
        (0, 0, 255),
        2
    )

# Save result
output_path = project / "outputs/validated_map.png"
cv2.imwrite(str(output_path), result)

# Display image
plt.figure(figsize=(8, 8))
plt.imshow(cv2.cvtColor(result, cv2.COLOR_BGR2RGB))
plt.title("Cleaned Difference Map + Ground Truth")
plt.axis("off")
plt.show()
