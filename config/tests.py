from unittest import mock

from django.db import OperationalError
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

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


class LoginLockoutTest(TestCase):
    @override_settings(PROXY_COUNT=1, AXES_FAILURE_LIMIT=2)
    def test_login_lockout_is_per_client_behind_proxy(self):
        def login(ip, email):
            return self.client.post(
                reverse("login"),
                {"username": email, "password": "falsch"},
                HTTP_X_FORWARDED_FOR=ip,
            )

        for _ in range(2):
            login("1.1.1.1", "a@example.ch")
        self.assertEqual(login("1.1.1.1", "x@example.ch").status_code, 429)
        self.assertEqual(login("2.2.2.2", "y@example.ch").status_code, 200)


@override_settings(ALLOWED_HOSTS=["training.example.ch"])
class HealthCheckTest(TestCase):
    def test_ok_without_allowed_host(self):
        response = self.client.get("/health/", HTTP_HOST="localhost")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")

    def test_database_unavailable(self):
        with mock.patch("config.health.connection.cursor", side_effect=OperationalError):
            response = self.client.get("/health/", HTTP_HOST="localhost")
        self.assertEqual(response.status_code, 503)
