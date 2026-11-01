from django.apps import AppConfig


class AuditlogConfig(AppConfig):
    name = "auditlog"
    verbose_name = "Änderungsprotokoll"

    def ready(self):
        from .tracking import connect

        connect()
