from datetime import date, timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateRangeField, RangeBoundary, RangeOperators
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Func, Q
from django.db.models.functions import Lower
from django.utils import timezone

from accounts.audit import AuditedModel

# R12: Leaders and squad leaders may record at most this many days back.
MAX_DAYS_BACK = 30


def today() -> date:
    """Today's date in Europe/Zurich (TIME_ZONE)."""
    return timezone.localdate()


def earliest_date() -> date:
    return today() - timedelta(days=MAX_DAYS_BACK)


class DateRange(Func):
    function = "DATERANGE"
    output_field = DateRangeField()


def valid_on(day: date, prefix: str = "") -> Q:
    """Filter for periods `valid_from..valid_until` (inclusive, empty end = open)."""
    return Q(**{f"{prefix}valid_from__lte": day}) & (
        Q(**{f"{prefix}valid_until__isnull": True}) | Q(**{f"{prefix}valid_until__gte": day})
    )


def no_overlap(name: str) -> ExclusionConstraint:
    """R5/R6: No overlapping periods per person and squad."""
    return ExclusionConstraint(
        name=name,
        expressions=[
            ("person", RangeOperators.EQUAL),
            ("squad", RangeOperators.EQUAL),
            (
                DateRange("valid_from", "valid_until", RangeBoundary(True, True)),
                RangeOperators.OVERLAPS,
            ),
        ],
        violation_error_message="Für diese Person und Riege gibt es im Zeitraum bereits einen Eintrag.",
    )


def until_after_from(name: str) -> models.CheckConstraint:
    """R7: valid until ≥ valid from."""
    return models.CheckConstraint(
        name=name,
        condition=Q(valid_until__isnull=True) | Q(valid_until__gte=F("valid_from")),
        violation_error_message="«gültig bis» darf nicht vor «gültig ab» liegen.",
    )


class Club(AuditedModel):
    name = models.CharField("Name", max_length=200, unique=True)

    class Meta:
        verbose_name = "Verein"
        verbose_name_plural = "Vereine"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Squad(AuditedModel):
    name = models.CharField("Name", max_length=200)
    club = models.ForeignKey(  # R1
        Club, verbose_name="Verein", on_delete=models.PROTECT, related_name="squads"
    )

    class Meta:
        verbose_name = "Riege"
        verbose_name_plural = "Riegen"
        ordering = ["club__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["club", "name"], name="squad_name_unique_per_club"),
        ]

    def __str__(self):
        return self.name


class Person(AuditedModel):
    """A person in one club. The same login can belong to persons in several clubs."""

    last_name = models.CharField("Name", max_length=100)
    first_name = models.CharField("Vorname", max_length=100)
    email = models.EmailField("E-Mail")  # R3
    birth_year = models.PositiveSmallIntegerField("Jahrgang", null=True, blank=True)
    # Inactive: no access in this club; the login itself stays usable for other clubs.
    is_active = models.BooleanField("aktiv", default=True)
    is_club_admin = models.BooleanField(
        "Vereins-Admin",
        default=False,
        help_text="Verwaltet Riegen, Personen und Einsätze dieses Vereins.",
    )
    club = models.ForeignKey(  # R2
        Club, verbose_name="Verein", on_delete=models.PROTECT, related_name="persons"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Login",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="persons",
    )

    class Meta:
        verbose_name = "Person"
        verbose_name_plural = "Personen"
        ordering = ["last_name", "first_name"]
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                "club",
                name="person_email_ci_unique_per_club",
                violation_error_message="Diese E-Mail wird in diesem Verein bereits verwendet.",
            ),
            models.UniqueConstraint(
                fields=["user", "club"],
                name="person_one_per_login_and_club",
                violation_error_message="Dieser Login hat in diesem Verein bereits eine Person.",
            ),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def clean(self):
        super().clean()
        # The email is the username of the login; it is changed on the login, for all its persons.
        user = self.user if self.user_id else None
        if user is not None and self.email and self.email.lower() != user.email:
            raise ValidationError(
                {"email": "Die E-Mail gehört zum Login. Ändern kann sie nur der Haupt-Admin am Login."}
            )

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        super().save(*args, **kwargs)


if TYPE_CHECKING:
    _ModelBase = models.Model
else:
    _ModelBase = object


class SameClubMixin(_ModelBase):
    """R8: Person and squad belong to the same club."""

    person: Person
    squad: Squad
    person_id: int | None
    squad_id: int | None

    def clean(self):
        super().clean()
        if self.person_id and self.squad_id and self.person.club_id != self.squad.club_id:
            raise ValidationError("Person und Riege müssen zum selben Verein gehören.")


class SquadLeadership(SameClubMixin, AuditedModel):
    person = models.ForeignKey(
        Person, verbose_name="Person", on_delete=models.CASCADE, related_name="leaderships"
    )
    squad = models.ForeignKey(
        Squad, verbose_name="Riege", on_delete=models.CASCADE, related_name="leaderships"
    )
    valid_from = models.DateField("gültig ab", default=today)
    valid_until = models.DateField("gültig bis", null=True, blank=True)

    class Meta:
        verbose_name = "Riegenleitung"
        verbose_name_plural = "Riegenleitungen"
        ordering = ["squad", "-valid_from"]
        constraints = [
            no_overlap("leadership_no_overlap"),  # R6
            until_after_from("leadership_until_after_from"),  # R7
        ]

    def __str__(self):
        return f"{self.person} leitet {self.squad}"


class Role(models.TextChoices):
    HEAD_LEADER = "HEAD_LEADER", "Hauptleiter"
    ASSISTANT_LEADER = "ASSISTANT_LEADER", "Hilfsleiter"


class SquadAssignment(SameClubMixin, AuditedModel):
    person = models.ForeignKey(
        Person, verbose_name="Person", on_delete=models.CASCADE, related_name="assignments"
    )
    squad = models.ForeignKey(
        Squad, verbose_name="Riege", on_delete=models.CASCADE, related_name="assignments"
    )
    role = models.CharField("Funktion", max_length=20, choices=Role.choices)
    valid_from = models.DateField("gültig ab", default=today)
    valid_until = models.DateField("gültig bis", null=True, blank=True)

    class Meta:
        verbose_name = "Riegenzuteilung"
        verbose_name_plural = "Riegenzuteilungen"
        ordering = ["squad", "person"]
        constraints = [
            no_overlap("assignment_no_overlap"),  # R5
            until_after_from("assignment_until_after_from"),  # R7
        ]

    def __str__(self):
        return f"{self.person} – {self.squad} ({self.get_role_display()})"

    def clean(self):
        super().clean()
        if not self.pk:
            return
        # R9 after the fact: recorded attendances must stay covered by the assignment.
        old = SquadAssignment.objects.get(pk=self.pk)
        affected = Attendance.objects.filter(
            person_id=old.person_id, squad_id=old.squad_id, date__gte=old.valid_from
        )
        if old.valid_until:
            affected = affected.filter(date__lte=old.valid_until)
        if (self.person_id, self.squad_id) == (old.person_id, old.squad_id) and self.valid_from:
            still_covered = Q(date__gte=self.valid_from)
            if self.valid_until:
                still_covered &= Q(date__lte=self.valid_until)
            affected = affected.exclude(still_covered)
        if affected.exists():
            raise ValidationError(
                "Es gibt erfasste Einsätze ausserhalb des neuen Zeitraums. "
                "Bitte zuerst diese Einsätze löschen."
            )


class Attendance(SameClubMixin, AuditedModel):
    person = models.ForeignKey(
        Person, verbose_name="Person", on_delete=models.PROTECT, related_name="attendances"
    )
    squad = models.ForeignKey(
        Squad, verbose_name="Riege", on_delete=models.PROTECT, related_name="attendances"
    )
    date = models.DateField("Datum", default=today)
    # Taken from the valid assignment on save (model and DB trigger).
    role = models.CharField("Funktion", max_length=20, choices=Role.choices, editable=False)

    class Meta:
        verbose_name = "Einsatz"
        verbose_name_plural = "Einsätze"
        ordering = ["-date", "squad", "person"]
        constraints = [
            models.UniqueConstraint(
                fields=["person", "squad", "date"],
                name="attendance_once_per_day",
                violation_error_message="Für diese Person, Riege und Datum gibt es bereits einen Einsatz.",
            ),  # R10
            models.UniqueConstraint(
                fields=["squad", "date"],
                condition=Q(role=Role.HEAD_LEADER),
                name="attendance_one_head_leader_per_day",
                violation_error_message="Für diese Riege ist an diesem Datum bereits ein Hauptleiter erfasst.",
            ),  # R11
        ]

    def __str__(self):
        return f"{self.date:%d.%m.%Y} {self.squad}: {self.person}"

    def assignment(self):
        return SquadAssignment.objects.filter(
            valid_on(self.date), person_id=self.person_id, squad_id=self.squad_id
        ).first()

    def clean(self):
        super().clean()  # R8
        if self.date and self.date > today():  # R13
            raise ValidationError({"date": "Einsätze in der Zukunft sind nicht erlaubt."})
        if self.person_id and self.squad_id and self.date:
            assignment = self.assignment()  # R9
            if assignment is None:
                raise ValidationError("Die Person ist an diesem Datum der Riege nicht zugeteilt.")
            self.role = assignment.role

    def validate_constraints(self, exclude=None):
        # The role is only set in clean(), so do not exclude it from R11.
        if exclude:
            exclude = set(exclude) - {"role"}
        super().validate_constraints(exclude=exclude)
