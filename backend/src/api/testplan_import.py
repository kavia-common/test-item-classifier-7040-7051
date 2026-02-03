"""
Test plan import parsing + normalization.

Supports:
- CSV: UTF-8, with headers
- XLSX: first sheet, headers in first row

Normalization target fields:
- suite_name, case_id, title, description, priority, category, subcategory,
  preconditions, steps, expected_result, tags
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from fastapi import HTTPException


_STANDARD_FIELDS = [
    "suite_name",
    "case_id",
    "title",
    "description",
    "priority",
    "category",
    "subcategory",
    "preconditions",
    "steps",
    "expected_result",
    "tags",
]


def _norm_key(s: str) -> str:
    """Normalize a header key for matching (lowercase, remove non-alphanum)."""
    return "".join(ch for ch in s.strip().lower() if ch.isalnum())


# Best-effort mapping: many synonyms appear in real-world exports.
# We align with the artifact naming (suite_name/id/testarea/name/description_steps/expected_result/priority).
_HEADER_SYNONYMS: Dict[str, str] = {
    # suite name
    "suitename": "suite_name",
    "suite": "suite_name",
    "suiteid": "suite_name",  # artifact uses suite_id=WiFi/Mesh; treat as suite name
    # case id
    "caseid": "case_id",
    "id": "case_id",
    "testcaseid": "case_id",
    "tcid": "case_id",
    # title
    "title": "title",
    "name": "title",  # artifact uses "name" as a short title
    "testcasename": "title",
    # description / steps
    "description": "description",
    "descriptionsteps": "steps",  # artifact "description_steps" is steps-like
    "descriptionsteps": "steps",
    "steps": "steps",
    "procedure": "steps",
    # expected
    "expected": "expected_result",
    "expectedresult": "expected_result",
    "result": "expected_result",  # sometimes expected is labeled result in templates
    # priority
    "priority": "priority",
    "prio": "priority",
    # category/subcategory
    "category": "category",
    "testarea": "category",  # artifact uses testarea
    "area": "category",
    "subcategory": "subcategory",
    "subcat": "subcategory",
    # preconditions
    "preconditions": "preconditions",
    "precondition": "preconditions",
    "prerequisites": "preconditions",
    # tags
    "tags": "tags",
    "tag": "tags",
}


@dataclass
class NormalizedRow:
    """Normalized import row with standard fields."""
    suite_name: str
    case_id: Optional[str]
    title: str
    description: Optional[str]
    priority: Optional[str]
    category: Optional[str]
    subcategory: Optional[str]
    preconditions: Optional[str]
    steps: Optional[List[str]]
    expected_result: Optional[str]
    tags: Optional[List[str]]

    def to_preview_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable preview dict."""
        return {
            "suite_name": self.suite_name,
            "case_id": self.case_id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "category": self.category,
            "subcategory": self.subcategory,
            "preconditions": self.preconditions,
            "steps": self.steps,
            "expected_result": self.expected_result,
            "tags": self.tags,
        }


def _split_multiline_steps(value: Optional[str]) -> Optional[List[str]]:
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    # Common patterns: "1. ...\n2. ..." or newline-separated bullets.
    parts = [p.strip() for p in v.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    parts = [p for p in parts if p]
    return parts or None


def _split_tags(value: Optional[str]) -> Optional[List[str]]:
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    # Accept comma/semicolon separated.
    raw = [p.strip() for p in v.replace(";", ",").split(",")]
    raw = [p for p in raw if p]
    return raw or None


def _map_headers(headers: Sequence[str]) -> Dict[int, str]:
    """
    Create a mapping from column index -> standard field name.

    Unknown columns are ignored.
    """
    mapping: Dict[int, str] = {}
    for idx, h in enumerate(headers):
        nk = _norm_key(h)
        if nk in _HEADER_SYNONYMS:
            mapping[idx] = _HEADER_SYNONYMS[nk]
        elif nk in _STANDARD_FIELDS:
            mapping[idx] = nk
    return mapping


def _coerce_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def normalize_rows(raw_rows: Iterable[Dict[str, Any]]) -> Tuple[List[NormalizedRow], List[str]]:
    """
    Normalize input row dicts into NormalizedRow list.

    Each input row is a dict keyed by original headers.

    Returns:
      (rows, warnings)
    """
    warnings: List[str] = []
    normalized: List[NormalizedRow] = []

    for i, raw in enumerate(raw_rows, start=1):
        # Build header map per-row keys (stable for CSV; for xlsx it also is stable).
        # We match by normalized keys.
        key_to_val: Dict[str, Any] = {}
        for k, v in raw.items():
            # Some CSV/XLSX parsers can yield non-string keys (e.g. None when a row has
            # more values than headers). Skip those to avoid 500s during import.
            if k is None:
                continue
            std = _HEADER_SYNONYMS.get(_norm_key(str(k)), _norm_key(str(k)))
            key_to_val[std] = v

        suite_name = _coerce_str(key_to_val.get("suite_name")) or "Default"
        case_id = _coerce_str(key_to_val.get("case_id"))
        title = _coerce_str(key_to_val.get("title")) or _coerce_str(key_to_val.get("name")) or ""

        if not title:
            warnings.append(f"Row {i}: missing title/name; skipped.")
            continue

        description = _coerce_str(key_to_val.get("description"))
        priority = _coerce_str(key_to_val.get("priority"))
        category = _coerce_str(key_to_val.get("category"))
        subcategory = _coerce_str(key_to_val.get("subcategory"))
        preconditions = _coerce_str(key_to_val.get("preconditions"))
        expected_result = _coerce_str(key_to_val.get("expected_result"))

        steps_val = key_to_val.get("steps")
        steps = _split_multiline_steps(_coerce_str(steps_val)) if steps_val is not None else None

        tags_val = key_to_val.get("tags")
        tags = _split_tags(_coerce_str(tags_val)) if tags_val is not None else None

        normalized.append(
            NormalizedRow(
                suite_name=suite_name,
                case_id=case_id,
                title=title,
                description=description,
                priority=priority,
                category=category,
                subcategory=subcategory,
                preconditions=preconditions,
                steps=steps,
                expected_result=expected_result,
                tags=tags,
            )
        )

    return normalized, warnings


def parse_csv(file_bytes: bytes, max_rows: int = 50_000) -> List[Dict[str, Any]]:
    """Parse UTF-8 CSV with headers to a list of dict rows."""
    try:
        text = file_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(status_code=400, detail=f"CSV must be UTF-8 encoded: {e}") from e

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV must include a header row.")

    rows: List[Dict[str, Any]] = []
    for i, row in enumerate(reader, start=1):
        if i > max_rows:
            raise HTTPException(status_code=413, detail=f"CSV too large; max {max_rows} rows.")
        rows.append(row)
    return rows


def parse_xlsx(file_bytes: bytes, max_rows: int = 50_000) -> List[Dict[str, Any]]:
    """
    Parse XLSX first sheet. Requires openpyxl installed.

    We interpret:
      - first row as headers
      - subsequent rows as data
    """
    try:
        import openpyxl  # type: ignore
    except Exception as e:  # pragma: no cover
        raise HTTPException(
            status_code=500,
            detail="XLSX import requires 'openpyxl' dependency installed on the backend.",
        ) from e

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    sheet = wb.worksheets[0]
    rows_iter = sheet.iter_rows(values_only=True)

    try:
        headers_row = next(rows_iter)
    except StopIteration:
        raise HTTPException(status_code=400, detail="XLSX appears to be empty.")

    headers = [str(h).strip() if h is not None else "" for h in headers_row]
    if not any(headers):
        raise HTTPException(status_code=400, detail="XLSX header row is empty.")

    out: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows_iter, start=1):
        if idx > max_rows:
            raise HTTPException(status_code=413, detail=f"XLSX too large; max {max_rows} rows.")
        rec: Dict[str, Any] = {}
        for c, h in enumerate(headers):
            if not h:
                continue
            rec[h] = row[c] if c < len(row) else None
        # Skip completely empty rows.
        if all(v is None or str(v).strip() == "" for v in rec.values()):
            continue
        out.append(rec)

    return out


def dumps_json_text(value: Any) -> Optional[str]:
    """Dump JSON-serializable value to text, or return None."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)
