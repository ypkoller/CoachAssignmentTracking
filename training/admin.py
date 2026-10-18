from django.contrib import admin

from accounts.audit import AuditedAdmin

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


@admin.register(Person)
class PersonAdmin(AuditedAdmin):
    list_display = ["last_name", "first_name", "email", "birth_year", "is_active", "club"]
    list_filter = ["is_active", "club"]
    search_fields = ["last_name", "first_name", "email"]


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
