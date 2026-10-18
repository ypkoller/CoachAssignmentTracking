"""Client IP behind reverse proxies, used by django-axes and django-ratelimit."""

from django.conf import settings


def client_ip(request) -> str | None:
    """Address of the client as seen by the outermost trusted proxy.

    Each trusted proxy appends the address it received the request from to
    `X-Forwarded-For`, so with N trusted proxies the client is the N-th entry from the
    right. Entries further left are set by the client and cannot be trusted. Without
    trusted proxies (`PROXY_COUNT = 0`) the header is ignored.
    """
    forwarded = [ip.strip() for ip in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")]
    forwarded = [ip for ip in forwarded if ip]
    if settings.PROXY_COUNT and len(forwarded) >= settings.PROXY_COUNT:
        return forwarded[-settings.PROXY_COUNT]
    # Requests built without a client (e.g. force_login in tests) have no REMOTE_ADDR.
    return request.META.get("REMOTE_ADDR")
