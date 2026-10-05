"""Importa todos los modelos para que ``Base.metadata`` esté completo (Alembic, tests)."""

from app.core.db import Base
from app.modules.organizations import models as _organizations  # noqa: F401
from app.modules.users import models as _users  # noqa: F401

metadata = Base.metadata
