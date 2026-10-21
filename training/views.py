import csv
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST
from openpyxl import Workbook

from .forms import AssignmentForm
from .models import (
    Attendance,
    Person,
    Role,
    Squad,
    SquadAssignment,
    earliest_date,
    today,
    valid_on,
)
from .permissions import (
    can_edit_attendance,
    can_lead_squad,
    date_allowed,
    led_squads,
    person_of,
    unrestricted_dates,
    visible_attendances,
)


def parse_date[T](value: str | None, default: T) -> date | T:
    try:
        return date.fromisoformat(value) if value else default
    except ValueError:
        return default


def date_context(request, day: date) -> dict:
    return {
        "date": day,
        "date_min": None if unrestricted_dates(request.user) else earliest_date(),
        "date_max": today(),
        "date_allowed": date_allowed(request.user, day),
    }


def rows(request, assignments, day: date) -> list[dict]:
    """Per assignment: the existing attendance and whether the user may toggle it."""
    assignments = list(assignments.select_related("person", "squad"))
    attendances = {
        (a.person_id, a.squad_id): a
        for a in Attendance.objects.filter(
            date=day,
            squad_id__in={s.squad_id for s in assignments},
            person_id__in={s.person_id for s in assignments},
        )
    }
    return [
        {
            "person": s.person,
            "squad": s.squad,
            "role": s.get_role_display(),
            "attendance": attendances.get((s.person_id, s.squad_id)),
            "date": day,
            "can_edit": can_edit_attendance(request.user, s.person, s.squad, day),
        }
        for s in assignments
    ]


@login_required
def record(request):
    """Start page: pick a date, record your own squads on that date with one tap."""
    day = parse_date(request.GET.get("date"), today())
    person = person_of(request.user)
    own = (
        SquadAssignment.objects.filter(valid_on(day), person=person, squad__club=person.club)
        if person
        else SquadAssignment.objects.none()
    )
    context = {
        **date_context(request, day),
        "rows": rows(request, own.order_by("squad__name"), day),
        "led_squads": led_squads(request.user, day),
    }
    template = "training/_record_day.html" if request.headers.get("HX-Request") else "training/record.html"
    return render(request, template, context)


@login_required
def squad_day(request, squad_id: int):
    """Squad leader: record all assigned leaders of a squad on a given date."""
    squad = get_object_or_404(Squad.objects.select_related("club"), pk=squad_id)
    day = parse_date(request.GET.get("date"), today())
    if not can_lead_squad(request.user, squad, day):
        raise PermissionDenied
    assignments = SquadAssignment.objects.filter(valid_on(day), squad=squad).order_by(
        "role", "person__last_name", "person__first_name"
    )
    context = {
        **date_context(request, day),
        "squad": squad,
        "rows": rows(request, assignments, day),
    }
    template = "training/_squad_day.html" if request.headers.get("HX-Request") else "training/squad_day.html"
    return render(request, template, context)


@login_required
@require_POST
def toggle_attendance(request):
    """Records the attendance if none exists, otherwise deletes it. Response: button partial."""
    person = get_object_or_404(Person, pk=request.POST.get("person"))
    squad = get_object_or_404(Squad, pk=request.POST.get("squad"))
    day = parse_date(request.POST.get("date"), None)
    if day is None or not can_edit_attendance(request.user, person, squad, day):
        raise PermissionDenied

    error = None
    attendance = Attendance.objects.filter(person=person, squad=squad, date=day).first()
    if attendance:
        attendance.delete()
        attendance = None
    else:
        attendance = Attendance(person=person, squad=squad, date=day)
        try:
            attendance.full_clean()
            with transaction.atomic():
                attendance.save()
        except (ValidationError, IntegrityError) as exc:
            error = " ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            attendance = None

    assignment = SquadAssignment.objects.filter(valid_on(day), person=person, squad=squad).first()
    row = {
        "person": person,
        "squad": squad,
        "role": assignment.get_role_display() if assignment else "",
        "attendance": attendance,
        "date": day,
        "can_edit": True,
        "error": error,
    }
    mode = "person" if request.POST.get("mode") == "person" else "squad"
    html = render_to_string(
        "training/_attendance_row.html", {"row": row, "mode": mode}, request=request
    )
    return HttpResponse(html)


def period(request) -> tuple[date, date]:
    until = parse_date(request.GET.get("to"), today())
    since = parse_date(request.GET.get("from"), until.replace(day=1))
    return min(since, until), max(since, until)


def summary(request, since: date, until: date):
    return (
        visible_attendances(request.user)
        .filter(date__range=(since, until))
        .values("person__last_name", "person__first_name", "squad__name", "role")
        .annotate(count=Count("id"))
        .order_by("person__last_name", "person__first_name", "squad__name", "role")
    )


@login_required
def attendance_list(request):
    since, until = period(request)
    attendances = visible_attendances(request.user).filter(date__range=(since, until))
    roles = dict(Role.choices)
    summary_rows = [
        {**row, "role": roles[row["role"]]} for row in summary(request, since, until)
    ]
    return render(
        request,
        "training/attendance_list.html",
        {
            "since": since,
            "until": until,
            "attendances": attendances[:500],
            "count": attendances.count(),
            "summary": summary_rows,
        },
    )


def spreadsheet_safe(value):
    """Neutralise text that a spreadsheet would run as a formula (CSV/formula injection)."""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


@login_required
def export(request):
    """Number of attendances per person, squad and role in the period (CSV or Excel)."""
    since, until = period(request)
    roles = dict(Role.choices)
    header = ["Name", "Vorname", "Riege", "Funktion", "Anzahl Einsätze"]
    data = [
        [
            spreadsheet_safe(value)
            for value in (
                r["person__last_name"],
                r["person__first_name"],
                r["squad__name"],
                roles[r["role"]],
                r["count"],
            )
        ]
        for r in summary(request, since, until)
    ]
    filename = f"einsaetze_{since:%Y-%m-%d}_{until:%Y-%m-%d}"

    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
        response.write("﻿")  # BOM so that Excel detects the umlauts correctly
        writer = csv.writer(response, delimiter=";")
        # nosemgrep comments: csv-writer-injection; values went through spreadsheet_safe() above.
        writer.writerow(header)  # nosemgrep
        writer.writerows(data)  # nosemgrep
        return response

    wb = Workbook()
    ws = wb.active
    ws.title = "Einsätze"
    ws.append([f"Einsätze vom {since:%d.%m.%Y} bis {until:%d.%m.%Y}"])
    ws.append(header)
    for row in data:
        ws.append(row)
    for column, width in zip("ABCDE", (20, 20, 25, 15, 16)):
        ws.column_dimensions[column].width = width
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
    wb.save(response)
    return response


@login_required
def assignments(request, squad_id: int):
    """Squad leader: assign head and assistant leaders or remove them (via «valid until»)."""
    squad = get_object_or_404(Squad.objects.select_related("club"), pk=squad_id)
    if not can_lead_squad(request.user, squad, today()):
        raise PermissionDenied

    form = AssignmentForm(squad=squad)
    if request.method == "POST":
        if "end" in request.POST:
            assignment = get_object_or_404(SquadAssignment, pk=request.POST["end"], squad=squad)
            assignment.valid_until = parse_date(request.POST.get("valid_until"), today())
            try:
                assignment.full_clean()
                assignment.save()
                messages.success(request, f"Zuteilung von {assignment.person} beendet.")
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            return redirect("assignments", squad_id=squad.pk)

        form = AssignmentForm(request.POST, squad=squad)
        if form.is_valid():
            form.save()
            messages.success(request, f"{form.instance.person} wurde zugeteilt.")
            return redirect("assignments", squad_id=squad.pk)

    current = (
        SquadAssignment.objects.filter(squad=squad)
        .exclude(valid_until__lt=today())
        .select_related("person")
        .order_by("role", "person__last_name")
    )
    return render(
        request,
        "training/assignments.html",
        {"squad": squad, "assignments": current, "form": form, "today": today()},
    )


def manifest(request):
    return render(request, "manifest.webmanifest", content_type="application/manifest+json")


def service_worker(request):
    response = render(request, "sw.js", content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    return response


def home(request):
    return redirect("record")
