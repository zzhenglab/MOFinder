# Holdout calibration

[Calculation code](../../../src/mofinder/evaluation/calibration.py) scores the three models in one [prediction CSV](predictions.csv), aligned to all 2,595 released holdout reactions. Run from the repository root after installation:

```bash
python -m mofinder.evaluation.calibration --bootstrap 5000
```

| Model | ECE (10 bins) | Brier |
| --- | ---: | ---: |
| Fine-tuned open weight LLM (MOFinder) | 0.0243 | 0.1209 |
| Base open weight LLM (gpt-oss-20b) | 0.3347 | 0.3657 |
| Base proprietary LLM (GPT-4.1) | 0.3605 | 0.3802 |

ECE weights each bin's absolute gap between mean P probability and observed positive fraction by its record count. Brier is `mean((p-y)**2)`, with P = 1. Bins are equal-width, left-closed/right-open; the last includes 1. Predictions use `p >= 0.5`. DOI bootstrap draws are shared across models (seed 20261002). Missing probabilities and duplicate inputs are rejected.

The CSV includes labels, probabilities, predictions, per-record Brier terms and available P/N log probabilities. GPT-4.1 follows Step 6b (`temperature=0`, `top_p=1`, `max_tokens=2`, `seed=7`), with top-token coverage increased to 20: 2,573 pairs are directly observed; 22 bounded tails agree to 12 decimals. Blank log probabilities are unobserved, not zeros. MOFinder uses the step-4500 archive; base gpt-oss-20b uses GGUF MXFP4. [Provenance](provenance.json) records identities, bounds and limitations.

See [prediction workflow](../../../docs/holdout_evaluation.md#calibration-of-saved-predictions) and [SI Section S6 addition](../../../docs/si/calibration_model_evaluation.pdf) for equations, uncertainty, bin sensitivity and interpretation. The PDF is the insertion-ready subsection; Figure Sx/Table Sx await manuscript numbering.
