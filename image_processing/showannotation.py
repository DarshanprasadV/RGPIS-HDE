
from pathlib import Path
import cv2
import matplotlib.pyplot as plt

# Find main project folder
project = Path(__file__).resolve().parent.parent

# File paths
image_path = project / "datasets/test/test.png"
annotation_path = project / "datasets/test/00041000.txt"

# Load test PCB image
image = cv2.imread(str(image_path))

if image is None:
    raise FileNotFoundError("Test PCB image not found.")

if not annotation_path.exists():
    raise FileNotFoundError("Annotation file not found.")

# DeepPCB defect categories (IDs follow the dataset README)
classes = {
    1: "Open circuit",
    2: "Short circuit",
    3: "Mouse bite",
    4: "Spur",
    5: "Copper",
    6: "Pin hole"
}

# Read annotation file
with open(annotation_path, "r") as file:
    lines = file.readlines()

print("Total labelled defects:", len(lines))

# Draw rectangles around defects
for line in lines:
    x1, y1, x2, y2, class_id = map(int, line.split())

    defect_name = classes.get(class_id, "Unknown")

    # Draw red bounding box (BGR format)
    cv2.rectangle(
        image,
        (x1, y1),
        (x2, y2),
        (0, 0, 255),
        2
    )

    # Add class label
    cv2.putText(
        image,
        defect_name,
        (x1, max(12, y1 - 5)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.4,
        (0, 0, 255),
        1
    )

# Save annotated image
output_dir = project / "outputs"
output_dir.mkdir(exist_ok=True)

cv2.imwrite(
    str(output_dir / "annotated_pcb.png"),
    image
)

# Display the image
image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

plt.figure(figsize=(9, 9))
plt.imshow(image_rgb)
plt.title("PCB Ground Truth - 10 Labelled Defects")
plt.axis("off")
plt.show()
