"""ORM models. Import model modules here so Alembic autogenerate sees them.

Tables are added in the DB-schema step; the mixins below are shared by all models.
"""

from app.models.base import TimestampMixin, UUIDMixin  # noqa: F401
