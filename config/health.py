from django.db import DatabaseError, connection
from django.http import HttpResponse

HEALTH_PATH = "/health/"


class HealthCheckMiddleware:
    """Answers `/health/` before any other middleware.

    It runs before the host check, so that the container healthcheck works with
    `Host: localhost`, and does not touch sessions or authentication.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path != HEALTH_PATH:
            return self.get_response(request)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except DatabaseError:
            return HttpResponse("database unavailable", status=503, content_type="text/plain")
        return HttpResponse("ok", content_type="text/plain")
