"""Expectations aligned with ``m8flow-backend/sample_templates/README.md`` § *Templates included*.

The README lists human-oriented descriptions and ZIP filenames. The **UI title** for
automatically loaded zips is not the parenthetical phrase: it comes from
``m8flow_backend.services.sample_template_loader._derive_display_name`` (strip
``(...)`` segments, turn ``-``/``_`` into spaces, :func:`str.title`). Substrings
below match those **derived** names so search and card text both line up.

When the README adds or renames a ZIP, re-derive the substring from that algorithm
(do not use the description column verbatim if it only appears inside parentheses).

Do **not** edit backend files from the browser test tree—mirror behaviour here.
"""

from __future__ import annotations

from typing import NamedTuple

__all__ = ["SampleTemplateReadmeRow", "SAMPLE_TEMPLATE_README_ROWS"]


class SampleTemplateReadmeRow(NamedTuple):
    """One row from the README template catalogue."""

    slug: str
    ui_substring: str


# Order matches README.md "Templates included" table (template-1 … template-6).
# ui_substring matches _derive_display_name(zip_filename), not the table description.
SAMPLE_TEMPLATE_README_ROWS: tuple[SampleTemplateReadmeRow, ...] = (
    SampleTemplateReadmeRow(
        "single-approval-wfh-timeout",
        # ZIP: Single Approval - ( WFH Approval Process with Timeout ).zip → outside parens only
        "Single Approval",
    ),
    SampleTemplateReadmeRow(
        "two-step-leave-email",
        # ZIP: Two-Step Leave ... → hyphens become spaces
        "Two Step Leave",
    ),
    SampleTemplateReadmeRow(
        "approval-expense-dmn",
        # ZIP: Approval with Conditional Escalation - ( Expense Claim ... ).zip
        "Conditional Escalation",
    ),
    SampleTemplateReadmeRow(
        "form-driven-it-support",
        # ZIP: Form-Driven Approval ... → "Form Driven Approval ..."
        "Form Driven",
    ),
    SampleTemplateReadmeRow(
        "salesforce-slack-lead",
        "Salesforce Lead",
    ),
    SampleTemplateReadmeRow(
        "postgresql-lifecycle",
        # .title() yields "Postgresql ..."; avoid brand spelling mismatch
        "Table Lifecycle",
    ),
)
