from django import forms
from django.contrib import admin, messages
from django.contrib.auth import password_validation
from django.urls import reverse
from django.utils.html import format_html

from accounts.audit import AUDIT_FIELDS, AuditedAdmin
from accounts.invitations import email_taken, has_registered, invitation_message, invite
from accounts.models import User

from .models import Attendance, Club, Person, Squad, SquadAssignment, SquadLeadership


@admin.register(Club)
class ClubAdmin(AuditedAdmin):
    search_fields = ["name"]


class SquadLeadershipInline(admin.TabularInline):
    model = SquadLeadership
    extra = 0
    autocomplete_fields = ["person"]


class SquadAssignmentInline(admin.TabularInline):
    model = SquadAssignment
    extra = 0
    autocomplete_fields = ["person"]


@admin.register(Squad)
class SquadAdmin(AuditedAdmin):
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
        if email and email_taken(email, self.instance):
            self.add_error("create_login", "Diese E-Mail wird bereits von einem anderen Login verwendet.")
        if password:
            try:
                password_validation.validate_password(password, User(email=email or ""))
            except forms.ValidationError as error:
                self.add_error("password", error)
        return cleaned


@admin.register(Person)
class PersonAdmin(AuditedAdmin):
    form = PersonAdminForm
    list_display = ["last_name", "first_name", "email", "birth_year", "is_active", "club", "registered"]
    list_filter = ["is_active", "club"]
    search_fields = ["last_name", "first_name", "email"]
    list_select_related = ["club", "user"]
    readonly_fields = ["login"]
    actions = ["invite_selected"]

    def get_fieldsets(self, request, obj=None):
        fields = ["last_name", "first_name", "email", "birth_year", "is_active", "club"]
        # Once registered, the password belongs to the person; only the link to the login remains.
        login = [] if obj is None else ["login"]
        if obj is None or not has_registered(obj):
            login += ["create_login", "password"]
        fieldsets = [(None, {"fields": fields}), ("Login", {"fields": login})]
        if obj is not None:
            fieldsets.append(("Daten", {"fields": AUDIT_FIELDS}))
        return fieldsets

    @admin.display(description="Login")
    def login(self, obj):
        user = getattr(obj, "user", None)
        if user is None:
            return "kein Login"
        state = "registriert" if user.has_usable_password() else "eingeladen, noch nicht registriert"
        return format_html(
            '<a href="{}">{}</a> ({})', reverse("admin:accounts_user_change", args=[user.pk]), user, state
        )

    @admin.display(description="registriert", boolean=True)
    def registered(self, obj):
        return has_registered(obj)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if form.cleaned_data.get("create_login") and not has_registered(obj):
            url, sent = invite(obj, request, form.cleaned_data.get("password") or None)
            self.message_user(request, invitation_message([(obj, url, sent)]), messages.WARNING)

    @admin.action(description="Login anlegen und Einladung senden")
    def invite_selected(self, request, queryset):
        invitations, skipped = [], []
        for person in queryset.select_related("user"):
            if not person.is_active or has_registered(person) or email_taken(person.email, person):
                skipped.append(str(person))
                continue
            invitations.append((person, *invite(person, request)))
        if invitations:
            self.message_user(request, invitation_message(invitations), messages.WARNING)
        if skipped:
            self.message_user(
                request,
                "Übersprungen (inaktiv, bereits registriert oder E-Mail von anderem Login belegt): "
                + ", ".join(skipped),
                messages.INFO,
            )


@admin.register(SquadLeadership)
class SquadLeadershipAdmin(AuditedAdmin):
    list_display = ["person", "squad", "valid_from", "valid_until"]
    list_filter = ["squad__club", "squad"]
    autocomplete_fields = ["person", "squad"]


@admin.register(SquadAssignment)
class SquadAssignmentAdmin(AuditedAdmin):
    list_display = ["person", "squad", "role", "valid_from", "valid_until"]
    list_filter = ["role", "squad__club", "squad"]
    autocomplete_fields = ["person", "squad"]


@admin.register(Attendance)
class AttendanceAdmin(AuditedAdmin):
    list_display = ["date", "squad", "person", "role", "created_by"]
    list_filter = ["role", "squad__club", "squad"]
    date_hierarchy = "date"
    autocomplete_fields = ["person", "squad"]
    readonly_fields = ["role"]
