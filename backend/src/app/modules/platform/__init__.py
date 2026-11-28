"""Panel de la dueña de la plataforma: ver quién usa Handie y qué hace, y pausar accesos.

Solo lo ve quien figura en PLATFORM_ADMINS; para el resto la API responde 404.
"""

from app.modules.platform.router import router

__all__ = ["router"]
