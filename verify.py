"""Mechanical evidence checks. This module never reads reference answers."""

import re
from decimal import Decimal, localcontext

from table_layout import column_header_entries, heading_year, table_structure, years_in
from units import resolve_unit

PROCESSING_VERSION = 1
SCALES = {"": "1", "thousand": "1000", "million": "1000000",
          "billion": "1000000000", "percent": "0.01"}

METRIC_QUALIFIERS = (
    re.compile(r"\b(gross|net)\b", re.IGNORECASE),
    re.compile(r"\b(basic|diluted)\b", re.IGNORECASE),
)
YEAR_QUESTION = re.compile(
    r"^\s*(?:when\b|(?:(?:in|for)\s+)?(?:which|what)\s+"
    r"(?:(?:fiscal|calendar|reporting)\s+)?year\b|what\s+(?:was|is)\s+the\s+"
    r"(?:(?:first|last|fiscal|calendar|reporting)\s+)*year\b(?!\s*-?\s*over\b))",
    re.IGNORECASE,
)


def parse_number(value: str) -> Decimal:
    """Read a whole financial number; do not extract digits from prose."""
    text = str(value).strip().replace("−", "-").replace("–", "-")
    text = re.sub(r"[\s,$£€%]", "", text)
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", text):
        raise ValueError(f"Not a supported whole number: {value!r}")
    return Decimal(text)


def is_numeric(value: str) -> bool:
    try:
        parse_number(value)
    except ValueError:
        return False
    return True


def is_period_header(value: str, row: int, column: int, header_rows: list[int]) -> bool:
    return column > 0 and row in header_rows and heading_year(value) is not None


def asks_for_year(question: str) -> bool:
    return YEAR_QUESTION.match(question) is not None


def _period_conflict(question: str, table: list[list[str]],
                     column_entries: list[tuple[int, int]]) -> dict | None:
    requested = years_in(question)
    if len(requested) != 1:
        return None

    candidates = {}
    for index, column in column_entries:
        header = table[index]
        # A date in a lone merged heading can apply to several columns.
        alternatives = {heading_year(str(cell)) for cell in header[1:]}
        alternatives.discard(None)
        label = str(header[column]).strip()
        year = heading_year(label)
        if len(alternatives) > 1 and year is not None:
            candidates[year] = label

    if len(candidates) == 1 and candidates.keys().isdisjoint(requested):
        year, label = next(iter(candidates.items()))
        return {"requested_year": next(iter(requested)), "selected_year": year, "header": label}
    return None


def _metric_conflict(question: str, labels: list[str], section: str) -> dict | None:
    for pattern in METRIC_QUALIFIERS:
        requested = set(pattern.findall(question.casefold()))
        if len(requested) != 1:
            continue
        specific = [label for label in labels if pattern.search(label)]
        selected = set(pattern.findall(" ".join(specific or [section]).casefold()))
        if len(selected) == 1 and selected.isdisjoint(requested):
            label = specific[0] if specific else section
            return {"requested": next(iter(requested)), "selected": next(iter(selected)), "label": label}
    return None


def finalize_selection(table: list[list[str]], paragraphs: list[dict], row: int | None,
                       column: int | None, *, question: str = "") -> tuple[dict, dict]:
    """Read a model-selected coordinate and verify its source evidence."""
    found = row is not None or column is not None
    prediction = {"status": "found" if found else "not_found", "value": None,
                  "scale": None, "row": row, "column": column}
    verification = {"passed": False, "reasons": [], "cell": None, "normalised_value": None,
                    "unit": None, "period": None, "metric": None}
    reasons = verification["reasons"]
    if not found:
        reasons.append("model_did_not_find_an_answer")
        return prediction, verification
    if (type(row) is not int or type(column) is not int
            or not 0 <= row < len(table)
            or not 0 <= column < len(table[row])):
        reasons.append("invalid_cell_coordinates")
        return prediction, verification

    cell = str(table[row][column])
    verification["cell"] = cell
    try:
        number = parse_number(cell)
    except ValueError:
        reasons.append("value_or_cell_is_not_numeric")
        return prediction, verification
    prediction["value"] = cell

    header_rows, sections = table_structure(table)
    if is_period_header(cell, row, column, header_rows):
        if asks_for_year(question):
            prediction["scale"] = ""
            verification["unit"] = {
                "status": "resolved", "scale": "", "unit": "year", "multiplier": "1",
                "evidence": [{"source": "column_heading", "row": row, "column": column, "text": cell}],
            }
            reasons.append("header_year_requires_review")
        else:
            reasons.append("selected_cell_is_period_header")
        return prediction, verification

    headers = column_header_entries(table, [index for index in header_rows if index < row], column)
    period = _period_conflict(question, table, headers)
    if period:
        verification["period"] = period
        reasons.append("selected_cell_period_conflict")
    labels = [str(table[row][0]).strip()]
    labels.extend(str(table[index][col]).strip() for index, col in headers)
    metric = _metric_conflict(question, labels, sections[row])
    if metric:
        verification["metric"] = metric
        reasons.append("selected_cell_metric_conflict")

    unit = {**resolve_unit(table, paragraphs, row, column), "multiplier": None}
    verification["unit"] = unit
    if unit["status"] == "conflict":
        reasons.append("conflicting_unit_evidence")
    elif unit["status"] == "unknown":
        reasons.append("unresolved_unit")
    elif unit["scale"] not in SCALES:
        reasons.append("unsupported_scale")
    else:
        prediction["scale"] = unit["scale"]
        unit["multiplier"] = SCALES[unit["scale"]]

    if not reasons:
        multiplier = Decimal(unit["multiplier"])
        with localcontext() as context:
            context.prec = max(context.prec, len(number.as_tuple().digits) + len(multiplier.as_tuple().digits))
            verification["normalised_value"] = format(number * multiplier, "f")
        verification["passed"] = True
    return prediction, verification


def verify(table: list[list[str]], prediction: dict) -> dict:
    """Check a legacy model-supplied value and coordinate against its source."""
    result = {"passed": False, "reasons": [], "cell": None,
              "normalised_value": None}
    if prediction["status"] != "found":
        result["reasons"].append("model_did_not_find_an_answer")
        return result

    row, column = prediction["row"], prediction["column"]
    if (type(row) is not int or type(column) is not int
            or not 0 <= row < len(table)
            or not 0 <= column < len(table[row])):
        result["reasons"].append("invalid_cell_coordinates")
        return result

    cell = str(table[row][column])
    result["cell"] = cell
    try:
        source_value = parse_number(cell)
        predicted_value = parse_number(prediction["value"])
    except ValueError:
        result["reasons"].append("value_or_cell_is_not_numeric")
        return result

    if source_value != predicted_value:
        result["reasons"].append("value_does_not_match_cited_cell")
    scale = prediction["scale"]
    if scale not in SCALES:
        result["reasons"].append("unsupported_scale")
        return result
    if "%" in cell and scale != "percent":
        result["reasons"].append("percent_cell_requires_percent_scale")

    result["normalised_value"] = format(
        predicted_value * Decimal(SCALES[scale]), "f"
    )
    result["passed"] = not result["reasons"]
    return result
