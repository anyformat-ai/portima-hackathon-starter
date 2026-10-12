"""Hackathon CLI: create the anyformat workflows, run documents, score them, push datasets, run evals.

    uv run af.py create accident_statement
    uv run af.py run accident_statement
    uv run af.py score accident_statement
    uv run af.py dataset accident_statement
    uv run af.py eval accident_statement
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
WORKFLOWS = ROOT / "workflows"
SAMPLE_DIRS = {"accident_statement": ROOT / "samples/accident_statements", "order_form": ROOT / "samples/order_forms"}
TRUTH_DIRS = {"accident_statement": ROOT / "ground_truth/accident_statements", "order_form": ROOT / "ground_truth/order_forms"}
RESULTS = ROOT / "results"
REPORTS = ROOT / "reports"
STATE = ROOT / ".anyformat/workflows.json"
THRESHOLDS = [0, 50, 60, 70, 80, 85, 90, 95, 98]
SUBMIT_GAP_S = 1.1  # the submission endpoints allow 60 calls per minute

Fields = dict[str, Any]


def client():
    from anyformat.sdk import Client

    load_dotenv(ROOT / ".env")
    key = os.environ.get("ANYFORMAT_API_KEY")
    if not key:
        sys.exit("Set ANYFORMAT_API_KEY in .env (mint one at https://app.anyformat.ai/api-key)")
    return Client(api_key=key, base_url=os.environ.get("ANYFORMAT_BASE_URL", "https://api.anyformat.ai"), timeout=120)


def definitions(doc_type: str) -> dict[str, dict]:
    files = sorted((WORKFLOWS / doc_type).glob("*.json"))
    if not files:
        sys.exit(f"No workflow definitions in workflows/{doc_type}/")
    return {re.sub(r"^\d+_", "", f.stem): json.loads(f.read_text()) for f in files}


def schema_fields(definition: dict) -> list[dict]:
    extract = next(n for n in definition["nodes"] if n["type"] == "extract")
    return extract["extraction_schema"]["fields"]


def field_types(doc_type: str) -> dict[str, str]:
    return {f["name"]: f["data_type"] for d in definitions(doc_type).values() for f in schema_fields(d)}


def load_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def workflow_ids(doc_type: str) -> dict[str, str]:
    ids = load_state().get(doc_type)
    if not ids:
        sys.exit(f"No workflows yet for {doc_type}. Run: uv run af.py create {doc_type}")
    return ids


def documents(doc_type: str, paths: list[str]) -> list[Path]:
    if paths:
        return [Path(p) for p in paths]
    return sorted(SAMPLE_DIRS[doc_type].glob("*.pdf"))


# --- create -----------------------------------------------------------------------------------


def cmd_create(args: argparse.Namespace) -> None:
    from anyformat.workflow.definition import WorkflowDefinition

    c = client()
    state = load_state()
    ids = state.setdefault(args.doc_type, {})
    team = os.environ.get("TEAM_NAME", "").strip()
    for group, definition in definitions(args.doc_type).items():
        if group in ids and not args.force:
            print(f"= {group}: exists ({ids[group]})")
            continue
        if team:
            definition = {**definition, "name": f"[{team}] {definition['name']}"}
        wf = c.create_workflow(WorkflowDefinition.model_validate(definition))
        ids[group] = wf.id
        print(f"+ {group}: {wf.id}  https://app.anyformat.ai/workflows/{wf.id}")
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2) + "\n")


# --- run --------------------------------------------------------------------------------------


def results_of(raw: dict) -> dict:
    return raw.get("results") or raw


def merge(group_results: dict[str, dict]) -> dict:
    fields: Fields = {}
    validations, links = [], {}
    for group, res in group_results.items():
        links[group] = res.get("verification_url")
        for extraction in res.get("extractions") or []:
            fields.update(extraction.get("fields") or {})
            validations += [{**v, "group": group} for v in extraction.get("validations") or []]
    return {"fields": fields, "validations": validations, "verification_urls": links}


def cmd_run(args: argparse.Namespace) -> None:
    c = client()
    ids = workflow_ids(args.doc_type)
    out_dir = RESULTS / args.doc_type
    out_dir.mkdir(parents=True, exist_ok=True)
    docs = documents(args.doc_type, args.files)
    pending = []
    for doc in docs:
        for group, wid in ids.items():
            pending.append((doc, group, c.upload(wid, doc, on_conflict="rename").run()))
            print(f"submitted {doc.name} -> {group}")
            time.sleep(SUBMIT_GAP_S)

    def wait(item):
        doc, group, run = item
        try:
            return doc, group, run.wait(timeout=900).raw
        except Exception as exc:  # one failed run should not lose the others
            print(f"! {doc.name} -> {group}: {exc}")
            return doc, group, {}

    by_doc: dict[Path, dict[str, dict]] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for doc, group, raw in pool.map(wait, pending):
            by_doc.setdefault(doc, {})[group] = results_of(raw)
    for doc, groups in by_doc.items():
        merged = merge(groups)
        (out_dir / f"{doc.stem}.json").write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n")
        failed = [v for v in merged["validations"] if v.get("status") == "fail"]
        print(f"\n{doc.name}: {len(merged['fields'])} fields, {len(failed)} failed validations")
        for v in failed:
            print(f"  ✗ [{v.get('severity')}] {v.get('rule_id')}: {v.get('detail')}")
        for group, url in merged["verification_urls"].items():
            print(f"  review {group}: {url}")
    print(f"\nWrote {len(by_doc)} result files to {out_dir.relative_to(ROOT)}/. Next: uv run af.py score {args.doc_type}")


# --- score ------------------------------------------------------------------------------------


def flatten(truth: dict, prefix: str = "") -> Fields:
    flat: Fields = {}
    for key, value in truth.items():
        name = f"{prefix}_{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(flatten(value, name))
        else:
            flat[name] = value
    return flat


def parse_date(text: str) -> str | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_number(text: str) -> float | None:
    cleaned = re.sub(r"[^\d,.\-]", "", text)
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".") if cleaned.rfind(",") > cleaned.rfind(".") else cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize(value: Any, data_type: str) -> Any:
    """Bring a value to a canonical form so formatting differences don't count as errors."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip()
    if text in {"", "-", "—", "null", "None", "n/a"}:
        return None
    if data_type == "boolean":
        return text.lower() in {"true", "yes", "oui", "ja", "1", "x"}
    if data_type in {"integer", "float"}:
        number = parse_number(text)
        return round(number, 2) if number is not None else text.lower()
    if data_type == "date":
        return parse_date(text) or text
    folded = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"\s+", " ", folded).strip(" .,;")


def same(truth: Any, predicted: Any, data_type: str, nested: dict[str, str] | None = None) -> bool:
    if data_type == "object":
        rows_t = sorted(json.dumps({k: normalize(v, nested.get(k, "string")) for k, v in r.items()}, sort_keys=True)
                        for r in truth or [])
        rows_p = sorted(json.dumps({k: normalize(v, nested.get(k, "string")) for k, v in r.items()}, sort_keys=True)
                        for r in predicted or [])
        return rows_t == rows_p
    return normalize(truth, data_type) == normalize(predicted, data_type)


def predicted_value(field: Any) -> tuple[Any, float | None]:
    """(value, confidence) from a result field; object fields come back as a list of row dicts."""
    if isinstance(field, list):
        rows = [{k: (cell.get("value_override") or cell.get("value")) for k, cell in row.items()} for row in field]
        confs = [cell.get("confidence") for row in field for cell in row.values() if cell.get("confidence") is not None]
        return rows, (min(confs) if confs else None)
    if not field:
        return None, None
    return field.get("value_override") or field.get("value"), field.get("confidence")


def cmd_score(args: argparse.Namespace) -> None:
    types = field_types(args.doc_type)
    nested = {f["name"]: {c["name"]: c["data_type"] for c in f.get("nested_fields", [])}
              for d in definitions(args.doc_type).values() for f in schema_fields(d)}
    rows = []
    for result_file in sorted((RESULTS / args.doc_type).glob("*.json")):
        truth_file = TRUTH_DIRS[args.doc_type] / result_file.name
        if not truth_file.exists():
            print(f"skip {result_file.name}: no ground truth")
            continue
        truth = flatten(json.loads(truth_file.read_text()))
        predicted = json.loads(result_file.read_text())["fields"]
        for name, data_type in types.items():
            value, conf = predicted_value(predicted.get(name))
            ok = same(truth.get(name), value, data_type, nested.get(name))
            rows.append({"document": result_file.stem, "field": name, "truth": truth.get(name), "predicted": value,
                         "confidence": conf, "correct": ok})
    if not rows:
        sys.exit(f"No results to score. Run: uv run af.py run {args.doc_type}")
    REPORTS.mkdir(exist_ok=True)
    with (REPORTS / f"{args.doc_type}_fields.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows([{**r, "truth": json.dumps(r["truth"], ensure_ascii=False), "predicted": json.dumps(r["predicted"], ensure_ascii=False)} for r in rows])
    report = render_report(args.doc_type, rows)
    (REPORTS / f"{args.doc_type}.md").write_text(report)
    print(report)


def render_report(doc_type: str, rows: list[dict]) -> str:
    total = len(rows)
    correct = sum(r["correct"] for r in rows)
    lines = [f"# {doc_type}: field accuracy", "", f"Documents: {len({r['document'] for r in rows})} · "
             f"field values: {total} · accuracy: **{correct / total:.1%}**", "",
             "## Confidence threshold sweep", "",
             "Auto-accept every field at or above the threshold; the rest go to a broker.", "",
             "| Threshold | Auto-accepted | Accuracy of auto-accepted | Errors that slip through |", "|---|---|---|---|"]
    for t in THRESHOLDS:
        accepted = [r for r in rows if (r["confidence"] or 0) >= t]
        acc = sum(r["correct"] for r in accepted) / len(accepted) if accepted else 0
        slipped = sum(not r["correct"] for r in accepted)
        lines.append(f"| ≥ {t} | {len(accepted) / total:.0%} | {acc:.1%} | {slipped} |")
    lines += ["", "## Per field (worst first)", "", "| Field | Accuracy | Mean confidence | Misses |", "|---|---|---|---|"]
    by_field: dict[str, list[dict]] = {}
    for r in rows:
        by_field.setdefault(r["field"], []).append(r)
    stats = []
    for name, rs in by_field.items():
        acc = sum(r["correct"] for r in rs) / len(rs)
        confs = [r["confidence"] for r in rs if r["confidence"] is not None]
        misses = "; ".join(f"{r['document']}: {r['predicted']!r} ≠ {r['truth']!r}" for r in rs if not r["correct"])[:160]
        stats.append((acc, name, sum(confs) / len(confs) if confs else None, misses))
    for acc, name, conf, misses in sorted(stats):
        lines.append(f"| `{name}` | {acc:.0%} | {conf:.0f} | {misses} |" if conf is not None else f"| `{name}` | {acc:.0%} | - | {misses} |")
    return "\n".join(lines) + "\n"


# --- dataset & eval ---------------------------------------------------------------------------


def api_value(value: Any, data_type: str) -> Any:
    """Ground truth for the dataset API: every scalar is a string or null."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if data_type == "float":
        return f"{float(value):.2f}"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def api_ground_truth(definition: dict, truth: Fields) -> dict:
    out = {}
    for f in schema_fields(definition):
        if f["data_type"] == "object":
            kids = {c["name"]: c["data_type"] for c in f["nested_fields"]}
            out[f["name"]] = [{k: api_value(row.get(k), t) for k, t in kids.items()} for row in truth.get(f["name"]) or []]
        else:
            out[f["name"]] = api_value(truth.get(f["name"]), f["data_type"])
    return out


def cmd_ground_truth(args: argparse.Namespace) -> None:
    defs = definitions(args.doc_type)
    out_root = ROOT / "ground_truth/_api" / args.doc_type
    for truth_file in sorted(TRUTH_DIRS[args.doc_type].glob("*.json")):
        flat = flatten(json.loads(truth_file.read_text()))
        known = {f["name"] for d in defs.values() for f in schema_fields(d)}
        extra = sorted(k for k in set(flat) - known if not k.startswith("_"))
        missing = sorted(known - set(flat))
        if extra:
            print(f"! {truth_file.name}: keys not in any workflow: {extra}")
        if missing:
            print(f"! {truth_file.name}: workflow fields with no ground truth (sent as null): {missing}")
        if flat.get("_unsure"):
            print(f"? {truth_file.name}: still has _unsure keys for a broker to check: {flat['_unsure']}")
        for group, definition in defs.items():
            target = out_root / group / truth_file.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(api_ground_truth(definition, flat), indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote dataset-format ground truth to {out_root.relative_to(ROOT)}/<group>/")


def cmd_dataset(args: argparse.Namespace) -> None:
    c = client()
    ids = workflow_ids(args.doc_type)
    defs = definitions(args.doc_type)
    for doc in documents(args.doc_type, args.files):
        truth_file = TRUTH_DIRS[args.doc_type] / f"{doc.stem}.json"
        if not truth_file.exists():
            print(f"skip {doc.name}: no ground_truth/{truth_file.parent.name}/{truth_file.name}")
            continue
        flat = flatten(json.loads(truth_file.read_text()))
        for group, wid in ids.items():
            c.upload_to_dataset(wid, doc, ground_truth=api_ground_truth(defs[group], flat), on_conflict="rename")
            print(f"+ {doc.name} -> {group} dataset")
            time.sleep(SUBMIT_GAP_S)
    print(f"\nDatasets ready. Next: uv run af.py eval {args.doc_type}, or Health -> Optimizer in the app.")


def cmd_eval(args: argparse.Namespace) -> None:
    c = client()
    ids = workflow_ids(args.doc_type)
    launched = {}
    for group, wid in ids.items():
        launched[group] = (wid, c.launch_eval(wid).eval_id)
        time.sleep(SUBMIT_GAP_S)
    print("Evals launched; polling...")
    while launched:
        time.sleep(15)
        for group, (wid, eval_id) in list(launched.items()):
            e = c.get_eval(wid, eval_id)
            if e.status in {"processed", "error"}:
                acc = f"{e.accuracy:.1%}" if e.accuracy is not None else "-"
                print(f"{group}: {e.status} accuracy={acc} matched={e.matched} mismatched={e.mismatched} "
                      f"https://app.anyformat.ai/workflows/{wid}/evals/{eval_id}")
                del launched[group]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, fn, help_ in [
        ("create", cmd_create, "create the workflows in workflows/<doc_type>/ in your workspace"),
        ("run", cmd_run, "run documents through every workflow of a doc type and merge the fields"),
        ("score", cmd_score, "compare results/ with ground_truth/ field by field, plus a threshold sweep"),
        ("ground-truth", cmd_ground_truth, "write ground truth in the dataset API format, for inspection"),
        ("dataset", cmd_dataset, "upload documents + ground truth to each workflow's dataset"),
        ("eval", cmd_eval, "launch an eval on each workflow's dataset and wait for accuracy"),
    ]:
        p = sub.add_parser(name, help=help_)
        p.add_argument("doc_type", choices=sorted(SAMPLE_DIRS))
        if name in {"run", "dataset"}:
            p.add_argument("files", nargs="*", help="PDFs to use (default: every sample of the doc type)")
        if name == "create":
            p.add_argument("--force", action="store_true", help="create again even if already created")
        p.set_defaults(fn=fn)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
