"""Read headings and sections from the source table's flattened grid."""

import re


YEAR = re.compile(
    r"(?<!\w)(?:f(?:y|iscal\s+year)?\s*['’]?(?P<fiscal>\d{2}|(?:19|20)\d{2})"
    r"|(?P<calendar>(?:19|20)\d{2}))(?!\w)", re.IGNORECASE,
)
DATE_MONTH = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\b", re.IGNORECASE,
)
_UNIT_SUFFIX = re.compile(
    r"\s*\(?(?:[$£€¥]\s*|(?:USD|CAD|AUD|TWD|EUR|GBP|CNY|RMB)\s*['’]?\s*)"
    r"(?:in\s+)?(?:k|m|b|mn|bn|000s?|thousands?|millions?|billions?)\)?\s*$",
    re.IGNORECASE,
)
NUMBER_OR_DASH = re.compile(
    r"\s*(?:[\$£€¥]?\s*\(?\s*[\$£€¥]?\s*[+−–-]?(?:\d[\d,]*(?:\.\d*)?|\.\d+)"
    r"\s*\)?\s*%?|[\$£€¥]?\s*[—–-])\s*"
)


def years_in(text: str) -> set[int]:
    return {
        int(year) if len(year) == 4 else 2000 + int(year)
        for match in YEAR.finditer(text)
        for year in (match["fiscal"] or match["calendar"],)
    }


def heading_year(text: str) -> int | None:
    cleaned = re.sub(r"(?:\*+|\(\d+\))\s*$", "", text).strip()
    cleaned = _UNIT_SUFFIX.sub("", cleaned)
    years = years_in(cleaned)
    if len(years) == 1 and (YEAR.fullmatch(cleaned) or DATE_MONTH.search(cleaned)):
        return next(iter(years))
    return None


def heading_and_section_cells(
    table: list[list[str]],
) -> tuple[list[int], list[tuple[int, int] | None]]:
    """Identify leading headings and the preceding section cell for each row."""
    header_rows = []
    sections = []
    section = None
    for index, row in enumerate(table):
        sections.append(section)
        populated = [(column, str(cell)) for column, cell in enumerate(row) if str(cell).strip()]
        amounts = [cell.strip() for column, cell in populated
                   if column > 0 and NUMBER_OR_DASH.fullmatch(cell)]
        years = {year for cell in amounts if (year := heading_year(cell)) is not None}
        stub = str(row[0]).strip().lower() if row else ""
        year_headers = all(heading_year(cell) is not None for cell in amounts) and (
            len(years) > 1 or stub in {"", "year", "as of", "date", "metric", "period"}
            or stub.startswith("(in ")
        )
        if len(header_rows) == index and (not amounts or year_headers):
            header_rows.append(index)
        if len(populated) == 1 and not NUMBER_OR_DASH.fullmatch(populated[0][1]):
            section = (index, populated[0][0])
    return header_rows, sections


def table_structure(table: list[list[str]]) -> tuple[list[int], list[str]]:
    """Return leading heading rows and the active section text for each row."""
    header_rows, sections = heading_and_section_cells(table)
    return header_rows, [
        str(table[cell[0]][cell[1]]).strip() if cell else "" for cell in sections
    ]


def column_header_entries(
    table: list[list[str]], header_rows: list[int], column: int,
) -> list[tuple[int, int]]:
    """Find the direct or leftmost cell for each applicable column heading."""
    path = []
    for index in header_rows:
        row = table[index]
        if not 0 < column < len(row):
            continue
        if str(row[column]).strip():
            path.append((index, column))
            continue
        populated = [c for c, cell in enumerate(row) if c > 0 and str(cell).strip()]
        previous = [c for c in populated if c < column]
        if len(populated) < 2 or not previous:
            continue
        group = previous[-1]
        years = [c for c in populated if heading_year(str(row[c])) is not None]
        if not years or (group in years and _repeated_subheading(table, header_rows, index, column, group, years)):
            path.append((index, group))
    return path


def _repeated_subheading(
    table: list[list[str]], header_rows: list[int], parent: int, column: int, group: int,
    groups: list[int],
) -> bool:
    offset = column - group
    for index in header_rows:
        row = table[index]
        if index <= parent or column >= len(row):
            continue
        label = str(row[column]).strip().casefold()
        if label and any(c != group and c + offset < len(row)
                         and str(row[c + offset]).strip().casefold() == label for c in groups):
            return True
    return False


def column_header_path(table: list[list[str]], header_rows: list[int], column: int) -> list[str]:
    """Render applicable heading cells with their original wording."""
    return [str(table[r][c]).strip() for r, c in column_header_entries(table, header_rows, column)]
