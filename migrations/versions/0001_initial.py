"""Initial relational schema (SQLite and PostgreSQL)."""
revision='0001'
down_revision=None
branch_labels=None
depends_on=None
def upgrade():
    from backend.db import migrate
    from alembic import op
    migrate(op.get_bind().engine)
def downgrade():
    raise RuntimeError('Migração destrutiva bloqueada. Restaure backup para retornar uma versão.')
