"""Object-level permissions (per club, squad and person). Every view checks through these.

All checks refer to the club chosen at login (`user.person`, see `accounts.clubs`). The main
administrator may do everything in all clubs, a club administrator the same in their club.
"""

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


def admin_club_id(user) -> int | None:
    """Club the user administers in this session (club administrator), else None."""
    person = person_of(user)
    return person.club_id if person is not None and user.is_club_admin else None


def manages_club(user, club_id: int) -> bool:
    return user.is_admin or admin_club_id(user) == club_id


def unrestricted_dates(user) -> bool:
    """Administrators are not bound to R12 (30 days back)."""
    return user.is_admin or admin_club_id(user) is not None


def led_squads(user, day: date) -> QuerySet[Squad]:
    """Squads the user leads as squad leader on the given day (administrators: all of theirs)."""
    squads = Squad.objects.select_related("club")
    if user.is_admin:
        return squads
    club_id = admin_club_id(user)
    if club_id is not None:
        return squads.filter(club_id=club_id)
    person = person_of(user)
    if person is None:
        return squads.none()
    ids = SquadLeadership.objects.filter(valid_on(day), person=person).values("squad_id")
    return squads.filter(id__in=ids)


def can_lead_squad(user, squad: Squad, day: date) -> bool:
    return led_squads(user, day).filter(pk=squad.pk).exists()


def date_allowed(user, day: date) -> bool:
    """R12/R13: Never in the future, for non-admins at most 30 days back."""
    if day > today():
        return False
    return unrestricted_dates(user) or day >= earliest_date()


def can_edit_attendance(user, person: Person, squad: Squad, day: date) -> bool:
    """May the user record, change or delete an attendance for (person, squad, day)?"""
    if not user.is_authenticated or not date_allowed(user, day):
        return False
    if manages_club(user, squad.club_id):
        return True
    assigned = SquadAssignment.objects.filter(valid_on(day), person=person, squad=squad).exists()
    if not assigned:
        return False
    return person == person_of(user) or can_lead_squad(user, squad, day)


def visible_attendances(user) -> QuerySet[Attendance]:
    """Admins: all (of their club). Squad leader: their squads while leading. Leader: own."""
    qs = Attendance.objects.select_related("person", "squad", "squad__club")
    if user.is_admin:
        return qs
    club_id = admin_club_id(user)
    if club_id is not None:
        return qs.filter(squad__club_id=club_id)
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
