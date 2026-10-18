from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm

from training.models import Club

from .clubs import active_persons


class EmailLoginForm(AuthenticationForm):
    username = forms.EmailField(
        label="E-Mail", widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"})
    )
    club = forms.ModelChoiceField(
        label="Verein",
        queryset=Club.objects.all(),
        required=False,
        empty_label="–",
        help_text="Nur nötig, wenn du in mehreren Vereinen erfasst bist.",
    )

    def clean(self):
        cleaned = super().clean()
        # Only reached with valid credentials.
        user = self.user_cache
        assert user is not None
        persons = active_persons(user)
        club = cleaned.get("club")
        if club is not None:
            self.person = next((p for p in persons if p.club_id == club.pk), None)
            if self.person is None:
                raise forms.ValidationError("Du bist in diesem Verein nicht erfasst.")
        elif len(persons) == 1:
            self.person = persons[0]
        elif persons and not user.is_superuser:
            raise forms.ValidationError("Du bist in mehreren Vereinen erfasst. Bitte wähle den Verein.")
        else:
            self.person = None
        return cleaned


class RegistrationForm(forms.Form):
    password1 = forms.CharField(
        label="Passwort", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )
    password2 = forms.CharField(
        label="Passwort wiederholen",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean(self):
        cleaned = super().clean() or {}
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Die Passwörter stimmen nicht überein.")
        if p1:
            password_validation.validate_password(p1, self.user)
        return cleaned
