
from pathlib import Path
import cv2
import matplotlib.pyplot as plt

project = Path(__file__).resolve().parent.parent

reference_path = project / "datasets/reference/golden.png"
test_path = project / "datasets/test/test.png"

reference = cv2.imread(str(reference_path), cv2.IMREAD_GRAYSCALE)
test = cv2.imread(str(test_path), cv2.IMREAD_GRAYSCALE)

if reference is None or test is None:
    raise FileNotFoundError("Check your PCB image paths.")

if reference.shape != test.shape:
    raise ValueError("Reference and test image dimensions differ.")

# Calculate absolute difference between pixels
difference = cv2.absdiff(reference, test)

# Convert differences into a binary map
_, binary_map = cv2.threshold(
    difference, 30, 255, cv2.THRESH_BINARY
)

# Save output images
output_dir = project / "outputs"
output_dir.mkdir(exist_ok=True)

cv2.imwrite(str(output_dir / "difference.png"), difference)
cv2.imwrite(str(output_dir / "binary_map.png"), binary_map)

# Display the results
fig, axes = plt.subplots(1, 3, figsize=(12, 4))

axes[0].imshow(reference, cmap="gray")
axes[0].set_title("Golden Reference")

axes[1].imshow(test, cmap="gray")
axes[1].set_title("Test PCB")

axes[2].imshow(binary_map, cmap="gray")
axes[2].set_title("Difference Map")

for ax in axes:
    ax.axis("off")

plt.tight_layout()
plt.show()
