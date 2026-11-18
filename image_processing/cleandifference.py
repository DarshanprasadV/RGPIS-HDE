
from pathlib import Path
import cv2
import matplotlib.pyplot as plt

project = Path(__file__).resolve().parent.parent

# Load existing difference map
difference_path = project / "outputs/binary_map.png"
binary_map = cv2.imread(
    str(difference_path),
    cv2.IMREAD_GRAYSCALE
)

if binary_map is None:
    raise FileNotFoundError(
        "Run basic_difference.py first."
    )

# Create a small kernel
kernel = cv2.getStructuringElement(
    cv2.MORPH_ELLIPSE, (3, 3)
)

# Remove tiny noise regions
cleaned = cv2.morphologyEx(
    binary_map,
    cv2.MORPH_OPEN,
    kernel
)

# Save cleaned result
output_path = project / "outputs/cleaned_map.png"
cv2.imwrite(str(output_path), cleaned)

# Display before and after
fig, axes = plt.subplots(1, 2, figsize=(10, 5))

axes[0].imshow(binary_map, cmap="gray")
axes[0].set_title("Before Cleaning")

axes[1].imshow(cleaned, cmap="gray")
axes[1].set_title("After Cleaning")

for ax in axes:
    ax.axis("off")

plt.tight_layout()
plt.show()
