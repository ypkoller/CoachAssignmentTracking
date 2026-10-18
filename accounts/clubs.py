"""Club chosen at login: stored in the session, resolved to the person in it on every request."""

from django.contrib.auth import logout

SESSION_KEY = "club_id"


def active_persons(user) -> list:
    """Active persons of a login, one per club, sorted by club."""
    return list(user.persons.filter(is_active=True).select_related("club").order_by("club__name"))


def choose_club(request, person) -> None:
    """Remembers the club of `person` (None: main administrator without club)."""
    request.session[SESSION_KEY] = person.club_id if person else None


class ClubMiddleware:
    """Sets `request.user.person` and `request.user.club_persons`.

    Without a chosen club, a login with exactly one active person works in its club. If the
    person of the chosen club has been deactivated, the session ends (only the main
    administrator may work without a club).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated:
            persons = active_persons(user)
            club_id = request.session.get(SESSION_KEY)
            if club_id:
                person = next((p for p in persons if p.club_id == club_id), None)
            else:
                person = persons[0] if len(persons) == 1 else None
            if person is None and not user.is_superuser:
                logout(request)
            else:
                user.person, user.club_persons = person, persons
        return self.get_response(request)
