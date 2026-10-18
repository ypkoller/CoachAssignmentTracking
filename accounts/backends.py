from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    """Login by email (case-insensitive). Inactive persons are rejected.

    `ModelBackend.get_user` checks `user_can_authenticate` on every request, so a
    deactivated person immediately loses access in existing sessions too.
    """

    def user_can_authenticate(self, user):
        if not super().user_can_authenticate(user):
            return False
        person = user.person
        return person is None or person.is_active
