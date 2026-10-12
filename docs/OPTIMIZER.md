# Dataset → evaluation → optimizer

The optimizer rewrites a workflow's **field descriptions** to raise accuracy against your ground
truth. You need a dataset first.

## 1. Fill the datasets

```bash
uv run af.py dataset order_form          # samples + ground truth into each workflow's dataset
```

For real documents, first make the ground truth (`GROUND_TRUTH.md`), then pass the PDFs:
`uv run af.py dataset order_form our_docs/order_forms/*.pdf`.

## 2. Measure the baseline

```bash
uv run af.py eval order_form
```

This prints accuracy per workflow and a link to each evaluation, where you see accuracy per field.
An evaluation re-runs extraction on every dataset document, so it costs credits.

## 3. Run the optimizer (in the app)

The optimizer is not in the API yet. For each workflow you want to improve:

1. Open the workflow → **Health** → **Optimizer** → **Run optimization**.
2. Choose the iterations (1–10; 3 is a good start). It scores the whole dataset on overall accuracy.
3. Each iteration proposes new field descriptions and re-scores them. A change is kept only if
   accuracy beats the best so far.
4. The best iteration becomes a **new workflow version** automatically. The run page shows accuracy
   per iteration and the description changes, field by field.

Start with the workflow whose fields score worst in `reports/<type>.md`. On the accident
statement, that is usually the circumstances or the drivers.

Or ask *annie* (the assistant in the app): "improve this workflow".

## 4. Bring the improvements back

The optimizer changes the workflow in your workspace, not the JSON in this repo. Copy the new
descriptions from the run page into `workflows/<type>/*.json`, so the repo and the workspace agree.
Then re-run `af.py run` and `af.py score` on documents **not** in the dataset. That is the number to
report.
