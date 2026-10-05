"""Alta de una organización nueva + invitación de su OWNER (no hay registro self-service en el MVP).

Uso: uv run python scripts/create_org.py --name "Productora X" --owner-email persona@x.com
Imprime el link de invitación y además lo envía por email (según EMAIL_BACKEND).
"""

import argparse
import re

from app.core.db import DbContext, session_scope
from app.core.enums import Role
from app.core.ids import uuid7
from app.modules.auth import create_invitation
from app.modules.identity import Organization
from app.modules.notifications import send_email


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--owner-email", required=True)
    args = parser.parse_args()

    org_id = uuid7()
    with session_scope(DbContext(organization_id=org_id)) as s:
        s.add(Organization(id=org_id, name=args.name))
        s.flush()
        _, message = create_invitation(s, org_id, args.owner_email, Role.OWNER, None)
    send_email(message)
    link = re.search(r"https?://\S+", message.text)
    print(f"Organización creada: {args.name} ({org_id})")
    print(f"Invitación OWNER para {args.owner_email}: {link.group(0) if link else '(ver email)'}")


if __name__ == "__main__":
    main()
