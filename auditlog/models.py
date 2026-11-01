from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from training.models import Club, Squad


class Action(models.TextChoices):
    CREATE = "CREATE", "Erstellt"
    UPDATE = "UPDATE", "Geändert"
    DELETE = "DELETE", "Gelöscht"


def _reference(model, verbose_name: str):
    """Reference without a DB constraint: an entry keeps the id after the row is deleted.

    Entries are also written while the referenced row is being deleted (e.g. a squad and,
    by cascade, its assignments), which a foreign key constraint would reject.
    """
    return models.ForeignKey(
        model,
        verbose_name=verbose_name,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True,
        blank=True,
        related_name="+",
    )


class AuditEntry(models.Model):
    """One change of a tracked object (see `auditlog.tracking`).

    Unlike the other models it does not inherit `AuditedModel`: entries are never changed,
    `timestamp`/`actor` are the "when" and "who", and they must survive deleted users.
    """

    timestamp = models.DateTimeField("Zeitpunkt", default=timezone.now, db_index=True)
    actor = _reference(settings.AUTH_USER_MODEL, "geändert von")
    # Name at the time of the change; stays readable when the login is renamed or deleted.
    actor_name = models.CharField("geändert von (Name)", max_length=300, blank=True)
    action = models.CharField("Aktion", max_length=6, choices=Action.choices)
    content_type = models.ForeignKey(
        ContentType, verbose_name="Bereich", on_delete=models.PROTECT, related_name="+"
    )
    object_id = models.BigIntegerField("Objekt-ID")
    object_repr = models.CharField("Objekt", max_length=300)
    # [[field label, old value, new value], ...] as display text at the time of the change.
    changes = models.JSONField("Änderungen", default=list)
    club = _reference(Club, "Verein")
    squad = _reference(Squad, "Riege")

    class Meta:
        verbose_name = "Änderung"
        verbose_name_plural = "Änderungen"
        ordering = ["-timestamp", "-id"]
        indexes = [
            models.Index(fields=["club", "timestamp"], name="auditentry_club_time"),
            models.Index(fields=["squad", "timestamp"], name="auditentry_squad_time"),
            models.Index(fields=["actor", "timestamp"], name="auditentry_actor_time"),
        ]

    def __str__(self):
        when = timezone.localtime(self.timestamp)
        return f"{when:%d.%m.%Y %H:%M} {self.get_action_display()}: {self.object_repr}"

    @property
    def area(self) -> str:
        model = self.content_type.model_class()
        return str(model._meta.verbose_name) if model else self.content_type.model

    @property
    def actor_label(self) -> str:
        return self.actor_name or "System"
