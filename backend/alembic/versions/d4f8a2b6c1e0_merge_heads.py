"""merge heads

Revision ID: d4f8a2b6c1e0
Revises: c33027e735ba, c9e1f4a7b2d8
Create Date: 2026-09-08 00:00:00.000000

BUG FIX: c33027e735ba ("add platform theme") and c9e1f4a7b2d8 ("add
knowledge base") were both generated against b7d4e91a2c3f as their
down_revision -- i.e. two people/sessions ran `alembic revision
--autogenerate` from the same starting point without either picking up
the other's migration first, so the history forked into two heads
instead of a single line. `alembic upgrade head` refuses to guess
which one you mean and errors out with "Multiple head revisions are
present" -- that's not a corrupt database, it's Alembic correctly
refusing to pick a winner.

Safe to merge as a pure no-op: c33027e735ba's upgrade()/downgrade()
are both empty autogenerate stubs (nothing was actually filled in), so
there's no ordering conflict with c9e1f4a7b2d8's real work (creating
knowledge_documents/knowledge_chunks). This migration does nothing
itself -- it just gives Alembic a single revision that depends on both
branches, so "head" is unambiguous again.

Merging is purely a history fix, not a code change, so no test can
show it "worked" beyond upgrade() succeeding -- that's expected for a
merge revision.
"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "d4f8a2b6c1e0"
down_revision: Union[str, Sequence[str], None] = ("c33027e735ba", "c9e1f4a7b2d8")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Merge revision — no schema changes; both parent branches already
    # applied their own upgrade() when they ran.
    pass


def downgrade() -> None:
    # Merge revision — nothing to undo at this point specifically.
    pass
