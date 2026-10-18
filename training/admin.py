from django import forms
from django.contrib import admin, messages
from django.contrib.auth import password_validation
from django.urls import reverse
from django.utils.html import format_html

from accounts.audit import AUDIT_FIELDS, AuditedAdmin
from accounts.invitations import has_registered, invitation_message, invite
from accounts.models import User

from .admin_scope import ClubScopedAdmin, ClubScopedInline
from .models import Attendance, Club, Person, Squad, SquadAssignment, SquadLeadership


@admin.register(Club)
class ClubAdmin(AuditedAdmin):
    search_fields = ["name"]


class SquadLeadershipInline(ClubScopedInline):
    model = SquadLeadership
    extra = 0
    autocomplete_fields = ["person"]


class SquadAssignmentInline(ClubScopedInline):
    model = SquadAssignment
    extra = 0
    autocomplete_fields = ["person"]


@admin.register(Squad)
class SquadAdmin(ClubScopedAdmin):
    list_display = ["name", "club"]
    list_filter = ["club"]
    search_fields = ["name"]
    inlines = [SquadLeadershipInline, SquadAssignmentInline]


class PersonAdminForm(forms.ModelForm):
    create_login = forms.BooleanField(
        label="Login anlegen und Einladung senden",
        required=False,
        help_text="Die Person erhält per E-Mail einen Link, mit dem sie ihr Passwort festlegt.",
    )
    password = forms.CharField(
        label="Startpasswort (optional)",
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Damit kann sich die Person sofort anmelden. Über den Link kann sie es selbst ändern.",
    )

    class Meta:
        model = Person
        fields = "__all__"

    def clean(self):
        cleaned = super().clean() or {}
        password = cleaned.get("password")
        if not cleaned.get("create_login"):
            if password:
                self.add_error("password", "Nur zusammen mit «Login anlegen» möglich.")
            return cleaned
        email = cleaned.get("email")
        if not cleaned.get("is_active"):
            self.add_error("create_login", "Für inaktive Personen kann kein Login angelegt werden.")
        # An existing login (possibly of another club) keeps its password.
        if password and (self.instance.user_id or User.objects.filter(email__iexact=email).exists()):
            self.add_error(
                "password", "Für diese E-Mail gibt es bereits einen Login; er wird mit der Person verknüpft."
            )
            return cleaned
        if password:
            try:
                password_validation.validate_password(password, User(email=email or ""))
            except forms.ValidationError as error:
                self.add_error("password", error)
        return cleaned


@admin.register(Person)
class PersonAdmin(ClubScopedAdmin):
    form = PersonAdminForm
    list_display = [
        "last_name",
        "first_name",
        "email",
        "birth_year",
        "is_active",
        "is_club_admin",
        "club",
        "registered",
    ]
    list_filter = ["is_active", "is_club_admin", "club"]
    search_fields = ["last_name", "first_name", "email"]
    list_select_related = ["club", "user"]
    # Only the main administrator manages logins, so only they get the link to it.
    readonly_fields = ["login", "login_link"]
    actions = ["invite_selected"]

    def get_fieldsets(self, request, obj=None):
        fields = ["last_name", "first_name", "email", "birth_year", "is_active", "is_club_admin", "club"]
        # Once registered, the password belongs to the person; only the link to the login remains.
        login = [] if obj is None else ["login_link" if request.user.is_admin else "login"]
        if obj is None or not has_registered(obj):
            login.append("create_login")
        if obj is None or obj.user_id is None:
            login.append("password")
        fieldsets = [(None, {"fields": fields}), ("Login", {"fields": login})]
        if obj is not None:
            fieldsets.append(("Daten", {"fields": AUDIT_FIELDS}))
        return fieldsets

    @staticmethod
    def login_state(user) -> str:
        return "registriert" if user.has_usable_password() else "eingeladen, noch nicht registriert"

    @admin.display(description="Login")
    def login(self, obj):
        return f"{obj.user} ({self.login_state(obj.user)})" if obj.user else "kein Login"

    @admin.display(description="Login")
    def login_link(self, obj):
        if obj.user is None:
            return "kein Login"
        url = reverse("admin:accounts_user_change", args=[obj.user.pk])
        return format_html('<a href="{}">{}</a> ({})', url, obj.user, self.login_state(obj.user))

    @admin.display(description="registriert", boolean=True)
    def registered(self, obj):
        return has_registered(obj)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if form.cleaned_data.get("create_login") and not has_registered(obj):
            result = invite(obj, request, form.cleaned_data.get("password") or None)
            self.message_user(request, invitation_message([(obj, *result)]), messages.WARNING)

    @admin.action(description="Login anlegen und Einladung senden")
    def invite_selected(self, request, queryset):
        invitations, skipped = [], []
        for person in queryset.select_related("user"):
            if not person.is_active or has_registered(person):
                skipped.append(str(person))
                continue
            invitations.append((person, *invite(person, request)))
        if invitations:
            self.message_user(request, invitation_message(invitations), messages.WARNING)
        if skipped:
            self.message_user(
                request,
                "Übersprungen (inaktiv oder bereits registriert): "
                + ", ".join(skipped),
                messages.INFO,
            )


@admin.register(SquadLeadership)
class SquadLeadershipAdmin(ClubScopedAdmin):
    club_lookup = "squad__club"
    list_display = ["person", "squad", "valid_from", "valid_until"]
    list_filter = ["squad__club", "squad"]
    autocomplete_fields = ["person", "squad"]


@admin.register(SquadAssignment)
class SquadAssignmentAdmin(ClubScopedAdmin):
    club_lookup = "squad__club"
    list_display = ["person", "squad", "role", "valid_from", "valid_until"]
    list_filter = ["role", "squad__club", "squad"]
    autocomplete_fields = ["person", "squad"]


@admin.register(Attendance)
class AttendanceAdmin(ClubScopedAdmin):
    club_lookup = "squad__club"
    list_display = ["date", "squad", "person", "role", "created_by"]
    list_filter = ["role", "squad__club", "squad"]
    date_hierarchy = "date"
    autocomplete_fields = ["person", "squad"]
    readonly_fields = ["role"]
