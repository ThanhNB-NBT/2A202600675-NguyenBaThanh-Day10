# Corruption Impact Report

## Metrics Comparison

| Metric | Baseline | Corrupted | Repaired |
| --- | ---: | ---: | ---: |
| Samples | 8 | 8 | 8 |
| Retrieval hit rate | 1.0000 | 0.6250 | 1.0000 |
| Mean token F1 | 1.0000 | 0.6840 | 1.0000 |
| Judge accuracy | 1.0000 | 0.6250 | 1.0000 |
| Mean judge score | 5 | 3.5000 | 5 |

## Quality Comparison

- Corrupted quality success: False (3 failed checks)
- Repaired quality success: True (0 failed checks)

## Freshness Comparison

- Corrupted stale rows: 5 / 23
- Repaired stale rows: 0 / 23

## Interpretation

Corruption is expected to reduce retrieval or answer quality because records are removed, duplicated, blanked, noised, and made stale.
Repair rebuilds the clean dataset from the raw source snapshot, then rebuilds the index and evaluation artifacts.
