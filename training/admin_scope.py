"""Django admin restricted to the club of a club administrator (main administrator: everything)."""

from django.contrib import admin

from accounts.audit import AuditedAdmin

from .models import Club, Person, Squad
from .permissions import admin_club_id


class ClubScopeMixin:
    """Permissions for club administrators and choices limited to their club."""

    def _allowed(self, request) -> bool:
        return request.user.is_admin or admin_club_id(request.user) is not None

    def has_module_permission(self, request):
        return self._allowed(request)

    def has_view_permission(self, request, obj=None):
        return self._allowed(request)

    def has_add_permission(self, request, obj=None):
        return self._allowed(request)

    def has_change_permission(self, request, obj=None):
        return self._allowed(request)

    def has_delete_permission(self, request, obj=None):
        return self._allowed(request)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        club_id = None if request.user.is_admin else admin_club_id(request.user)
        if club_id is not None:
            model = db_field.related_model
            if model is Club:
                kwargs["queryset"] = Club.objects.filter(pk=club_id)
                kwargs["initial"] = club_id
            elif model in (Person, Squad):
                kwargs["queryset"] = model.objects.filter(club_id=club_id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)  # type: ignore[misc]


class ClubScopedAdmin(ClubScopeMixin, AuditedAdmin):
    # Lookup from the model to its club.
    club_lookup = "club"

    def get_list_filter(self, request):
        filters = super().get_list_filter(request)
        if request.user.is_admin:
            return filters
        # Club administrators only see their club; squads only those of their club.
        return [
            (f, admin.RelatedOnlyFieldListFilter) if f == "squad" else f
            for f in filters
            if isinstance(f, str) and not f.endswith("club")
        ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_admin:
            return qs
        return qs.filter(**{f"{self.club_lookup}_id": admin_club_id(request.user)})


class ClubScopedInline(ClubScopeMixin, admin.TabularInline):
    pass
