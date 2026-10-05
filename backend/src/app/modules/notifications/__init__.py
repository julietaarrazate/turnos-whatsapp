"""Notificaciones salientes (email)."""

from app.modules.notifications.email import Email, console_backend, send_email

__all__ = ["Email", "console_backend", "send_email"]
