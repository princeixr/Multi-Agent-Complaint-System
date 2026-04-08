# Classification evaluation slices

Slice complaints so accuracy and calibration can be compared across **data regimes**, not only overall accuracy.

## Recommended slices

| Slice | Definition | Why it matters |
| ----- | ---------- | -------------- |
| `narrative_absent` | No narrative or fewer than 10 characters | Portal-led classification; higher mislabel risk if tools or mapping are weak. |
| `long_narrative` | Narrative length ≥ 10 | Baseline text-heavy path. |
| `multi_issue_heuristic` | Narrative contains phrases like “another issue”, “in addition” | Multi-problem complaints; single-label taxonomy is stressed. |
| `structured_plus_narrative` | `cfpb_product` and `cfpb_issue` present and narrative ≥ 10 | Structured vs free-text reconciliation; tension and conflict scores apply. |
| `high_conflict` | From audit: `situation_assessment.conflict_score` ≥ 0.55 (post-run) | Mismatch between portal selections and narrative tokens. |
| `review_recommended` | `classification.review_recommended` true | Operational queue; link to human adjudication outcomes when available. |

## Calibration

Track **confidence vs error** within each slice (when gold labels exist):

- Bin predictions by `confidence` (e.g. 0.5–0.6, 0.6–0.7, …).
- For each bin, compute empirical error rate (wrong product or wrong issue).
- Adjust production thresholds using this reliability curve, not raw model scores alone.

## Harness

`app/evals/run_evals.py` reports aggregate metrics and a `slice_counts` object with per-slice `n`, `correct_product`, and `correct_issue`. Extend datasets with optional columns `cfpb_product`, `cfpb_issue`, etc., to populate structured slices.
