"""Shared field types for request schemas.

The free-text fields in this app (description / remarks / notes / reason)
are all `Text` columns, which SQLite does not length-limit at all. The cap
below is therefore a deliberate product limit, not a schema-derived one:
it keeps list views, PDFs and exports sane and stops an accidental
multi-megabyte paste from being stored.

Applied to **request** schemas only, never to `*Out` response schemas -
constraining a response would make existing rows that are already longer
than the cap unreadable through the API.

Keep in sync with TEXT_FIELD_MAX in frontend/src/components/ui.jsx.
"""
from typing import Annotated

from pydantic import StringConstraints

TEXT_FIELD_MAX_LENGTH = 2000

#: Free text with the shared cap applied (required).
LongText = Annotated[str, StringConstraints(max_length=TEXT_FIELD_MAX_LENGTH)]
#: Free text with the shared cap applied (optional).
OptLongText = Annotated[str, StringConstraints(max_length=TEXT_FIELD_MAX_LENGTH)] | None
