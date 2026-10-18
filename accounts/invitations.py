"""Login accounts and invitations for persons (person admin, its list action, invitation admin)."""

import logging
from collections.abc import Sequence

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from .models import Invitation, User

logger = logging.getLogger(__name__)


def has_registered(person) -> bool:
    """The person has a login with a password (set at registration or by the admin)."""
    return person.user is not None and person.user.has_usable_password()


def send_invitation(invitation: Invitation, request) -> tuple[str, bool]:
    """Saves the invitation with a new token and mails the link to the person.

    Returns the link (it cannot be shown again later) and whether the mail was sent.
    """
    token = invitation.generate_token()
    invitation.save()
    url = request.build_absolute_uri(reverse("register", args=[token]))
    context = {"person": invitation.person, "url": url, "valid_days": settings.INVITATION_VALID_DAYS}
    try:
        send_mail(
            render_to_string("accounts/email/invitation_subject.txt", context).strip(),
            render_to_string("accounts/email/invitation.txt", context),
            None,
            [invitation.person.email],
        )
    except Exception:
        # The admin still sees the link and can pass it on.
        logger.exception("Invitation mail to %s failed", invitation.person.email)
        return url, False
    return url, True


def invite(person, request, password: str | None = None) -> tuple[str | None, bool]:
    """Gives the person a login and invites it.

    An existing login with the same email (from another club) is linked; if it is already
    registered, no invitation is needed (result: no link). Otherwise a new login is created,
    without password or with the start password (only for a new login).
    """
    with transaction.atomic():
        user = person.user or User.objects.filter(email__iexact=person.email).first()
        created = user is None
        if user is None:
            user = User(email=person.email)
            if password:
                user.set_password(password)
            else:
                user.set_unusable_password()
            user.save()
        if person.user_id != user.pk:
            person.user = user
            person.save(update_fields=["user"])
        if not created and user.has_usable_password():
            return None, False
        return send_invitation(Invitation(person=person), request)


def invitation_message(invitations: Sequence[tuple[object, str | None, bool]]):
    """Admin message with the links, which are visible only now."""

    def state(url, sent):
        if url is None:
            return "bestehender Login verknüpft, keine Einladung nötig"
        return "E-Mail gesendet" if sent else "E-Mail fehlgeschlagen, Link selbst weitergeben"

    lines = format_html_join(
        "",
        "<br>{}: {}",
        (
            (person, f"{url} ({state(url, sent)})" if url else state(url, sent))
            for person, url, sent in invitations
        ),
    )
    return format_html("Logins und Einladungslinks (Links werden nur jetzt angezeigt):{}", lines)
