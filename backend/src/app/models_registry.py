"""Importa todos los modelos para que ``Base.metadata`` esté completo (Alembic, tests)."""

from app.core import counters as _counters  # noqa: F401
from app.core import idempotency as _idempotency  # noqa: F401
from app.core.db import Base
from app.modules.audit import models as _audit  # noqa: F401
from app.modules.auth import models as _auth  # noqa: F401
from app.modules.budgets import models as _budgets  # noqa: F401
from app.modules.catalog import models as _catalog  # noqa: F401
from app.modules.clients import models as _clients  # noqa: F401
from app.modules.events import models as _events  # noqa: F401
from app.modules.identity import organization as _organization  # noqa: F401
from app.modules.identity import user as _user  # noqa: F401
from app.modules.notifications import models as _notifications  # noqa: F401
from app.modules.pricing import models as _pricing  # noqa: F401
from app.modules.production import models as _production  # noqa: F401
from app.modules.proposals import models as _proposals  # noqa: F401

metadata = Base.metadata
