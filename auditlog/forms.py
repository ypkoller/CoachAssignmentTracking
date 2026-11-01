from datetime import date, datetime, time, timedelta
from typing import cast

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.db.models import QuerySet
from django.utils import timezone

from accounts.models import User
from training.models import Club, Squad
from training.permissions import admin_club_id

from .models import AuditEntry
from .tracking import TRACKED

SYSTEM = "system"  # actor filter for changes without a login (management commands)


class SquadChoiceField(forms.ModelChoiceField):
    with_club = False  # main administrator: squads of all clubs

    def label_from_instance(self, obj):
        return f"{obj.club} · {obj}" if self.with_club else str(obj)


class AreaChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        model = obj.model_class()
        return str(model._meta.verbose_name_plural) if model else obj.model


class AuditFilterForm(forms.Form):
    """Filters of the change log besides the period. Choices are limited to what the user may see."""

    club = forms.ModelChoiceField(
        Club.objects.none(), label="Verein", required=False, empty_label="Alle"
    )
    squad = SquadChoiceField(Squad.objects.none(), label="Riege", required=False, empty_label="Alle")
    actor = forms.ChoiceField(label="Geändert von", required=False)
    area = AreaChoiceField(
        ContentType.objects.none(), label="Bereich", required=False, empty_label="Alle"
    )

    def __init__(self, data, *, user, entries: QuerySet[AuditEntry]):
        super().__init__(data)
        squad_field = cast(SquadChoiceField, self.fields["squad"])
        area_field = cast(AreaChoiceField, self.fields["area"])
        tracked = list(TRACKED)
        if user.is_admin:
            cast(forms.ModelChoiceField, self.fields["club"]).queryset = Club.objects.all()
            squad_field.queryset = Squad.objects.select_related("club")
            squad_field.with_club = True
        else:
            del self.fields["club"]
            club_id = admin_club_id(user)
            squad_field.queryset = (
                Squad.objects.filter(club_id=club_id) if club_id is not None else Squad.objects.none()
            )
            tracked.remove(User)  # logins belong to no club
        area_field.queryset = ContentType.objects.filter(
            pk__in=[ContentType.objects.get_for_model(m).pk for m in tracked]
        )

        # Everyone who changed something the user may see, with their latest name.
        actors = (
            entries.exclude(actor_id=None)
            .order_by("actor_id", "-timestamp")
            .distinct("actor_id")
            .values_list("actor_id", "actor_name")
        )
        choices = sorted(((str(pk), name) for pk, name in actors), key=lambda c: c[1].lower())
        cast(forms.ChoiceField, self.fields["actor"]).choices = [
            ("", "Alle"),
            *choices,
            (SYSTEM, "System"),
        ]

    def apply(self, entries: QuerySet[AuditEntry], since: date, until: date) -> QuerySet[AuditEntry]:
        """Entries in the period (local days, inclusive) matching the valid filters."""
        start = timezone.make_aware(datetime.combine(since, time.min))
        end = timezone.make_aware(datetime.combine(until + timedelta(days=1), time.min))
        entries = entries.filter(timestamp__gte=start, timestamp__lt=end)
        self.is_valid()  # invalid filters (e.g. a foreign squad id) are ignored
        data = self.cleaned_data
        if data.get("club"):
            entries = entries.filter(club=data["club"])
        if data.get("squad"):
            entries = entries.filter(squad=data["squad"])
        if data.get("area"):
            entries = entries.filter(content_type=data["area"])
        actor = data.get("actor")
        if actor == SYSTEM:
            entries = entries.filter(actor_id=None)
        elif actor:
            entries = entries.filter(actor_id=actor)
        return entries
