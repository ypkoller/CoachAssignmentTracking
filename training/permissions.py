"""Object-level permissions (per squad and person). Every view checks through these."""

from datetime import date

from django.db.models import Q, QuerySet

from .models import (
    Attendance,
    Person,
    Squad,
    SquadAssignment,
    SquadLeadership,
    earliest_date,
    today,
    valid_on,
)


def person_of(user) -> Person | None:
    return user.person if user.is_authenticated else None


def led_squads(user, day: date) -> QuerySet[Squad]:
    """Squads the user leads as squad leader on the given day (admin: all)."""
    if user.is_admin:
        return Squad.objects.select_related("club")
    person = person_of(user)
    if person is None:
        return Squad.objects.none()
    ids = SquadLeadership.objects.filter(valid_on(day), person=person).values("squad_id")
    return Squad.objects.filter(id__in=ids).select_related("club")


def can_lead_squad(user, squad: Squad, day: date) -> bool:
    return led_squads(user, day).filter(pk=squad.pk).exists()


def date_allowed(user, day: date) -> bool:
    """R12/R13: Never in the future, for non-admins at most 30 days back."""
    if day > today():
        return False
    return user.is_admin or day >= earliest_date()


def can_edit_attendance(user, person: Person, squad: Squad, day: date) -> bool:
    """May the user record, change or delete an attendance for (person, squad, day)?"""
    if not user.is_authenticated or not date_allowed(user, day):
        return False
    if user.is_admin:
        return True
    assigned = SquadAssignment.objects.filter(valid_on(day), person=person, squad=squad).exists()
    if not assigned:
        return False
    return person == person_of(user) or can_lead_squad(user, squad, day)


def visible_attendances(user) -> QuerySet[Attendance]:
    """Admin: all. Squad leader: attendances of their squads while leading. Leader: own."""
    qs = Attendance.objects.select_related("person", "squad", "squad__club")
    if user.is_admin:
        return qs
    person = person_of(user)
    if person is None:
        return qs.none()
    visible = Q(person=person)
    for leadership in SquadLeadership.objects.filter(person=person):
        condition = Q(squad_id=leadership.squad_id, date__gte=leadership.valid_from)
        if leadership.valid_until:
            condition &= Q(date__lte=leadership.valid_until)
        visible |= condition
    return qs.filter(visible)
