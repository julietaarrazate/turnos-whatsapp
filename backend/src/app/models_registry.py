"""Importa todos los modelos para que ``Base.metadata`` esté completo (Alembic, tests)."""

from app.core.db import Base
from app.modules.audit import models as _audit  # noqa: F401
from app.modules.auth import models as _auth  # noqa: F401
from app.modules.identity import organization as _organization  # noqa: F401
from app.modules.identity import user as _user  # noqa: F401
from app.modules.notifications import models as _notifications  # noqa: F401

metadata = Base.metadata
