from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, status

from app.core.db import DbSession
from app.core.idempotency import run_idempotent
from app.core.permissions import Permission
from app.modules.auth import TenantContext, require
from app.modules.finance import service
from app.modules.finance.schemas import ExpenseIn, ExpensesOut, ExpenseUpdate, ProfitabilityOut

router = APIRouter(prefix="/api/v1", tags=["finance"])

# Los gastos son costos: los ve quien ve costos y los carga quien tiene expenses.edit.
CostView = Annotated[TenantContext, Depends(require(Permission.COST_VIEW))]
Edit = Annotated[TenantContext, Depends(require(Permission.EXPENSES_EDIT))]
Margins = Annotated[TenantContext, Depends(require(Permission.MARGIN_VIEW))]
IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key", max_length=100)]


@router.get("/events/{event_id}/expenses")
def list_expenses(event_id: UUID, ctx: CostView, db: DbSession) -> ExpensesOut:
    """Gastos reales del evento y presupuestado vs real (por línea y no presupuestado)."""
    return service.list_expenses(db, ctx, event_id)


@router.post("/events/{event_id}/expenses", status_code=status.HTTP_201_CREATED)
def create_expense(
    event_id: UUID,
    body: ExpenseIn,
    ctx: Edit,
    db: DbSession,
    idempotency_key: IdempotencyKey = None,
) -> ExpensesOut:
    """Cargar un gasto (en campo la señal es mala: con Idempotency-Key no se duplica)."""
    return run_idempotent(
        db,
        organization_id=ctx.organization_id,
        user_id=ctx.user_id,
        key=idempotency_key,
        scope="expense.create",
        payload={"event_id": str(event_id), **body.model_dump(mode="json")},
        model=ExpensesOut,
        run=lambda: service.create_expense(db, ctx, event_id, body),
    )


@router.patch("/expenses/{expense_id}")
def update_expense(expense_id: UUID, body: ExpenseUpdate, ctx: Edit, db: DbSession) -> ExpensesOut:
    return service.update_expense(db, ctx, expense_id, body)


@router.delete("/expenses/{expense_id}")
def delete_expense(expense_id: UUID, ctx: Edit, db: DbSession) -> ExpensesOut:
    return service.delete_expense(db, ctx, expense_id)


@router.get("/events/{event_id}/profitability")
def get_profitability(event_id: UUID, ctx: Margins, db: DbSession) -> ProfitabilityOut:
    """Rentabilidad estimada vs real (ganancia y margen: solo quien ve márgenes)."""
    return service.get_profitability(db, ctx, event_id)
