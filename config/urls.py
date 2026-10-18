from django.contrib import admin
from django.urls import include, path

from accounts.views import admin_login

admin.site.site_header = "Trainingserfassung"
admin.site.site_title = "Trainingserfassung"

urlpatterns = [
    path("admin/login/", admin_login),
    path("admin/", admin.site.urls),
    path("account/", include("accounts.urls")),
    path("", include("training.urls")),
]
