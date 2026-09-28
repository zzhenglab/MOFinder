# Reaction-condition holdout

The final holdout dataset is [data/processed_data_json/holdout.jsonl](../../data/processed_data_json/holdout.jsonl), beside its companion [training set](../../data/processed_data_json/train.jsonl). It contains 2,595 records: 1,320 P and 1,275 N. Both files preserve the original JSONL bytes; file identities are recorded in [the dataset manifest](../../data/processed_data_json/manifest.json).

[Split assignments and parameters](../../data/processed_data_json/README.md) identify the source rows and chemical groups in each partition.

The evaluator reads the assistant label as the reference answer and excludes it from model requests. Its parsing, P/N probability extraction, and reported metrics follow the source holdout evaluation notebook. See [the evaluation guide](../../docs/holdout_evaluation.md).
