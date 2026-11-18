from pathlib import Path

try:
    import cv2  # type: ignore[import-not-found]
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        "OpenCV (cv2) is required. Install it with: pip install opencv-python"
    ) from exc

try:
    import matplotlib.pyplot as plt  # type: ignore[import-not-found]
except ModuleNotFoundError:
    plt = None


project = Path(__file__).resolve().parent.parent
reference_path = project / "datasets" / "reference" / "golden.png"
test_path = project / "datasets" / "test" / "test.png"

reference = cv2.imread(str(reference_path), cv2.IMREAD_COLOR)
test = cv2.imread(str(test_path), cv2.IMREAD_COLOR)

if reference is None:
    raise FileNotFoundError(
        f"Golden reference image not found or unreadable: {reference_path}"
    )
if test is None:
    raise FileNotFoundError(
        f"Test PCB image not found or unreadable: {test_path}"
    )

print("Both images loaded successfully!")
print(f"Golden image dimensions: {reference.shape}")
print(f"Test image dimensions: {test.shape}")

reference_rgb = cv2.cvtColor(reference, cv2.COLOR_BGR2RGB)
test_rgb = cv2.cvtColor(test, cv2.COLOR_BGR2RGB)

if plt is not None:
    plt.figure(figsize=(12, 6))
    plt.subplot(1, 2, 1)
    plt.imshow(reference_rgb)
    plt.title("Golden reference")
    plt.axis("off")

    plt.subplot(1, 2, 2)
    plt.imshow(test_rgb)
    plt.title("Test PCB")
    plt.axis("off")

    plt.tight_layout()
    plt.show()
else:
    print("matplotlib is not installed; skipping image display.")
