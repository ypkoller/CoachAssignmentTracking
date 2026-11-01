"""Writes an `AuditEntry` for every create, change and delete of the tracked models.

Uses model signals, so it covers views, the admin (including bulk delete) and cascaded
deletes. `QuerySet.update()`/`bulk_create()` send no signals and are not logged (they are
avoided anyway, see CLAUDE.md). The acting user comes from `CurrentUserMiddleware`.
"""

from collections.abc import Callable
from datetime import date, datetime

from django.contrib.auth.hashers import is_password_usable
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models.signals import post_delete, post_save, pre_save
from django.utils import timezone
from django.utils.formats import date_format

from accounts.audit import AUDIT_FIELDS, current_user
from accounts.models import User
from training.models import Attendance, Person, Squad, SquadAssignment, SquadLeadership

from .models import Action, AuditEntry

# Per tracked model: (club id, squad id) of an object, used for the filters and permissions.
# A login (User) belongs to no club; its entries are visible to the main administrator only.
type Scope = Callable[[models.Model], tuple[int | None, int | None]]


def _via_squad(obj) -> tuple[int | None, int | None]:
    return obj.squad.club_id, obj.squad_id


TRACKED: dict[type[models.Model], Scope] = {
    User: lambda obj: (None, None),
    Person: lambda obj: (obj.club_id, None),  # type: ignore[attr-defined]
    Squad: lambda obj: (obj.club_id, obj.pk),  # type: ignore[attr-defined]
    SquadLeadership: _via_squad,
    SquadAssignment: _via_squad,
    Attendance: _via_squad,
}

# Not part of the data: audit fields, the primary key and the login timestamp.
IGNORED = {"id", "last_login", *AUDIT_FIELDS}


def _fields(model: type[models.Model]) -> list[models.Field]:
    return [f for f in model._meta.concrete_fields if f.name not in IGNORED]


def _display(obj: models.Model, field: models.Field) -> str:
    """The value as the user knows it: names instead of ids, «Hauptleiter» instead of HEAD_LEADER."""
    value = field.value_from_object(obj)
    if value is None or value == "":
        return ""
    if field.name == "password":
        return "gesetzt" if is_password_usable(value) else "nicht gesetzt"
    if field.is_relation:
        try:
            return str(getattr(obj, field.name))
        except ObjectDoesNotExist:
            return f"#{value}"
    if field.choices:
        return str(dict(field.flatchoices).get(value, value))
    if isinstance(value, bool):
        return "ja" if value else "nein"
    if isinstance(value, datetime):
        return date_format(timezone.localtime(value), "d.m.Y H:i")
    if isinstance(value, date):
        return date_format(value, "d.m.Y")
    return str(value)


def _label(field: models.Field) -> str:
    return str(field.verbose_name)


def _diff(old: models.Model, new: models.Model) -> list[list[str]]:
    changes = []
    for field in _fields(type(new)):
        if field.value_from_object(old) == field.value_from_object(new):
            continue
        if field.name == "password":
            # Never store the hash, not even as "set → set".
            changes.append([_label(field), "", "geändert"])
        else:
            changes.append([_label(field), _display(old, field), _display(new, field)])
    return changes


def _values(obj: models.Model, *, new: bool) -> list[list[str]]:
    """All non-empty values: as new values on create, as old values on delete."""
    changes = []
    for field in _fields(type(obj)):
        text = _display(obj, field)
        if text:
            changes.append([_label(field), "", text] if new else [_label(field), text, ""])
    return changes


def _actor() -> tuple[User | None, str]:
    user = current_user()
    if user is None:
        return None, ""
    person = getattr(user, "person", None)
    return user, f"{person} ({user.email})" if person else user.email


def _write(obj: models.Model, action: str, changes: list[list[str]]) -> None:
    club_id, squad_id = TRACKED[type(obj)](obj)
    actor, actor_name = _actor()
    AuditEntry.objects.create(
        actor=actor,
        actor_name=actor_name,
        action=action,
        content_type=ContentType.objects.get_for_model(obj),
        object_id=obj.pk,
        object_repr=str(obj)[:300],
        changes=changes,
        club_id=club_id,
        squad_id=squad_id,
    )


def _only_login(update_fields) -> bool:
    return update_fields is not None and not set(update_fields) - {"last_login"}


def remember_old(sender, instance, raw=False, update_fields=None, **kwargs):
    instance._audit_old = None
    if raw or instance._state.adding or instance.pk is None or _only_login(update_fields):
        return
    instance._audit_old = sender._base_manager.filter(pk=instance.pk).first()


def log_save(sender, instance, created, raw=False, update_fields=None, **kwargs):
    if raw or _only_login(update_fields):
        return
    old = getattr(instance, "_audit_old", None)
    if created or old is None:
        _write(instance, Action.CREATE, _values(instance, new=True))
        return
    changes = _diff(old, instance)
    if changes:
        _write(instance, Action.UPDATE, changes)


def log_delete(sender, instance, **kwargs):
    _write(instance, Action.DELETE, _values(instance, new=False))


def connect() -> None:
    for model in TRACKED:
        uid = f"auditlog.{model._meta.label}"
        pre_save.connect(remember_old, sender=model, dispatch_uid=f"{uid}.pre_save")
        post_save.connect(log_save, sender=model, dispatch_uid=f"{uid}.post_save")
        post_delete.connect(log_delete, sender=model, dispatch_uid=f"{uid}.post_delete")
