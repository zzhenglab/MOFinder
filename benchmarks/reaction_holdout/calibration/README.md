# ECE and Brier calculations

[Code](../../../src/mofinder/evaluation/calibration.py) and [one prediction CSV](predictions.csv) for three models on the same 2,595 holdout reactions. From the repository root after installation:

```bash
python -m mofinder.evaluation.calibration --bootstrap 5000
```

ECE uses ten equal-width bins and weights each absolute probability/positive-fraction gap by its record count. Brier is `mean((p-y)**2)`, with P = 1. Predictions use `p >= 0.5`; the last bin includes 1. Optional DOI bootstrap intervals use shared draws across models (seed 20261002).

The CSV includes probabilities, predictions, per-record Brier terms and available token log probabilities. Blank log probabilities are unobserved, not zeros; 22 GPT-4.1 tails have explicit bounds. [Provenance](provenance.json) records model identities, inference settings and limitations. The scorer rejects missing probabilities and duplicate inputs.
