# What you'll see in app.anyformat.ai

Everything `af.py` does lands in your workspace. This is where to find it.

## Workflows (`/workflows`)

After `af.py create`, your workflows are listed here, e.g. *Car order form · 2 vehicle, options &
price*. Prefix them with your team by setting `TEAM_NAME` in `.env` before `create`.

Open one and use the tabs at the top:

| Tab | What it shows | Use it to |
|---|---|---|
| **Data** | One row per document, one column per field | Scan results; export |
| **Studio** | The graph: Parse (Fast) → Extract → Validate | Edit field descriptions and rules by hand |
| **Health** | Overview, Datasets, Evaluations, Optimizer | Ground truth, accuracy, automatic improvement |

## One document (the review link `af.py run` prints)

`results.verification_url` opens the document view. This is where a broker validates.

- **Extraction tab:** every field with its value and confidence. Click a field to highlight where it
  was read on the page; click the page to find the field.
- **Validation tab:** each rule as pass, fail or inconclusive, with the values it compared. On
  `order_05_modern_nl_bad_total.pdf`: *Net + VAT = total*: fail, "sum(operands) = 51594.4,
  expected 51694.4".
- **Correcting a value:** the field is marked `human_edited` and the API returns it in
  `value_override`. `af.py score` prefers the override, so a broker's corrections count.
- **Accepting a value:** marks it `human_verified`. A fully verified document can be added to the
  dataset with **Add to dataset**.

## What the broker loop looks like

1. A document arrives and runs.
2. Fields at or above the threshold you picked from `reports/<type>.md` go straight to your
   database.
3. Fields below the threshold, and documents with a failed `error` rule, open in the document view.
4. The broker fixes or accepts only those fields. Every correction is new ground truth (see
   `OPTIMIZER.md`).

Example from a scanned sample accident statement:
- **Policyholder fields:** read at confidence 89–90, all correct.
- **The plate:** read as `2-HgL-344` at confidence 55. The truth is `2-GZL-344`. Two rules flagged it:
  - *plate looks Belgian*
  - *plate confidence ≥ 80*

  So it goes to review, and the correct fields don't.

## Health

- **Datasets:** the documents you uploaded with `af.py dataset`, each with its ground truth.
- **Evaluations:** each `af.py eval`: accuracy, matched and mismatched fields, per field.
- **Optimizer:** see `OPTIMIZER.md`.

## Credits and keys

- `/usage`: credits used and left.
- `/api-key`: create or revoke keys.
