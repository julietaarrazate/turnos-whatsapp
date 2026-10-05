"""Datos de desarrollo: una organización con un usuario por rol. Solo para ENV=local.

Uso: uv run python scripts/seed_dev.py
"""

import sys

from app.core.config import get_settings
from app.core.db import DbContext, session_scope
from app.core.enums import Role
from app.core.ids import uuid7
from app.core.security import hash_password
from app.modules.identity import Membership, Organization, User

PASSWORD = "demo-demo-1234"  # solo desarrollo local


def main() -> None:
    if get_settings().env != "local":
        sys.exit("seed_dev solo corre con ENV=local")
    org_id = uuid7()
    password_hash = hash_password(PASSWORD)
    users = []
    with session_scope() as s:
        for role in Role:
            user = User(
                email=f"{role.value.lower()}@demo.example.com",
                name=f"{role.value.title()} Demo",
                password_hash=password_hash,
            )
            s.add(user)
            users.append((user, role))
    with session_scope(DbContext(organization_id=org_id)) as s:
        s.add(Organization(id=org_id, name="Productora Demo"))
        s.flush()
        for user, role in users:
            s.add(Membership(organization_id=org_id, user_id=user.id, role=role.value))
    print("Organización: Productora Demo")
    for user, role in users:
        print(f"  {role.value:<10} {user.email}  /  {PASSWORD}")


if __name__ == "__main__":
    main()
