from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.production.models import HireStatus, PieceArea, PieceStatus, TaskStatus


class HireItem(BaseModel):
    line_key: UUID
    name: str
    quantity: Decimal
    unit_code: str
    days: int
    cost_total: Decimal | None  # solo con cost.view


class EventSupplierOut(BaseModel):
    id: UUID
    supplier_id: UUID | None
    supplier_name: str | None
    contact_name: str | None  # a quién escribirle (contacto principal del proveedor)
    contact_phone: str | None
    status: HireStatus
    budgeted_cost: Decimal | None  # solo con cost.view
    items: list[HireItem]
    notes: str | None
    invoice_number: str | None
    payment_terms: str | None
    confirmed_at: datetime | None
    paid_at: datetime | None


class EventSupplierUpdate(BaseModel):
    status: HireStatus | None = None
    notes: str | None = Field(default=None, max_length=2000)
    invoice_number: str | None = Field(default=None, max_length=50)
    payment_terms: str | None = Field(default=None, max_length=200)


class TaskOut(BaseModel):
    id: UUID
    title: str
    status: TaskStatus
    assignee_user_id: UUID | None
    assignee_name: str | None
    due_date: date | None


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    assignee_user_id: UUID | None = None
    due_date: date | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: TaskStatus | None = None
    assignee_user_id: UUID | None = None
    due_date: date | None = None


class ProductionOut(BaseModel):
    started: bool
    suppliers: list[EventSupplierOut]
    tasks: list[TaskOut]
    budgeted_cost: Decimal | None  # total, solo con cost.view


class PieceOut(BaseModel):
    id: UUID
    event_id: UUID
    name: str
    area: PieceArea
    status: PieceStatus
    assignee_user_id: UUID | None
    assignee_name: str | None
    due_date: date | None
    late: bool  # vencida y todavía no está lista para cargar
    notes: str | None
    status_changed_at: datetime | None


class PiecesOut(BaseModel):
    pieces: list[PieceOut]
    total: int
    ready: int  # listas para carga o montadas
    progress: int  # 0 a 100: promedio de la fase de cada pieza


class PieceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    area: PieceArea = PieceArea.OTHER
    assignee_user_id: UUID | None = None
    due_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


class PieceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    area: PieceArea | None = None
    status: PieceStatus | None = None
    assignee_user_id: UUID | None = None
    due_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


# --- Mis tareas (taller / montaje) ----------------------------------------------------------


class WorkEvent(BaseModel):
    id: UUID
    number: int
    name: str
    mount_date: date | None  # inicio menos días de armado; None = fecha a confirmar


class PlanRef(BaseModel):
    """Un plano vigente de la pieza (para "Ver plano")."""

    id: UUID
    title: str
    version: int


class MyPiece(BaseModel):
    id: UUID
    name: str
    area: PieceArea
    status: PieceStatus
    due_date: date | None
    late: bool
    notes: str | None
    event: WorkEvent
    plans: list[PlanRef]  # los vigentes (en Mis tareas; vacío en otras listas)


class OpenPiece(MyPiece):
    """Una pieza a la que se le puede subir un avance (para elegirla después de la foto)."""

    mine: bool  # asignada a quien consulta: va primero


class MyTask(BaseModel):
    id: UUID
    title: str
    status: TaskStatus
    due_date: date | None
    late: bool
    event: WorkEvent


class MyWorkOut(BaseModel):
    """Lo asignado a quien consulta, pendiente, en eventos abiertos: lo atrasado primero."""

    pieces: list[MyPiece]
    tasks: list[MyTask]


class MyPieceUpdate(BaseModel):
    status: PieceStatus


class MyTaskUpdate(BaseModel):
    status: TaskStatus


# --- Avances de una pieza (foto y/o nota) ------------------------------------------------------


class PhotoIn(BaseModel):
    """La foto en base64, ya achicada en el teléfono (JPG, PNG, WEBP o HEIC; ≤ 10 MB)."""

    filename: str = Field(min_length=1, max_length=255)
    file_base64: str = Field(min_length=4, max_length=14_000_000)


class PieceUpdateIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)
    photo: PhotoIn | None = None


class PieceUpdateOut(BaseModel):
    id: UUID
    piece_id: UUID
    author_name: str
    note: str | None
    has_photo: bool
    created_at: datetime


# --- Planos de una pieza (con versiones) -----------------------------------------------------


class PlanIn(BaseModel):
    """Un plano: PDF o imagen (JPG, PNG, WEBP, HEIC), ≤ 10 MB. Mismo título = versión nueva."""

    title: str = Field(min_length=1, max_length=120)
    filename: str = Field(min_length=1, max_length=255)
    file_base64: str = Field(min_length=4, max_length=14_000_000)


class PlanOut(BaseModel):
    id: UUID
    piece_id: UUID
    title: str
    version: int
    current: bool  # la versión más nueva de ese título
    filename: str
    mime: str
    uploaded_by_name: str
    created_at: datetime


# --- Actividad (lo que pasa en producción, lo más nuevo primero) -------------------------------


class ActivityEvent(BaseModel):
    id: UUID
    number: int
    name: str


class ActivityOut(BaseModel):
    """Un movimiento: quién, qué y en qué evento. El texto lo arma la pantalla según ``kind``."""

    id: UUID
    kind: str  # piece.status_changed | piece.update_posted | piece.plan_uploaded | …
    actor_name: str | None
    event: ActivityEvent
    piece: str | None
    status: str | None  # fase nueva de la pieza o estado nuevo del proveedor
    supplier: str | None
    title: str | None  # título del plano
    version: int | None
    note: str | None
    update_id: UUID | None  # para mostrar la foto del avance
    has_photo: bool
    created_at: datetime


class ActivityPage(BaseModel):
    items: list[ActivityOut]
    next_before: datetime | None  # para pedir los anteriores
