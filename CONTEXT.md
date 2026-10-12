# Context: Portima document intelligence hackathon

Prepared by anyformat for Portima engineering. This file and the slide deck (`docs/context-pack.pdf`) say the same
thing: the slides are for people, this file is for coding agents.

## The challenge

Brokers retype data from two high-volume documents. Turn them into structured data:

- **European accident statement** (constat amiable / aanrijdingsformulier): the parties, vehicles,
  insurers, the 17 circumstance boxes, impact points and the sketch needed to open a claim. Usually
  handwritten, in French or Dutch, often a faded scan.
- **Car order form:** the buyer and vehicle data needed to create a new object. Typed, but every
  dealer has its own layout.

The brief asks for three things:
- measure accuracy field by field
- set confidence thresholds
- design how a broker validates the uncertain results

## The pipeline

Each workflow is one chain:

```
parse (mode "lite", shown as "Fast" in the app)
  → extract (mode "standard")
  → validate (deterministic rules)
```

- **Fast parse:** OCR plus layout. It returns blocks (tables, text, pictures), each with a box,
  a type and a confidence. Tables come down to the cell.
- **Standard extract:** one typed value per schema field, with a confidence and evidence.
- **Validate:** rules checked in code, free. They label a run and never block it.
- **About 20 fields per extract:** a workflow holds one extract, so a large schema is split into
  several workflows. `af.py run` merges them back into one record per document. The accident
  statement uses six workflows and the order form two; see `workflows/`.

## The hierarchy: page → block → cell → field

| Level | What it is | Where in the result |
|---|---|---|
| Page | The scan as it arrives | `results.parse` |
| Block | A region with `bbox` (page fractions), `type`, `parse_confidence` | `results.parse.blocks[]` |
| Cell | One cell of a table block, e.g. `r13c1` | `blocks[].rows[][].cell_id` |
| Field | The value asked for, with confidence and the text it was read from | `results.extractions[].fields` |

A real, trimmed example is in `examples/parse_accident_05_scan.json`.

## The data contract (`GET /v3/runs/{run_id}/`)

```json
"results": {
  "extractions": [{
    "fields": {
      "vehicle_a_insurer_policy_number": {
        "value": "60.237235", "confidence": 89,
        "evidence": [{"text": "N° de contrat 60.237235", "page_number": 1}],
        "value_override": null, "verification_status": "not_verified"
      },
      "options": [{"code": {"value": "TOW", "confidence": 96}, "price_excl_vat": {"value": "980.0"}}]
    },
    "validations": [{"rule_id": "net-plus-vat-is-total", "severity": "error", "status": "fail", "detail": "..."}]
  }],
  "parse": {"blocks": [{"id": "p1_b3", "type": "table", "bbox": {"x0": 0.03, "y0": 0.14, "x1": 0.36, "y1": 0.61}}]},
  "verification_url": "https://app.anyformat.ai/workflows/.../files/..."
}
```

- `value` is always a string or null. Cast it yourself.
- `confidence` is 0–100, per field.
- When `value_override` is set, it holds a reviewer's correction. Prefer it.
- Object fields (lists such as `options`) come back as a list of rows of fields, one level deep.
- `validations[].status` is `pass`, `fail` or `inconclusive`.
- `verification_url` opens the document in the review workspace.

## What you can build

| App | What it uses |
|---|---|
| Claim intake: mailbox or upload → run → auto-create when fields clear the threshold, queue the rest | `confidence`, `validations` |
| Broker review screen: only uncertain fields, each beside its highlighted box | `evidence`, `parse.blocks[].bbox` |
| Vehicle object from an order form, totals checked before writing | object fields, arithmetic rules |
| Broker assistant agent that reads a constat and drafts the claim, citing cells | MCP tools, `evidence` |

Start from `uv run af.py run <doc_type>`: it writes merged results per document to `results/`.

## What comes with it

These are the parts you would otherwise have to build yourself. Use the list as a checklist,
whichever way you build:

- **Grounding:** every value tied to a block, a cell and a box on the page.
- **Per-field confidence:** a number to route on.
- **Layout parse of scans:** tables, checkboxes and handwriting come back as structure.
- **Deterministic validation rules:** totals, formats, dates, ranges, regex, confidence and CEL
  expressions.
- **A review workspace:** reviewers highlight, accept and correct; corrections are kept as
  `value_override`.
- **Datasets, evals and the optimizer:** accuracy against your ground truth, plus field
  descriptions improved automatically.
- **Versioned workflows:** each change is a new version, and every result records which version
  produced it.

## Measuring it

- **Ground truth:** `ground_truth/` holds the answers for the samples. For real documents, see
  `docs/GROUND_TRUTH.md`: an agent drafts the answers and a broker checks them.
- **Scoring:** `uv run af.py score <doc_type>` normalizes values before comparing, so
  `"21/03/2026"` = `"2026-03-21"` and `"€ 1 450,00"` = `1450`. It reports accuracy per field and a
  confidence threshold sweep in `reports/`.
- **Datasets and evals:** `af.py dataset` uploads ground truth to each workflow; `af.py eval`
  measures it there.
- **Optimizer:** runs in the app only (Health → Optimizer). See `docs/OPTIMIZER.md`.
- **Your own pipeline:** write its output in the shape of `results/<doc_type>/*.json` and
  `af.py score` measures it with the same script.

## Limits

- One extract per workflow; keep it to about 20 fields.
- Rate limits: 60 submissions per minute (uploads, runs, dataset uploads, evals) and 600 reads per
  minute. A 429 comes with `Retry-After`.
- Nesting is one level deep: an object field is a list of rows, and a row cannot contain another
  object.
- Editing `workflows/*.json` does not change the live workflow. Re-create it
  (`af.py create --force`) or edit it in Studio.
- Cost is about 47 credits per page per workflow (fast parse 12 + standard extract 35);
  deterministic rules are free.

## Glossary

| Term | Meaning |
|---|---|
| Block | A region of the page, with a box and a type |
| Cell | One cell of a table block |
| Field | A value you asked for, typed, with a confidence |
| Evidence | The text and page a value was read from |
| Threshold | Confidence at or above which a field skips review |
| Dataset | Documents with their correct answers |
| Eval | A workflow's accuracy on its dataset |

## Links

- Docs: https://docs.anyformat.ai (see "Connect your agent" and "How credits work")
- API keys: https://app.anyformat.ai/api-key
- MCP server: `https://api.anyformat.ai/mcp` (configured in `.mcp.json`)
- Python SDK: `pip install anyformat`, then `from anyformat.sdk import Client`
