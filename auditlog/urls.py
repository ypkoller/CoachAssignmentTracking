from django.urls import path

from . import views

urlpatterns = [
    path("", views.entries, name="audit_entries"),
    path("export/", views.export, name="audit_export"),
]
