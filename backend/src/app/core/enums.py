from enum import StrEnum


class Role(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    QUOTER = "QUOTER"
    PRODUCTION = "PRODUCTION"
    VIEWER = "VIEWER"


class TaxCondition(StrEnum):
    RI = "RI"
    MONOTRIBUTO = "MONOTRIBUTO"
    EXENTO = "EXENTO"


def check_in(column: str, values: type[StrEnum]) -> str:
    """Expresión SQL para un CHECK ``column IN (...)`` a partir de un enum."""
    options = ", ".join(f"'{v.value}'" for v in values)
    return f"{column} IN ({options})"
