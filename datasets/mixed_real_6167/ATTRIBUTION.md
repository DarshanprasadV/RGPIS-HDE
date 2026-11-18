# Dataset attribution and scope

This training set combines the project’s audited DeepPCB training split with compatible samples from DsPCBSD+.

## DsPCBSD+

Source: [DsPCBSD+ on Figshare](https://doi.org/10.6084/m9.figshare.24970329), released under **CC BY 4.0**. Attribute the original dataset authors and cite the linked dataset record when redistributing covered material. The upstream project is [PCB_Defect_Detection](https://github.com/kikopapa/PCB_Defect_Detection).

Only images with annotations entirely within the compatible classes were included. The source labels map as follows: OP → open, SH → short, MB → mousebite, SP → spur, and SC → copper. Images containing HB, CS, CFO, or BMFO annotations were excluded so that defects outside this model’s six-class taxonomy are not mislabeled as background. One additional image with invalid box coordinates was excluded. The original source partitions are recorded in `manifest.csv`.

## DeepPCB

The project’s audited design-wise DeepPCB split supplies the training images plus unchanged validation and held-out test images. DeepPCB’s accompanying README restricts dataset use to research; that restriction applies to this mixed dataset and its model unless separate rights are obtained.

## Split and counts

- Training: 1,048 DeepPCB + 5,118 DsPCBSD+ = 6,166 real images.
- Validation: 227 DeepPCB images.
- Test: 225 DeepPCB images, held out by design as in the project audit.
- DsPCBSD+ images are used only for training, including compatible images from both supplied source partitions.

See `summary.json` and `manifest.csv` for generated counts and per-image provenance.
