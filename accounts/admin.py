from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from training.admin_scope import ClubScopedAdmin
from training.models import Person

from .audit import AUDIT_FIELDS, AuditedAdminMixin
from .invitations import invitation_message, send_invitation
from .models import Invitation, User

PERSON_FIELDS = ("last_name", "first_name", "club", "is_active", "is_club_admin")


class PersonInline(admin.TabularInline):
    """The persons (one per club) of a login; edited in the person admin."""

    model = Person
    fk_name = "user"
    fields = PERSON_FIELDS
    readonly_fields = PERSON_FIELDS
    extra = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(AuditedAdminMixin, BaseUserAdmin):
    """Logins, main administrator only (a login can belong to several clubs)."""

    ordering = ["email"]
    list_display = ["email", "is_active", "is_superuser", "last_login"]
    list_filter = ["is_active", "is_superuser"]
    search_fields = ["email", "persons__last_name", "persons__first_name"]
    fieldsets = [
        (None, {"fields": ["email", "password"]}),
        ("Rechte", {"fields": ["is_active", "is_superuser"]}),
        ("Daten", {"fields": ["last_login", *AUDIT_FIELDS]}),
    ]
    add_fieldsets = [
        (None, {"classes": ["wide"], "fields": ["email", "password1", "password2"]}),
    ]
    filter_horizontal = []
    inlines = [PersonInline]


@admin.register(Invitation)
class InvitationAdmin(ClubScopedAdmin):
    club_lookup = "person__club"
    list_display = ["person", "expires_at", "used_at", "created_at"]
    autocomplete_fields = ["person"]
    readonly_fields = ["used_at"]

    def get_readonly_fields(self, request, obj=None):
        # An existing token cannot be shown again; do not allow changing the person.
        fields = super().get_readonly_fields(request, obj)
        return [*fields, "person"] if obj else fields

    def save_model(self, request, obj, form, change):
        if change:
            return super().save_model(request, obj, form, change)
        url, sent = send_invitation(obj, request)
        messages.warning(request, invitation_message([(obj.person, url, sent)]))
