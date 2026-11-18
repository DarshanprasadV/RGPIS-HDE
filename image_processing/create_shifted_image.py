
from pathlib import Path
import cv2
import numpy as np
import matplotlib.pyplot as plt

project = Path(__file__).resolve().parent.parent

image_path = project / "datasets/test/test.png"

image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)

if image is None:
    raise FileNotFoundError("Test PCB image not found.")

height, width = image.shape

# Rotate image by 5 degrees
center = (width / 2, height / 2)

rotation_matrix = cv2.getRotationMatrix2D(
    center,
    5,
    1.0
)

# Also shift image by 10 pixels right and 8 down
rotation_matrix[0, 2] += 10
rotation_matrix[1, 2] += 8

shifted = cv2.warpAffine(
    image,
    rotation_matrix,
    (width, height),
    flags=cv2.INTER_NEAREST,
    borderValue=255
)

# Save shifted image
output_dir = project / "outputs"
output_dir.mkdir(exist_ok=True)

output_path = output_dir / "shifted_test.png"
cv2.imwrite(str(output_path), shifted)

# Display
fig, axes = plt.subplots(1, 2, figsize=(10, 5))

axes[0].imshow(image, cmap="gray")
axes[0].set_title("Original Test PCB")

axes[1].imshow(shifted, cmap="gray")
axes[1].set_title("Rotated and Shifted PCB")

for ax in axes:
    ax.axis("off")

plt.tight_layout()
plt.show()

print("Saved shifted image to:", output_path)
