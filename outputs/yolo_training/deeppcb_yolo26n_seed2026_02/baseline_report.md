# DeepPCB YOLO26n baseline report

## Run

- Model: pretrained YOLO26n, fine-tuned for six DeepPCB classes.
- Runtime: Ultralytics 8.4.215, PyTorch 2.15.0, Apple M5 MPS.
- Seed: 2026; image size: 640; batch size: 8; workers: 0.
- Training stopped at epoch 74 by early stopping; best validation checkpoint was epoch 55.
- Train/validation/test counts: 1,048 / 227 / 225 test images, kept by whole board-design directories.
- The best checkpoint is `weights/best.pt`; training curves and configuration are in this directory.

## Held-out test results

Test set: 225 images, 1,351 labelled boxes from board designs `group12100` and `group50600`.

| Class | Precision | Recall | AP50 | AP50–95 |
|---|---:|---:|---:|---:|
| All | 0.950 | 0.952 | 0.975 | 0.736 |
| Open | 0.747 | 0.935 | 0.904 | 0.632 |
| Short | 0.994 | 0.860 | 0.983 | 0.695 |
| Mousebite | 0.973 | 0.980 | 0.990 | 0.710 |
| Spur | 0.995 | 0.950 | 0.988 | 0.745 |
| Copper | 0.994 | 1.000 | 0.993 | 0.850 |
| Pin-hole | 0.995 | 0.989 | 0.995 | 0.786 |

Aggregate values are also stored in `test_metrics.json`; the test evaluation's plots and prediction samples are in the sibling `deeppcb_yolo26n_seed2026_02_heldout_test/` folder.

## Interpretation and limits

This completes a first image-only YOLO baseline and its held-out evaluation. The very high test scores should be treated as preliminary: the test set contains only two held-out design directories, and DeepPCB notes that some labelled defects were artificially augmented. Inspect false positives and false negatives in the saved confusion matrix and prediction samples, and use additional independent PCB designs before making deployment or broad generalisation claims. This is the baseline stage only; reference-guided YOLO and later anomaly, risk, and process-memory phases are not included.
