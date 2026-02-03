"""
Routes for test plan import and retrieval.

Endpoints:
- POST /import/testplan
- GET /suites
- GET /suites/{suite_id}/testcases
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.api.db import get_db
from src.api.models import Suite, TestCase
from src.api.schemas import (
    ImportTestPlanResponse,
    SuitesListResponse,
    TestCasesPageResponse,
)
from src.api.testplan_import import (
    dumps_json_text,
    normalize_rows,
    parse_csv,
    parse_xlsx,
)

router = APIRouter(tags=["Test Plans"])


_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB safe default


def _require_supported_filename(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".csv"):
        return "csv"
    if lower.endswith(".xlsx"):
        return "xlsx"
    raise HTTPException(status_code=400, detail="Unsupported file type. Upload .csv or .xlsx.")


@router.post(
    "/import/testplan",
    response_model=ImportTestPlanResponse,
    summary="Import test plan (CSV/XLSX) and persist suites/test cases",
    description=(
        "Accepts multipart/form-data with file field 'file'. "
        "Parses CSV (UTF-8 headers) or XLSX (first sheet), normalizes columns, "
        "persists suites and test cases into MySQL, and returns summary + preview."
    ),
    operation_id="import_testplan",
)
async def import_testplan(
    file: UploadFile = File(..., description="CSV or XLSX file uploaded as multipart/form-data under field name 'file'."),
    db: Session = Depends(get_db),
) -> ImportTestPlanResponse:
    """
    Import a test plan file into the database.

    - CSV: UTF-8, headers required
    - XLSX: first worksheet, first row headers

    Returns summary counts and a preview of the first 10 normalized rows.
    """
    fmt = _require_supported_filename(file.filename or "")
    raw = await file.read()

    if len(raw) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large. Max size is {_MAX_UPLOAD_BYTES} bytes.")

    if fmt == "csv":
        raw_rows = parse_csv(raw)
    else:
        raw_rows = parse_xlsx(raw)

    normalized, warnings = normalize_rows(raw_rows)

    suites_created = 0
    testcases_created = 0
    duplicates_skipped = 0

    # Cache suites by name to reduce queries.
    suite_cache: dict[str, Suite] = {}

    for row in normalized:
        suite = suite_cache.get(row.suite_name)
        if suite is None:
            suite = db.execute(select(Suite).where(Suite.name == row.suite_name)).scalar_one_or_none()
            if suite is None:
                suite = Suite(name=row.suite_name)
                db.add(suite)
                try:
                    db.flush()  # allocate suite.id
                    suites_created += 1
                except IntegrityError:
                    db.rollback()
                    suite = db.execute(select(Suite).where(Suite.name == row.suite_name)).scalar_one()
            suite_cache[row.suite_name] = suite

        tc = TestCase(
            suite_id=suite.id,
            case_id=row.case_id,
            title=row.title,
            description=row.description,
            priority=row.priority,
            category=row.category,
            subcategory=row.subcategory,
            preconditions=row.preconditions,
            steps=dumps_json_text(row.steps),
            expected_result=row.expected_result,
            tags=dumps_json_text(row.tags),
        )
        db.add(tc)
        try:
            db.flush()
            testcases_created += 1
        except IntegrityError:
            # Likely duplicate suite_id+case_id unique constraint.
            db.rollback()
            duplicates_skipped += 1

    db.commit()

    preview = [r.to_preview_dict() for r in normalized[:10]]
    return ImportTestPlanResponse(
        suites_created=suites_created,
        testcases_created=testcases_created,
        duplicates_skipped=duplicates_skipped,
        warnings=warnings,
        preview=preview,
    )


@router.get(
    "/suites",
    response_model=SuitesListResponse,
    summary="List suites with test case counts",
    description="Returns all suites with their test case counts.",
    operation_id="list_suites",
)
def list_suites(db: Session = Depends(get_db)) -> SuitesListResponse:
    """List suites with counts of test cases."""
    stmt = (
        select(Suite.id, Suite.name, Suite.created_at, func.count(TestCase.id).label("cnt"))
        .select_from(Suite)
        .join(TestCase, TestCase.suite_id == Suite.id, isouter=True)
        .group_by(Suite.id, Suite.name, Suite.created_at)
        .order_by(Suite.created_at.desc())
    )
    rows = db.execute(stmt).all()
    return SuitesListResponse(
        suites=[
            {
                "id": r.id,
                "name": r.name,
                "created_at": r.created_at,
                "testcases_count": int(r.cnt or 0),
            }
            for r in rows
        ]
    )


@router.get(
    "/suites/{suite_id}/testcases",
    response_model=TestCasesPageResponse,
    summary="List test cases for a suite (paginated, filterable)",
    description=(
        "Returns paginated test cases for a given suite. "
        "Supports filters: category, priority, search (matches title/description/case_id)."
    ),
    operation_id="list_suite_testcases",
)
def list_suite_testcases(
    suite_id: int,
    page: int = Query(1, ge=1, description="1-based page number."),
    page_size: int = Query(20, ge=1, le=200, description="Page size (max 200)."),
    category: Optional[str] = Query(None, description="Filter by exact category."),
    priority: Optional[str] = Query(None, description="Filter by exact priority."),
    search: Optional[str] = Query(None, min_length=1, description="Search in title/description/case_id (contains, case-insensitive)."),
    db: Session = Depends(get_db),
) -> TestCasesPageResponse:
    """Paginated retrieval of test cases for a suite with basic filters."""
    suite = db.execute(select(Suite).where(Suite.id == suite_id)).scalar_one_or_none()
    if suite is None:
        raise HTTPException(status_code=404, detail="Suite not found.")

    filters = [TestCase.suite_id == suite_id]
    if category:
        filters.append(TestCase.category == category)
    if priority:
        filters.append(TestCase.priority == priority)
    if search:
        like = f"%{search}%"
        filters.append(
            or_(
                TestCase.title.ilike(like),
                TestCase.description.ilike(like),
                TestCase.case_id.ilike(like),
            )
        )

    total = db.execute(select(func.count(TestCase.id)).where(*filters)).scalar_one()

    stmt = (
        select(TestCase)
        .where(*filters)
        .order_by(TestCase.created_at.desc(), TestCase.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items: List[TestCase] = list(db.execute(stmt).scalars().all())

    return TestCasesPageResponse(
        items=[
            {
                "id": tc.id,
                "suite_id": tc.suite_id,
                "case_id": tc.case_id,
                "title": tc.title,
                "priority": tc.priority,
                "category": tc.category,
                "subcategory": tc.subcategory,
                "created_at": tc.created_at,
            }
            for tc in items
        ],
        total=int(total or 0),
        page=page,
        page_size=page_size,
        filters={"suite_id": suite_id, "category": category, "priority": priority, "search": search},
    )
