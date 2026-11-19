"""Evaluate one saved run without making any API calls."""

import argparse
import hashlib
import json
import math
from decimal import Decimal
from pathlib import Path

from verify import PROCESSING_VERSION, finalize_selection, parse_number, verify


def replay_record(record: dict) -> dict:
    """Apply source-backed verification to a previously validated selection."""
    prediction = record["prediction"]
    saved_check = record["verification"]
    if (record["outcome"] != "ok" or prediction is None
            or prediction.get("status") != "found" or not saved_check["passed"]):
        return record

    # Check the original claim before replacing its value with a source copy.
    legacy_check = verify(record["table"], prediction)
    if not legacy_check["passed"]:
        return {**record, "verification": legacy_check}
    prediction, verification = finalize_selection(
        record["table"], record["paragraphs"], prediction["row"], prediction["column"],
        question=record["question"],
    )
    return {**record, "prediction": prediction, "verification": verification}


def answer_matches(prediction: dict | None, gold_value: Decimal, gold_scale: str) -> tuple[bool, bool]:
    if prediction is None or prediction.get("status") != "found":
        return False, False
    try:
        numeric_match = parse_number(prediction.get("value")) == gold_value
    except (ValueError, TypeError):
        return False, False
    scale = prediction.get("scale")
    return numeric_match, numeric_match and scale is not None and scale == gold_scale


def replay_case(record: dict, matches: tuple[bool, bool]) -> dict:
    prediction = record["prediction"] or {}
    check = record["verification"]
    numeric_match, strict_match = matches
    return {
        "status": prediction.get("status"),
        "scale": prediction.get("scale"),
        "numeric_correct": numeric_match,
        "strict_correct": strict_match,
        "accepted": check["passed"],
        "review_reasons": check.get("reasons", []),
    }


def comparison_metrics(cases: list[dict], planned: int, successful: int) -> dict:
    processed = len(cases)
    numeric = sum(case["numeric_correct"] for case in cases)
    strict = sum(case["strict_correct"] for case in cases)
    accepted = sum(case["accepted"] for case in cases)
    accepted_correct = sum(case["accepted"] and case["strict_correct"] for case in cases)
    accepted_errors = accepted - accepted_correct
    return {
        "numeric_correct_answers": numeric,
        "strict_correct_answers": strict,
        "numeric_accuracy_over_processed": numeric / processed if processed else None,
        "strict_accuracy_over_processed": strict / processed if processed else None,
        "numeric_accuracy_over_planned": numeric / planned,
        "strict_accuracy_over_planned": strict / planned,
        "accepted_answers": accepted,
        "flagged_for_review": successful - accepted,
        "coverage_over_processed": accepted / processed if processed else None,
        "coverage_over_planned": accepted / planned,
        "correct_accepted_answers": accepted_correct,
        "accepted_errors": accepted_errors,
        "accepted_accuracy": accepted_correct / accepted if accepted else None,
        "accepted_error_rate": accepted_errors / accepted if accepted else None,
    }


def evaluate(path: Path, *, replay: bool = False) -> dict:
    data = path.read_bytes()
    run = json.loads(data.decode("utf-8"))
    if not isinstance(run, dict) or type(run.get("format_version")) is not int or run["format_version"] != 1:
        raise ValueError("Expected a format_version=1 run file created by run.py.")
    if replay and run.get("pipeline") == "cell_selection":
        raise ValueError("--replay expects a legacy extraction run.")
    planned = run.get("selected_count")
    records = run.get("records")
    if type(planned) is not int or planned < 1:
        raise ValueError("selected_count must be a positive integer.")
    if not isinstance(records, list) or (not records and not replay):
        raise ValueError("The run has no saved records to evaluate.")
    if len(records) > planned:
        raise ValueError("There are more records than selected examples.")
    if type(run.get("completed")) is not bool:
        raise ValueError("The run must include a boolean completed field.")
    if run["completed"] and len(records) != planned:
        raise ValueError("A completed run must contain every selected example.")
    if not all(isinstance(run.get(key), str) and run[key]
               for key in ("model", "split", "dataset_sha256")):
        raise ValueError("The run is missing model, split or dataset_sha256 metadata.")

    identifiers, correct, passed = set(), [], []
    saved_scores, replayed_scores, audit_cases = [], [], []
    numeric_correct = 0
    tokens = {"input_tokens": 0, "output_tokens": 0}
    total_seconds = 0.0
    for index, record in enumerate(records, 1):
        try:
            identifier = record["id"]
            if not isinstance(identifier, str) or not identifier or identifier in identifiers:
                raise ValueError("missing or duplicate example ID")
            identifiers.add(identifier)
            outcome = record["outcome"]
            if outcome not in {"ok", "api_error", "invalid_output"}:
                raise ValueError("unknown outcome")
            prediction = record["prediction"]
            if prediction is not None and not isinstance(prediction, dict):
                raise ValueError("prediction must be an object or null")
            if outcome == "ok" and (prediction is None or prediction.get("status") not in {"found", "not_found"}):
                raise ValueError("successful responses must contain a found/not_found prediction")
            did_pass = record["verification"]["passed"]
            if type(did_pass) is not bool:
                raise ValueError("verification.passed must be boolean")
            found = outcome == "ok" and prediction is not None and prediction.get("status") == "found"
            if did_pass and not found:
                raise ValueError("only a successful found prediction can pass verification")
            gold_value = parse_number(record["gold"]["value"])
            gold_scale = record["gold"]["scale"]
            matches = answer_matches(prediction if found else None, gold_value, gold_scale)
            numeric_correct += matches[0]
            correct.append(matches[1])
            passed.append(did_pass)
            if replay:
                replayed = replay_record(record)
                replay_matches = answer_matches(
                    replayed["prediction"] if outcome == "ok" else None, gold_value, gold_scale,
                )
                baseline_case = replay_case(record, matches)
                replayed_case = replay_case(replayed, replay_matches)
                saved_scores.append(baseline_case)
                replayed_scores.append(replayed_case)
                if (outcome == "ok" and
                        (baseline_case != replayed_case or not replayed_case["accepted"]
                         or not replayed_case["strict_correct"])):
                    check = replayed["verification"]
                    audit_cases.append({
                        "id": identifier,
                        "gold": record["gold"],
                        "row": prediction.get("row"),
                        "column": prediction.get("column"),
                        "claimed_value": prediction.get("value"),
                        "source_value": check.get("cell"),
                        "baseline": baseline_case,
                        "replay": replayed_case,
                        **{key: check[key] for key in ("unit", "period", "metric") if check.get(key)},
                    })
            seconds = record["elapsed_seconds"]
            if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
                raise ValueError("elapsed_seconds must be a finite nonnegative number")
            total_seconds += seconds
            for key in tokens:
                count = record["usage"][key]
                if type(count) is not int or count < 0:
                    raise ValueError("token counts must be nonnegative integers")
                tokens[key] += count
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Invalid record {index}: {error}") from error

    accepted = sum(passed)
    accepted_correct = sum(is_correct and did_pass for is_correct, did_pass in zip(correct, passed))
    summary = {
        "model": run["model"], "split": run["split"], "dataset_sha256": run["dataset_sha256"],
        "planned_count": planned, "processed_count": len(records), "unprocessed": planned - len(records),
        "successful_responses": sum(row["outcome"] == "ok" for row in records),
        "api_errors": sum(row["outcome"] == "api_error" for row in records),
        "invalid_outputs": sum(row["outcome"] == "invalid_output" for row in records),
        "flagged_for_review": sum(row["outcome"] == "ok" and not flag for row, flag in zip(records, passed)),
        "correct_answers": sum(correct), "accepted_answers": accepted,
        "correct_accepted_answers": accepted_correct,
        "answer_accuracy_over_planned": sum(correct) / planned,
        "pass_rate_over_planned": accepted / planned,
        "accepted_accuracy": accepted_correct / accepted if accepted else None,
        "accepted_error_rate": (accepted - accepted_correct) / accepted if accepted else None,
        "incorrect_passed_ids": [row["id"] for row, good, flag in zip(records, correct, passed) if flag and not good],
        "recorded_input_tokens": tokens["input_tokens"],
        "recorded_output_tokens": tokens["output_tokens"],
        "records_with_usage": sum(row.get("usage_known", False) for row in records),
        "records_without_usage": sum(not row.get("usage_known", False) for row in records),
        "average_elapsed_seconds": total_seconds / len(records) if records else None,
    }
    if run.get("pipeline") == "cell_selection":
        summary.update({
            "pipeline": run["pipeline"],
            "processing_version": run.get("processing_version"),
            "numeric_correct_answers": numeric_correct,
            "numeric_accuracy_over_processed": numeric_correct / len(records),
        })
    if replay:
        successful = summary["successful_responses"]
        baseline = comparison_metrics(saved_scores, planned, successful)
        improved = comparison_metrics(replayed_scores, planned, successful)
        summary = {
            "replay_format_version": 1,
            "processing_version": PROCESSING_VERSION,
            "source_run": path.name,
            "source_run_sha256": hashlib.sha256(data).hexdigest(),
            "model": run["model"],
            "split": run["split"],
            "dataset_sha256": run["dataset_sha256"],
            "prompt_sha256": run.get("prompt_sha256"),
            "completed": run["completed"],
            "planned_count": planned,
            "processed_count": len(records),
            "unprocessed": planned - len(records),
            "completion_rate": len(records) / planned,
            "successful_responses": successful,
            "api_errors": summary["api_errors"],
            "invalid_outputs": summary["invalid_outputs"],
            "not_found": sum(
                row["outcome"] == "ok" and row["prediction"]["status"] == "not_found"
                for row in records
            ),
            "baseline": baseline,
            "replay": improved,
            "delta": {
                key: value - baseline[key]
                if value is not None and baseline[key] is not None else None
                for key, value in improved.items()
            },
            "cases": audit_cases,
        }
    suffix = ".replay.summary.json" if replay else ".summary.json"
    output = path.with_name(path.stem + suffix)
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="A run JSON file saved by run.py.")
    parser.add_argument("--replay", action="store_true",
                        help="Compare saved results with offline source-backed verification.")
    args = parser.parse_args()
    try:
        print(json.dumps(evaluate(args.file, replay=args.replay), indent=2))
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()
