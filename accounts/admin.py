from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .audit import AUDIT_FIELDS, AuditedAdmin, AuditedAdminMixin
from .invitations import invitation_message, send_invitation
from .models import Invitation, User


@admin.register(User)
class UserAdmin(AuditedAdminMixin, BaseUserAdmin):
    ordering = ["email"]
    list_display = ["email", "person", "is_active", "is_superuser", "last_login"]
    list_filter = ["is_active", "is_superuser"]
    search_fields = ["email", "person__last_name", "person__first_name"]
    autocomplete_fields = ["person"]
    fieldsets = [
        (None, {"fields": ["email", "password", "person"]}),
        ("Rechte", {"fields": ["is_active", "is_staff", "is_superuser"]}),
        ("Daten", {"fields": ["last_login", *AUDIT_FIELDS]}),
    ]
    add_fieldsets = [
        (None, {"classes": ["wide"], "fields": ["email", "password1", "password2", "person"]}),
    ]
    filter_horizontal = []


@admin.register(Invitation)
class InvitationAdmin(AuditedAdmin):
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
