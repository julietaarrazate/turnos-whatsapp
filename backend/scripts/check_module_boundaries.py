"""Un módulo solo puede importar a otro por su paquete público (``app.modules.x``).

Prohibido: ``from app.modules.x.service import ...`` desde ``app/modules/y/``.
Uso: ``uv run python scripts/check_module_boundaries.py`` (corre en CI).
"""

import ast
import sys
from pathlib import Path

MODULES_DIR = Path(__file__).resolve().parent.parent / "src" / "app" / "modules"


def violations() -> list[str]:
    found: list[str] = []
    for path in sorted(MODULES_DIR.rglob("*.py")):
        own = path.relative_to(MODULES_DIR).parts[0]
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            for name in names:
                parts = name.split(".")
                if parts[:2] == ["app", "modules"] and len(parts) > 3 and parts[2] != own:
                    found.append(f"{path.relative_to(MODULES_DIR.parent)}:{node.lineno}: {name}")
    return found


if __name__ == "__main__":
    problems = violations()
    for problem in problems:
        print(f"Import interno de otro módulo: {problem}")
    sys.exit(1 if problems else 0)
