from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm


class EmailLoginForm(AuthenticationForm):
    username = forms.EmailField(
        label="E-Mail", widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"})
    )


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
