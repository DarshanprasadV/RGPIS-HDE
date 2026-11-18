from pathlib import Path
import cv2
import numpy as np
import matplotlib.pyplot as plt

project = Path(__file__).resolve().parent.parent

original_path = project / "datasets/test/test.png"
shifted_path = project / "outputs/shifted_test.png"

original = cv2.imread(
    str(original_path), cv2.IMREAD_GRAYSCALE
)

shifted = cv2.imread(
    str(shifted_path), cv2.IMREAD_GRAYSCALE
)

if original is None or shifted is None:
    raise FileNotFoundError("Check image paths.")

# 1. Create ORB feature detector
orb = cv2.ORB_create(nfeatures=2000)

# 2. Detect features and descriptors
kp1, des1 = orb.detectAndCompute(original, None)
kp2, des2 = orb.detectAndCompute(shifted, None)

if des1 is None or des2 is None:
    raise RuntimeError("Not enough features detected.")

# 3. Match descriptors
matcher = cv2.BFMatcher(cv2.NORM_HAMMING)

matches = matcher.knnMatch(des2, des1, k=2)

# 4. Lowe's ratio test
good_matches = []

for pair in matches:
    if len(pair) == 2:
        m, n = pair
        if m.distance < 0.75 * n.distance:
            good_matches.append(m)

print("Good matches:", len(good_matches))

if len(good_matches) < 4:
    raise RuntimeError("Not enough matches for homography.")

# 5. Extract matching coordinates
src_points = np.float32([
    kp2[m.queryIdx].pt for m in good_matches
]).reshape(-1, 1, 2)

dst_points = np.float32([
    kp1[m.trainIdx].pt for m in good_matches
]).reshape(-1, 1, 2)

# 6. Estimate homography using RANSAC
H, mask = cv2.findHomography(
    src_points,
    dst_points,
    cv2.RANSAC,
    5.0
)

if H is None:
    raise RuntimeError("Homography estimation failed.")

# 7. Warp the shifted image
height, width = original.shape

aligned = cv2.warpPerspective(
    shifted,
    H,
    (width, height),
    flags=cv2.INTER_NEAREST,
    borderValue=255
)

# 8. Save aligned output
output_dir = project / "outputs"
output_dir.mkdir(exist_ok=True)

cv2.imwrite(
    str(output_dir / "aligned_test.png"),
    aligned
)

# 9. Display results
fig, axes = plt.subplots(1, 3, figsize=(12, 4))

axes[0].imshow(original, cmap="gray")
axes[0].set_title("Original PCB")

axes[1].imshow(shifted, cmap="gray")
axes[1].set_title("Rotated PCB")

axes[2].imshow(aligned, cmap="gray")
axes[2].set_title("ORB + RANSAC Aligned PCB")

for ax in axes:
    ax.axis("off")

plt.tight_layout()
plt.show()

print("Aligned image saved successfully.")

# Measure alignment quality

# Difference before registration
difference_before = cv2.absdiff(original, shifted)

# Difference after registration
difference_after = cv2.absdiff(original, aligned)

# Calculate mean pixel difference
mae_before = np.mean(difference_before)
mae_after = np.mean(difference_after)

print("\nREGISTRATION QUALITY REPORT")
print("----------------------------")
print(f"MAE before registration: {mae_before:.2f}")
print(f"MAE after registration:  {mae_after:.2f}")

if mae_after < mae_before:
    print("Registration reduced the image difference.")
else:
    print("Registration did not reduce image difference.")

# Show differences
fig, axes = plt.subplots(1, 2, figsize=(10, 5))

axes[0].imshow(difference_before, cmap="gray")
axes[0].set_title("Difference Before Registration")

axes[1].imshow(difference_after, cmap="gray")
axes[1].set_title("Difference After Registration")

for ax in axes:
    ax.axis("off")

plt.tight_layout()
plt.show()
