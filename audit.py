"""Compare saved and replayed citations against the reviewed development cases."""

import argparse
import json
from pathlib import Path

from evaluate import replay_record
from verify import parse_number, verify

FIXTURE = Path(__file__).parent / "data" / "dev-evidence.json"


def scores(records: list[tuple[dict, dict]]) -> dict:
    cited = supported = accepted = correct_accepted = reviewed_unknown = 0
    for case, record in records:
        prediction = record.get("prediction") or {}
        selected = [prediction.get("row"), prediction.get("column")]
        valid_cell = prediction.get("status") == "found" and selected in case["cells"]
        if valid_cell:
            row, column = selected
            try:
                valid_cell = parse_number(record["table"][row][column]) == parse_number(prediction["value"])
            except (KeyError, ValueError):
                valid_cell = False
        passed = record["verification"]["passed"]
        resolved = case["scale"] is not None and prediction.get("scale") == case["scale"]
        cited += valid_cell
        supported += valid_cell and resolved
        accepted += passed
        correct_accepted += passed and valid_cell and resolved
        reviewed_unknown += valid_cell and case["scale"] is None and not passed
    return {
        "correct_citations": cited,
        "correct_citations_and_supported_scale": supported,
        "accepted": accepted,
        "accepted_with_correct_citation_and_scale": correct_accepted,
        "accepted_with_wrong_or_unsupported_answer": accepted - correct_accepted,
        "unresolved_reference_units_sent_to_review_with_correct_cell": reviewed_unknown,
    }


def audit(path: Path) -> dict:
    run = json.loads(path.read_text(encoding="utf-8"))
    if run.get("pipeline") == "cell_selection":
        raise ValueError("Supply the original development run to compare the baseline and replay.")
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if (run["split"], run["dataset_sha256"]) != (fixture["split"], fixture["dataset_sha256"]):
        raise ValueError("The reviewed cases require the matching development dataset.")
    by_id = {record["id"]: record for record in run["records"]}
    if len(by_id) != len(run["records"]):
        raise ValueError("Duplicate run record IDs.")
    if any(case["id"] not in by_id for case in fixture["cases"]):
        raise ValueError("The run does not include all reviewed cases.")
    original = [(case, by_id[case["id"]]) for case in fixture["cases"]]
    replayed = [(case, replay_record(record)) for case, record in original]

    # Give the verifier a real cell with the same printed number and a known wrong
    # metric or year. Each saved baseline selection used for this control passed.
    controls = []
    for case, record in original:
        for row, column in case.get("wrong_cells", []):
            prediction = record["prediction"]
            cell = record["table"][row][column]
            if (not record["verification"]["passed"] or [row, column] in case["cells"]
                    or parse_number(cell) != parse_number(prediction["value"])):
                raise ValueError(f"Invalid duplicate-cell control for {case['id']}")
            altered = {**record, "prediction": {**prediction, "row": row, "column": column}}
            altered["verification"] = verify(record["table"], altered["prediction"])
            checks = replay_record(altered)["verification"]
            controls.append({"id": case["id"], "wrong_cell": [row, column],
                             "baseline_passed": altered["verification"]["passed"],
                             "replay_passed": checks["passed"], "reasons": checks["reasons"]})
    return {
        "run": path.name, "reviewed_cases": len(original),
        "cases_with_supported_scale": sum(case["scale"] is not None for case, _ in original),
        "baseline": scores(original), "replay": scores(replayed),
        "same_number_wrong_cell_controls": controls,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(audit(args.file), indent=2))
    except (KeyError, OSError, ValueError) as error:
        parser.exit(2, f"Error: {error}\n")
