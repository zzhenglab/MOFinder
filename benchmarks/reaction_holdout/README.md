# Reaction-condition holdout

The final holdout dataset is [data/processed_data_json/holdout.jsonl](../../data/processed_data_json/holdout.jsonl), beside its companion [training set](../../data/processed_data_json/train.jsonl). It contains 2,595 records: 1,320 P and 1,275 N.

See [split preparation](../../docs/datasets.md) for grouping rules and generated assignment files.

The evaluator reads the assistant label as the reference answer and excludes it from model requests. See [the evaluation guide](../../docs/holdout_evaluation.md).

