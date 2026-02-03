"""Pydantic models for API request/response documentation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class ImportPreviewRow(BaseModel):
    suite_name: str = Field(..., description="Normalized suite name.")
    case_id: Optional[str] = Field(None, description="Normalized test case id (unique within suite).")
    title: str = Field(..., description="Test case title/name.")
    description: Optional[str] = Field(None, description="Optional description.")
    priority: Optional[str] = Field(None, description="Priority label, e.g. P0/P1.")
    category: Optional[str] = Field(None, description="Category/test area.")
    subcategory: Optional[str] = Field(None, description="Subcategory.")
    preconditions: Optional[str] = Field(None, description="Preconditions/prerequisites.")
    steps: Optional[List[str]] = Field(None, description="List of step strings (best-effort).")
    expected_result: Optional[str] = Field(None, description="Expected result/outcome.")
    tags: Optional[List[str]] = Field(None, description="List of tags (best-effort).")


class ImportTestPlanResponse(BaseModel):
    suites_created: int = Field(..., description="Number of suites created.")
    testcases_created: int = Field(..., description="Number of test cases created.")
    duplicates_skipped: int = Field(..., description="Number of duplicates skipped (same suite_id + case_id).")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal warnings encountered during import.")
    preview: List[ImportPreviewRow] = Field(default_factory=list, description="Preview of first 10 normalized rows.")


class SuiteListItem(BaseModel):
    id: int = Field(..., description="Suite database id.")
    name: str = Field(..., description="Suite name.")
    created_at: datetime = Field(..., description="Creation timestamp (UTC).")
    testcases_count: int = Field(..., description="Number of test cases in this suite.")


class SuitesListResponse(BaseModel):
    suites: List[SuiteListItem] = Field(..., description="List of suites with test case counts.")


class TestCaseListItem(BaseModel):
    id: int = Field(..., description="Test case database id.")
    suite_id: int = Field(..., description="Suite database id.")
    case_id: Optional[str] = Field(None, description="Imported test case identifier.")
    title: str = Field(..., description="Title/name.")
    priority: Optional[str] = Field(None, description="Priority label.")
    category: Optional[str] = Field(None, description="Category/test area.")
    subcategory: Optional[str] = Field(None, description="Subcategory.")
    created_at: datetime = Field(..., description="Creation timestamp (UTC).")


class TestCasesPageResponse(BaseModel):
    items: List[TestCaseListItem] = Field(..., description="Page items.")
    total: int = Field(..., description="Total number of matching test cases.")
    page: int = Field(..., description="1-based page number.")
    page_size: int = Field(..., description="Page size.")
    filters: Any = Field(..., description="Echo of applied filters.")
