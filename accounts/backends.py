from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    """Login by email (case-insensitive). Needs at least one active person (or main administrator).

    `ModelBackend.get_user` checks `user_can_authenticate` on every request, so a login whose
    persons have all been deactivated immediately loses access in existing sessions too.
    The chosen club is checked by `accounts.clubs.ClubMiddleware`.
    """

    def user_can_authenticate(self, user):
        if not super().user_can_authenticate(user):
            return False
        return user.is_superuser or user.persons.filter(is_active=True).exists()
