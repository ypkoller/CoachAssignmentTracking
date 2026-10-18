"""Audit fields for all tables: who created/updated a row and when.

The acting user is taken from the current request (`CurrentUserMiddleware`). Outside a
request (management commands, shell) it is empty.
"""

from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.contrib import admin
from django.db import models
from django.utils import timezone

if TYPE_CHECKING:
    from .models import User

AUDIT_FIELDS = ["created_at", "created_by", "updated_at", "updated_by"]

_current_user: ContextVar[User | None] = ContextVar("current_user", default=None)


def current_user() -> User | None:
    return _current_user.get()


class CurrentUserMiddleware:
    """Makes the logged-in user available to `AuditedModel.save()`."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user if request.user.is_authenticated else None
        token = _current_user.set(user)
        try:
            return self.get_response(request)
        finally:
            _current_user.reset(token)


def _user_field(verbose_name: str) -> Any:
    return models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=verbose_name,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="+",
    )


class AuditedModel(models.Model):
    created_at = models.DateTimeField("erstellt am", editable=False)
    created_by = _user_field("erstellt von")
    updated_at = models.DateTimeField("geändert am", editable=False)
    updated_by = _user_field("geändert von")

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        # A login only updates `last_login`; that is not a change of the data.
        if update_fields is not None and not set(update_fields) - {"last_login"}:
            return super().save(*args, **kwargs)
        now, user = timezone.now(), current_user()
        if self._state.adding:
            # On creation "updated" equals "created" (same timestamp, same user).
            self.created_at = self.updated_at = now
            self.created_by = self.updated_by = user
        else:
            self.updated_at, self.updated_by = now, user
            if update_fields is not None:
                kwargs["update_fields"] = {*update_fields, "updated_at", "updated_by"}
        return super().save(*args, **kwargs)


class AuditedAdminMixin:
    """Shows the audit fields read-only in the admin."""

    def get_readonly_fields(self, request, obj=None):
        return [*super().get_readonly_fields(request, obj), *AUDIT_FIELDS]  # type: ignore[misc]


class AuditedAdmin(AuditedAdminMixin, admin.ModelAdmin):
    pass
