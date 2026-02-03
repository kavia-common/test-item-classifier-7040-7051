"""
SQLAlchemy ORM models for imported test plans.

Schema (minimal):
- suites(id PK, name, created_at)
- test_cases(id PK, suite_id FK, case_id, title, description, priority, category, subcategory,
             preconditions, steps TEXT, expected_result, tags TEXT, created_at)

Note: steps/tags are stored as JSON text for portability/simplicity.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for SQLAlchemy declarative models."""


class Suite(Base):
    """A test suite (collection of test cases)."""

    __tablename__ = "suites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    test_cases: Mapped[List["TestCase"]] = relationship(
        back_populates="suite",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class TestCase(Base):
    """A single test case within a suite."""

    __tablename__ = "test_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    suite_id: Mapped[int] = mapped_column(Integer, ForeignKey("suites.id"), nullable=False, index=True)
    suite: Mapped[Suite] = relationship(back_populates="test_cases")

    # "case_id" corresponds to normalized test case identifier (e.g. wifistat-001).
    case_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    title: Mapped[str] = mapped_column(String(512), nullable=False)

    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    priority: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    category: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    subcategory: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    preconditions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # JSON text of array of step strings (or dicts), depending on parser output.
    steps: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    expected_result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # JSON text of array of tag strings.
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        # Prevent duplicate imports of the same case_id within the same suite (best-effort).
        UniqueConstraint("suite_id", "case_id", name="uq_suite_case_id"),
        Index("idx_test_cases_title", "title"),
    )
