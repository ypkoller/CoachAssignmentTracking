import hashlib
import secrets
from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from .audit import AuditedModel

if TYPE_CHECKING:
    from training.models import Person


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Die E-Mail ist Pflicht.")
        user = self.model(email=self.normalize_email(email).lower(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_superuser", True)
        return self._create_user(email, password, **extra_fields)

    def get_by_natural_key(self, username):
        return self.get(email__iexact=username)


class User(AuditedModel, AbstractBaseUser, PermissionsMixin):
    """Login account, possibly for several clubs (one `Person` per club).

    `is_superuser` is the main administrator flag (global).
    """

    email = models.EmailField("E-Mail")
    is_active = models.BooleanField("aktiv", default=True)

    objects = UserManager()

    # Set per request by `accounts.clubs.ClubMiddleware`: the person in the club chosen at
    # login, and all active persons of this login.
    person: Person | None = None
    club_persons: list[Person] = []

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"

    class Meta:
        verbose_name = "Benutzer"
        verbose_name_plural = "Benutzer"
        constraints = [
            models.UniqueConstraint(Lower("email"), name="user_email_ci_unique"),
        ]

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        super().save(*args, **kwargs)
        # The email is the username: keep the persons of this login in sync.
        update_fields = kwargs.get("update_fields")
        if update_fields is None or "email" in update_fields:
            for person in self.persons.exclude(email=self.email):
                person.email = self.email
                person.save(update_fields=["email"])

    @property
    def is_admin(self) -> bool:
        """Main administrator: everything, in all clubs."""
        return self.is_active and self.is_superuser

    @property
    def is_club_admin(self) -> bool:
        """Club administrator in the club chosen at login."""
        return self.is_active and self.person is not None and self.person.is_club_admin

    @property
    def is_staff(self) -> bool:
        """Access to the Django admin (checked by the admin site and used in templates)."""
        return self.is_admin or self.is_club_admin


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def default_invitation_expiry():
    return timezone.now() + timedelta(days=settings.INVITATION_VALID_DAYS)


class Invitation(AuditedModel):
    """One-time token for self-registration. Only its hash is stored."""

    person = models.ForeignKey(
        "training.Person",
        verbose_name="Person",
        on_delete=models.CASCADE,
        related_name="invitations",
    )
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    expires_at = models.DateTimeField("gültig bis", default=default_invitation_expiry)
    used_at = models.DateTimeField("benutzt am", null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "Einladung"
        verbose_name_plural = "Einladungen"

    def __str__(self):
        return f"Einladung für {self.person}"

    def generate_token(self) -> str:
        """Sets a new token and returns it in plain text (visible only once)."""
        token = secrets.token_urlsafe(32)
        self.token_hash = hash_token(token)
        return token

    @classmethod
    def find_valid(cls, token: str):
        return (
            cls.objects.select_related("person")
            .filter(
                token_hash=hash_token(token),
                used_at__isnull=True,
                expires_at__gt=timezone.now(),
                person__is_active=True,
            )
            .first()
        )
