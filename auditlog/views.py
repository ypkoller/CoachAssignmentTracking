from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import render
from django.utils import timezone

from training.permissions import can_view_audit, visible_audit_entries
from training.views import period, spreadsheet_response

from .forms import AuditFilterForm

PAGE_SIZE = 100


def filtered_entries(request):
    if not can_view_audit(request.user):
        raise PermissionDenied
    since, until = period(request)
    visible = visible_audit_entries(request.user)
    form = AuditFilterForm(request.GET, user=request.user, entries=visible)
    return form, since, until, form.apply(visible, since, until)


@login_required
def entries(request):
    """Change log: who changed what and when, with old and new values."""
    form, since, until, entries = filtered_entries(request)
    page = Paginator(entries, PAGE_SIZE).get_page(request.GET.get("page"))
    return render(
        request,
        "auditlog/entries.html",
        {"form": form, "since": since, "until": until, "page": page},
    )


@login_required
def export(request):
    """Change log as CSV or Excel: one row per changed field."""
    _, since, until, entries = filtered_entries(request)
    data = []
    for entry in entries:
        when = timezone.localtime(entry.timestamp).strftime("%d.%m.%Y %H:%M")
        common = [
            when,
            entry.actor_label,
            entry.area,
            entry.get_action_display(),
            entry.object_repr,
            str(entry.club or ""),
            str(entry.squad or ""),
        ]
        for field, old, new in entry.changes or [["", "", ""]]:
            data.append([*common, field, old, new])
    return spreadsheet_response(
        request,
        f"aenderungen_{since:%Y-%m-%d}_{until:%Y-%m-%d}",
        f"Änderungen vom {since:%d.%m.%Y} bis {until:%d.%m.%Y}",
        ["Zeitpunkt", "Geändert von", "Bereich", "Aktion", "Objekt", "Verein", "Riege", "Feld", "Alt", "Neu"],
        data,
        [17, 30, 18, 10, 35, 18, 18, 18, 25, 25],
    )
