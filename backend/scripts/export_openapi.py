"""Exporta el contrato OpenAPI. El frontend genera sus tipos desde este archivo.

Uso: uv run python scripts/export_openapi.py ../frontend/src/lib/api/openapi.json
CI regenera el archivo y falla si difiere del commiteado (contrato desactualizado).
"""

import json
import sys
from pathlib import Path

from app.main import create_app


def main() -> None:
    target = Path(sys.argv[1])
    schema = create_app().openapi()
    target.write_text(json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"OpenAPI exportado a {target}")


if __name__ == "__main__":
    main()
