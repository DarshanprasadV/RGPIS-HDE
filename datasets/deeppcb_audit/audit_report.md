# DeepPCB dataset audit

## Scope and result

Audited the supplied `DeepPCB-master/PCBData` directory in place. The audit did not modify its files.

- 1,500 test images and 1,500 annotation files across 11 board-design directories.
- 1,501 template images; one template has no corresponding test image.
- All 1,500 test images are 640 × 640. All corresponding templates and labels were present, and the audit reported no malformed boxes, unknown class IDs, or out-of-bounds boxes.
- 10,013 annotated defect boxes across six classes.
- All supplied `trainval.txt` / `test.txt` entries resolve to the 1,500 suffixed test images and annotation files in this checkout. Their split is image-level: seven design directories appear in both lists, so it does not provide a design-held-out evaluation.

## Class counts

DeepPCB's documented source IDs and generated zero-based YOLO IDs are:

| YOLO ID | Source ID | Class | Boxes |
|---:|---:|---|---:|
| 0 | 1 | open | 1,942 |
| 1 | 2 | short | 1,506 |
| 2 | 3 | mousebite | 1,965 |
| 3 | 4 | spur | 1,625 |
| 4 | 5 | copper | 1,474 |
| 5 | 6 | pin-hole | 1,501 |

## Design-held-out split

The generated split keeps every design directory wholly within one set. The seed is 2026; the selected assignment minimizes the difference between the target 70/15/15 proportions and image totals, with two designs in validation and two in test.

| Split | Designs | Images | Boxes |
|---|---:|---:|---:|
| Train | 7 | 1,048 | 7,444 |
| Validation | 2 | 227 | 1,218 |
| Test | 2 | 225 | 1,351 |

| Design directory | Split | Images |
|---|---|---:|
| group00041 | Train | 221 |
| group12000 | Train | 14 |
| group12100 | Test | 146 |
| group12300 | Train | 98 |
| group13000 | Train | 216 |
| group20085 | Train | 325 |
| group44000 | Train | 100 |
| group50600 | Test | 79 |
| group77000 | Validation | 107 |
| group90100 | Train | 74 |
| group92000 | Validation | 120 |

The split contains all six classes in each set. It is a small design-wise evaluation with only two held-out designs per validation/test set; report that limitation when training and evaluating a model.

## Terms and attribution

The supplied DeepPCB README describes the dataset as research-use-only. The adjacent MIT license applies to the repository's software and does not establish broader rights for the image dataset. Obtain permission from the dataset authors before commercial use or redistribution. This audit preserves the original source location and only generates local metadata, labels, and symlinks.

## Generated files

See `summary.json`, `manifest.csv`, and `issues.csv` for machine-readable detail. YOLO labels use normalized center-based `xywh` boxes and zero-based IDs. `yolo/data.yaml` points to `yolo/images/{train,val,test}`; those images are symlinks into the source checkout, and the matching labels are under `yolo/labels/`.
