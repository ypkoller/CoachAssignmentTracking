from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("record/", views.record, name="record"),
    path("attendance/toggle/", views.toggle_attendance, name="toggle_attendance"),
    path("squad/<int:squad_id>/", views.squad_day, name="squad_day"),
    path("squad/<int:squad_id>/assignments/", views.assignments, name="assignments"),
    path("attendances/", views.attendance_list, name="attendance_list"),
    path("export/", views.export, name="export"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("sw.js", views.service_worker, name="service_worker"),
]
