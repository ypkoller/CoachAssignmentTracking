"""Login accounts and invitations for persons (person admin, its list action, invitation admin)."""

import logging

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
    user = getattr(person, "user", None)
    return user is not None and user.has_usable_password()


def email_taken(email: str, person=None) -> bool:
    """Another login (not the one of `person`) already uses this email."""
    users = User.objects.filter(email__iexact=email)
    if person is not None and person.pk:
        users = users.exclude(person=person)
    return users.exists()


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


def invite(person, request, password: str | None = None) -> tuple[str, bool]:
    """Creates the login of the person if missing, optionally with a start password, and invites it."""
    with transaction.atomic():
        user = getattr(person, "user", None) or User(email=person.email, person=person)
        if password:
            user.set_password(password)
        elif user.pk is None:
            user.set_unusable_password()
        user.save()
        return send_invitation(Invitation(person=person), request)


def invitation_message(invitations: list[tuple[object, str, bool]]):
    """Admin message with the links, which are visible only now."""
    lines = format_html_join(
        "",
        "<br>{}: {} ({})",
        (
            (person, url, "E-Mail gesendet" if sent else "E-Mail fehlgeschlagen, Link selbst weitergeben")
            for person, url, sent in invitations
        ),
    )
    return format_html("Einladungslinks (werden nur jetzt angezeigt):{}", lines)
