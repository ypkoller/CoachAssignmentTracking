from datetime import timedelta
from unittest import mock

from axes.models import AccessAttempt
from django.db import OperationalError
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .client_ip import client_ip


class ClientIpTest(SimpleTestCase):
    def request(self, forwarded=None):
        headers = {"HTTP_X_FORWARDED_FOR": forwarded} if forwarded else {}
        return RequestFactory().get("/", REMOTE_ADDR="10.0.0.2", **headers)

    @override_settings(PROXY_COUNT=0)
    def test_without_proxy_the_header_is_ignored(self):
        self.assertEqual(client_ip(self.request("1.2.3.4")), "10.0.0.2")

    @override_settings(PROXY_COUNT=1)
    def test_behind_one_proxy_the_rightmost_entry_is_the_client(self):
        self.assertEqual(client_ip(self.request("6.6.6.6, 1.2.3.4")), "1.2.3.4")

    @override_settings(PROXY_COUNT=1)
    def test_behind_proxy_without_header_falls_back_to_remote_addr(self):
        self.assertEqual(client_ip(self.request()), "10.0.0.2")


@override_settings(PROXY_COUNT=1)
class LoginLockoutTest(TestCase):
    def login(self, ip, email):
        return self.client.post(
            reverse("login"),
            {"username": email, "password": "falsch"},
            HTTP_X_FORWARDED_FOR=ip,
        )

    def fail_logins(self, ip, email, times=5):
        for _ in range(times):
            self.login(ip, email)

    def test_fifth_failure_locks_ip_and_username_together(self):
        for _ in range(4):
            self.assertEqual(self.login("1.1.1.1", "a@example.ch").status_code, 200)
        self.assertEqual(self.login("1.1.1.1", "a@example.ch").status_code, 429)
        self.assertEqual(self.login("1.1.1.1", "a@example.ch").status_code, 429)
        # Neither another login from the same IP nor the same login from another IP is locked.
        self.assertEqual(self.login("1.1.1.1", "b@example.ch").status_code, 200)
        self.assertEqual(self.login("2.2.2.2", "a@example.ch").status_code, 200)

    def test_lock_ends_after_30_minutes(self):
        self.fail_logins("1.1.1.1", "a@example.ch")
        for minutes, status in [(29, 429), (31, 200)]:
            # Moves the recorded failures back in time (the axes table, not app data).
            attempt_time = timezone.now() - timedelta(minutes=minutes)
            AccessAttempt.objects.update(attempt_time=attempt_time)
            self.assertEqual(self.login("1.1.1.1", "a@example.ch").status_code, status)


@override_settings(ALLOWED_HOSTS=["training.example.ch"])
class HealthCheckTest(TestCase):
    def test_ok_without_allowed_host(self):
        response = self.client.get("/health/", HTTP_HOST="localhost")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")

    def test_ok_without_trailing_slash(self):
        response = self.client.get("/health", HTTP_HOST="localhost:8000")
        self.assertEqual(response.status_code, 200)

    def test_database_unavailable(self):
        with mock.patch("config.health.connection.cursor", side_effect=OperationalError):
            response = self.client.get("/health/", HTTP_HOST="localhost")
        self.assertEqual(response.status_code, 503)
