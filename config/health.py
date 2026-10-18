from django.db import DatabaseError, connection
from django.http import HttpResponse

# Coolify requests the path without the trailing slash.
HEALTH_PATHS = {"/health", "/health/"}


class HealthCheckMiddleware:
    """Answers `/health/` before any other middleware.

    It runs before the host check, so that the container healthcheck works with
    `Host: localhost`, and does not touch sessions or authentication.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path not in HEALTH_PATHS:
            return self.get_response(request)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except DatabaseError:
            return HttpResponse("database unavailable", status=503, content_type="text/plain")
        return HttpResponse("ok", content_type="text/plain")
