from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Trainingserfassung"
admin.site.site_title = "Trainingserfassung"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("account/", include("accounts.urls")),
    path("", include("training.urls")),
]
