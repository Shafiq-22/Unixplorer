"""derived positions and search indexes

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-12 11:22:38.398865

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Trusted contrib extensions (PostgreSQL >= 13): pg_trgm for name search, cube for the
    # GiST-indexed 3D points used by octree tile queries. Both ship with postgres:16.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS cube")
    op.create_index(
        "ix_celestial_object_parent_object_id",
        "celestial_object",
        ["parent_object_id"],
        unique=False,
    )
    op.create_index(
        "ix_object_alias_alias_trgm",
        "object_alias",
        ["alias_normalized"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"alias_normalized": "gin_trgm_ops"},
    )
    op.add_column("position_solution", sa.Column("bary_x_pc", sa.Double(), nullable=True))
    op.add_column("position_solution", sa.Column("bary_y_pc", sa.Double(), nullable=True))
    op.add_column("position_solution", sa.Column("bary_z_pc", sa.Double(), nullable=True))
    # Raw SQL keeps this migration independent of atlas_db.models (which may change later).
    op.execute("ALTER TABLE position_solution ADD COLUMN bary_xyz cube")
    op.add_column("position_solution", sa.Column("derived_method", sa.Text(), nullable=True))
    op.create_index(
        "ix_position_solution_bary_xyz",
        "position_solution",
        ["bary_xyz"],
        unique=False,
        postgresql_using="gist",
    )
    op.create_check_constraint(
        "derived_has_method", "position_solution", "(bary_x_pc IS NULL) = (derived_method IS NULL)"
    )


def downgrade() -> None:
    """Downgrade schema. Extensions are left installed (other objects may use them)."""
    op.drop_constraint(
        op.f("ck_position_solution_derived_has_method"), "position_solution", type_="check"
    )
    op.drop_index(
        "ix_position_solution_bary_xyz", table_name="position_solution", postgresql_using="gist"
    )
    op.drop_column("position_solution", "derived_method")
    op.drop_column("position_solution", "bary_xyz")
    op.drop_column("position_solution", "bary_z_pc")
    op.drop_column("position_solution", "bary_y_pc")
    op.drop_column("position_solution", "bary_x_pc")
    op.drop_index(
        "ix_object_alias_alias_trgm",
        table_name="object_alias",
        postgresql_using="gin",
        postgresql_ops={"alias_normalized": "gin_trgm_ops"},
    )
    op.drop_index("ix_celestial_object_parent_object_id", table_name="celestial_object")
    # ### end Alembic commands ###
