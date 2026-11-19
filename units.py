"""Resolve a numeric cell's reporting scale from source declarations."""

import re
from dataclasses import dataclass

from table_layout import NUMBER_OR_DASH, column_header_entries, heading_and_section_cells


@dataclass(frozen=True)
class _Unit:
    scale: str | None
    name: str | None = None


_Candidate = tuple[_Unit, dict]
_YEAR = re.compile(r"(?:19|20)\d{2}")
_CURRENCIES = {
    "NTD": r"\b(?:NT\s*dollars?|NTD|TWD)\b|NT\$",
    "USD": r"\b(?:U\.?S\.?\s*dollars?|United States dollars?|USD)\b|\bUS\s*\$",
    "CAD": r"\b(?:Canadian dollars?|CAD)\b|CA\$",
    "AUD": r"\b(?:Australian dollars?|AUD)\b|AU\$",
    "CNY": r"\b(?:CNY|RMB|renminbi|yuan)\b|[¥￥]",
    "EUR": r"\b(?:EUR|euros?)\b|€",
    "GBP": r"\b(?:GBP|pounds sterling)\b|£",
    "dollar": r"\bdollars?\b|\$",
}
_SCALE_WORD = r"(?P<scale>thousand|million|billion)s?\b"
_SCALE = re.compile(
    rf"\bin\s+(?:[A-Za-z.]+\s+){{0,2}}?{_SCALE_WORD}"
    r"|^(?P<bare>thousand|million|billion)s?(?:\s+of\b|$)"
    r"|\b(?:shares|USD|CAD|AUD|TWD|EUR|GBP)[,\s]+(?P<qualified>thousand|million|billion)s?\b",
    re.IGNORECASE,
)
_CURRENCY_SCALE = re.compile(
    r"(?P<currency>[$£€¥￥]|\b(?:USD|CAD|AUD|TWD|EUR|GBP|CNY|RMB)\b)"
    r"\s*['’]?\s*(?:in\s+)?(?P<scale>thousand|million|billion)s?\b",
    re.IGNORECASE,
)
_SHORT_SCALE = re.compile(
    r"(?:[$£€¥￥]|\b(?:USD|CAD|AUD|TWD|EUR|GBP|CNY|RMB)\s*|\bin\s+)"
    r"['’]?\s*(?P<scale>000s?|[kmb]|mn|bn)\b",
    re.IGNORECASE,
)
_SHORT_NAMES = {
    "000": "thousand", "000s": "thousand", "k": "thousand",
    "m": "million", "mn": "million", "b": "billion", "bn": "billion",
}
_CAPTION_CUE = re.compile(
    r"\b(?:table|tabular|statements? of|notes? to|as follows|the following(?=\s*\()|"
    r"comparison of|"
    r"consist(?:s|ed|ing)? of|compri[sz](?:e|es|ed) of|composed of|"
    r"summar(?:y|i[sz](?:es|ed))|breakdown|disaggregation|reconciliation|"
    r"(?:all )?amounts (?:are |expressed |reported )?in)\b",
    re.IGNORECASE,
)
_PARAGRAPH_DECLARATION = re.compile(
    r"^(?:all\s+)?(?:(?:table|tabular)\s+)?"
    r"(?:(?:amounts|figures|values|dollars|shares)\s+)?"
    r"(?:(?:are|expressed|reported|stated)\s+)*in\b",
    re.IGNORECASE,
)
_PER_SHARE = re.compile(r"\bper[-\s]+(?:ordinary\s+|common\s+|diluted\s+|basic\s+)?share\b", re.I)
_TONNES = re.compile(r"\b(?:metric\s+)?tonnes?\b(?:\s*(?:CO₂e|CO2e)\b)?", re.I)
_YEARS = re.compile(r"\bin years\b|\(years\)|^years$", re.I)
_YEAR_OF = re.compile(
    r"^(?:(?:last|first)\s+)?(?:(?:fiscal|calendar)\s+)?year(?:\s+of\s+\w{3,})?$", re.I
)
_COUNT = re.compile(
    r"^(?:number|no\.?)$|\b(?:number|no\.?)\s+of\b|\b(?:headcounts?|counts?|whole shares)\b",
    re.I,
)
_SHARE_COUNT = re.compile(
    r"\b(?:number|no\.?)\s+of\s+(?:(?:ordinary|common)\s+)?shares\b"
    r"|\bshares\s+(?:used|outstanding|purchased|issued)\b",
    re.I,
)


def _currency(text: str) -> str | None:
    return next((name for name, pattern in _CURRENCIES.items() if re.search(pattern, text, re.I)), None)


def _unit(text: str) -> _Unit | None:
    # The declaration before "except" gives the default. Exceptions are
    # detected separately from the labels of the selected row and column.
    declaration = re.split(r"\bexcept\b", text, maxsplit=1, flags=re.I)[0].strip(" ()")
    explicit_currency = _CURRENCY_SCALE.search(declaration)
    currency = _currency(explicit_currency["currency"] if explicit_currency else declaration)
    multiplier = _SCALE.search(declaration)
    short = _SHORT_SCALE.search(declaration)
    scale = next((group.lower() for group in multiplier.groups() if group), "") if multiplier else ""
    if explicit_currency:
        scale = explicit_currency["scale"].lower()
    elif short:
        scale = scale or _SHORT_NAMES[short["scale"].lower()]

    if re.search(r"\bpercentage points?\b", declaration, re.I):
        return _Unit("", "percentage points")
    if re.search(r"(?<![\d.,])%|\b(?:percent(?:age)?|per cent)\b", declaration, re.I):
        return _Unit("percent", "percent")
    if _SHARE_COUNT.search(declaration):
        return _Unit(scale or None, "shares")
    if _PER_SHARE.search(declaration):
        if re.search(r"\bcents?\b", declaration, re.I):
            return _Unit(scale, "cents/share")
        return _Unit(scale, f"{currency}/share" if currency else "per share")
    if re.search(r"\bper dozen\b", declaration, re.I):
        if re.search(r"\bcents?\b", declaration, re.I):
            return _Unit(scale, "cents/dozen")
        return _Unit(scale, f"{currency}/dozen" if currency else "per dozen")
    if tonnes := _TONNES.search(declaration):
        unit = "tonnes CO2e" if re.search(r"CO[₂2]e", tonnes[0], re.I) else "tonnes"
        return _Unit(scale or None, unit)
    if re.search(r"\bmwh\b|\bmegawatt[- ]hours?\b", declaration, re.I):
        return _Unit(scale or None, "MWh")
    if _YEARS.search(declaration):
        return _Unit(scale, "years")
    if re.search(r"\b(?:ordinary |common )?shares\s*(?:[,)]|$|in\b)", declaration, re.I):
        if re.search(r"\bwhole shares\b", declaration, re.I):
            return _Unit("", "shares")
        return _Unit(scale or None, "shares")
    if _COUNT.search(declaration):
        return _Unit(scale or None, "count")
    if scale:
        return _Unit(scale, currency)
    # A currency symbol or label establishes denomination only. In particular
    # "$" and "Variance in Dollars" can sit above a table expressed in millions.
    if currency and re.search(r"\b(?:whole|individual)\b", declaration, re.I):
        return _Unit("", currency)
    return None


def _table_evidence(source: str, row: int, column: int, text: str) -> dict:
    return {"source": source, "row": row, "column": column, "text": text}


def _headings(
    table: list[list[str]], header_rows: list[int], column: int, cell: str,
) -> tuple[list[_Candidate], list[_Candidate]]:
    columns, captions = [], []
    for index, c in column_header_entries(table, header_rows, column):
        text = str(table[index][c])
        if _YEAR_OF.fullmatch(text.strip()) and _YEAR.fullmatch(cell.strip()):
            claim = _Unit("", "year")
        else:
            claim = _unit(text)
        if claim:
            columns.append((claim, _table_evidence("column_heading", index, c, text)))
    for index in header_rows:
        heading = table[index]
        populated = [(c, str(text)) for c, text in enumerate(heading) if str(text).strip()]
        if populated and (len(populated) == 1 or populated[0][0] == 0):
            c, text = populated[0]
            if len(populated) == 1 and c == 0 and index > 0:
                # A stub-only row below a heading starts or names a section.
                continue
            if claim := _unit(text):
                captions.append((claim, _table_evidence("table_heading", index, c, text)))
    return columns, captions


def _paragraph_units(paragraphs: list[dict], labels: str) -> tuple[list[_Candidate], list[_Candidate]]:
    captions, defaults = [], []
    for paragraph in paragraphs:
        text = paragraph["text"]
        for sentence in re.split(r"(?<![A-Z]\.)(?<=[.!?])\s+", text):
            fragments = re.findall(r"\(([^()]*)\)", sentence)
            standalone = _PARAGRAPH_DECLARATION.match(sentence.strip())
            if standalone or (_CAPTION_CUE.search(sentence) and re.search(r"\bthe percentage of\b", sentence, re.I)):
                fragments.append(sentence.strip())
            for fragment in fragments:
                if re.match(r"\s*\(\d+\)", sentence):
                    continue
                if not (standalone or _CAPTION_CUE.search(sentence)
                        or sentence.lstrip().startswith("(") or sentence.rstrip().endswith(":")):
                    continue
                # Notes frequently cite individual amounts in another scale.
                if re.search(r"[$£€]\s*[1-9]|[$£€]\s*0[.]", fragment):
                    continue
                claim = _unit(fragment)
                if not claim or (claim.name == "shares" and not re.search(r"\bshares\b", labels, re.I)):
                    continue
                # Earnings per share is a currency amount, not a share count.
                if claim.name == "shares" and _PER_SHARE.search(labels):
                    continue
                declaration = {
                    "source": "paragraph",
                    "paragraph_order": paragraph["order"],
                    "text": fragment,
                }
                if re.search(r"\bunless otherwise (?:stated|disclosed)\b", fragment, re.I):
                    defaults.append((claim, declaration))
                else:
                    captions.append((claim, declaration))
    return captions, defaults


def _result(candidates: list[_Candidate]) -> dict:
    scales = {unit.scale for unit, _ in candidates if unit.scale is not None}
    names = {unit.name for unit, _ in candidates if unit.name is not None}
    if "dollar" in names and names & {"USD", "NTD", "CAD", "AUD"}:
        names.remove("dollar")
    evidence = [evidence for _, evidence in candidates]
    if len(scales) > 1 or len(names) > 1:
        return {"status": "conflict", "scale": None, "unit": None, "evidence": evidence}
    if candidates:
        return {
            "status": "resolved", "scale": next(iter(scales), ""),
            "unit": next(iter(names), None), "evidence": evidence,
        }
    return {"status": "unknown", "scale": None, "unit": None, "evidence": []}


def _supports_unit(candidate: _Candidate, name: str | None) -> bool:
    unit, evidence = candidate
    if unit.name is not None and unit.name != name:
        return False
    exceptions = re.split(r"\bexcept\b", evidence["text"], maxsplit=1, flags=re.I)
    if len(exceptions) == 1:
        return True
    if name == "count":
        return _COUNT.search(exceptions[1]) is None
    if name == "shares":
        return re.search(r"\bshares?\b", _PER_SHARE.sub("", exceptions[1]), re.I) is None
    return True


def resolve_unit(table: list[list[str]], paragraphs: list[dict], row: int, column: int) -> dict:
    """Return the reporting scale, unit and evidence applicable to one cell."""
    if not 0 <= row < len(table) or not 0 <= column < len(table[row]):
        return _result([])
    cell = str(table[row][column])
    if "%" in cell:
        return _result([(_Unit("percent", "percent"), _table_evidence("cell", row, column, cell))])

    header_rows, sections = heading_and_section_cells(table)
    column_units, table_captions = _headings(table, [r for r in header_rows if r < row], column, cell)
    labels = [(c, str(text)) for c, text in enumerate(table[row][:column])
              if str(text).strip() and not NUMBER_OR_DASH.fullmatch(str(text))]
    row_units = [(claim, _table_evidence("row_label", row, c, text))
                 for c, text in labels if (claim := _unit(text))]
    section_units = []
    if sections[row] is not None:
        r, c = sections[row]
        text = str(table[r][c])
        if c == 0 and (claim := _unit(text)):
            section_units.append((claim, _table_evidence("section_heading", r, c, text)))
    local_units = row_units or section_units
    # Per-share and percent labels are narrower than an amount column heading.
    if any(unit.name in {"per share", "per dozen", "percent", "percentage points"}
           or (unit.name and unit.name.endswith(("/share", "/dozen"))) for unit, _ in local_units):
        return _result(local_units)
    preferred = local_units + column_units
    if preferred and any(unit.scale is not None for unit, _ in preferred):
        return _result(preferred)
    label_text = " ".join([text for _, text in labels] + [item["text"] for _, item in preferred])
    captions, defaults = _paragraph_units(paragraphs, label_text)
    if preferred:
        name = preferred[0][0].name
        # A dimension label can inherit a multiplier from broader source
        # declarations with compatible scope and no matching exception.
        for broader in (table_captions, captions, defaults):
            inherited = [item for item in broader if _supports_unit(item, name)]
            if inherited:
                return _result(preferred + inherited)
        return _result(preferred)
    return _result(table_captions or captions or defaults)
