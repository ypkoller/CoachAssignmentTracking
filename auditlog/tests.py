import json
from contextlib import contextmanager
from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone

from accounts.audit import _current_user
from accounts.models import User
from training.models import Attendance, Person, Role, SquadAssignment, SquadLeadership, today
from training.tests import PW, Base

from .models import Action, AuditEntry


@contextmanager
def acting(user):
    """Changes outside a request, made as `user` (like `CurrentUserMiddleware`)."""
    token = _current_user.set(user)
    try:
        yield
    finally:
        _current_user.reset(token)


def entries_for(model, action=None):
    qs = AuditEntry.objects.filter(content_type=ContentType.objects.get_for_model(model))
    return qs.filter(action=action) if action else qs


class TrackingTest(Base):
    def test_toggle_logs_create_and_delete_with_actor(self):
        user = User.objects.get(persons=self.beat)
        self.client.force_login(user)
        data = {"person": self.beat.pk, "squad": self.jugi.pk, "date": today().isoformat()}
        self.client.post(reverse("toggle_attendance"), data)
        created = entries_for(Attendance, Action.CREATE).get()
        self.assertEqual(created.actor, user)
        self.assertEqual(created.actor_name, "beat Test (beat@example.ch)")
        self.assertEqual((created.club, created.squad), (self.club, self.jugi))
        self.assertIn(["Person", "", "beat Test"], created.changes)
        self.assertIn(["Funktion", "", "Hilfsleiter"], created.changes)
        self.assertIn(["Datum", "", f"{today():%d.%m.%Y}"], created.changes)

        self.client.post(reverse("toggle_attendance"), data)
        deleted = entries_for(Attendance, Action.DELETE).get()
        self.assertEqual(deleted.actor, user)
        self.assertIn(["Riege", "Jugi", ""], deleted.changes)

    def test_update_logs_only_changed_fields(self):
        assignment = SquadAssignment.objects.get(person=self.beat, squad=self.jugi)
        self.client.force_login(self.admin)
        self.client.post(
            reverse("admin:training_squadassignment_change", args=[assignment.pk]),
            {"person": self.beat.pk, "squad": self.jugi.pk, "role": Role.HEAD_LEADER,
             "valid_from": self.start.isoformat(), "valid_until": ""},
        )
        entry = entries_for(SquadAssignment, Action.UPDATE).get()
        self.assertEqual(entry.changes, [["Funktion", "Hilfsleiter", "Hauptleiter"]])
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.actor_name, "admin@example.ch")  # main administrator without club

    def test_save_without_change_writes_nothing(self):
        before = AuditEntry.objects.count()
        self.jugi.save()
        self.beat.save(update_fields=["is_active"])
        self.assertEqual(AuditEntry.objects.count(), before)

    def test_without_request_the_actor_is_system(self):
        self.jugi.name = "Jugend"
        self.jugi.save()
        entry = AuditEntry.objects.latest("id")
        self.assertIsNone(entry.actor)
        self.assertEqual(entry.actor_label, "System")
        self.assertEqual(entry.changes, [["Name", "Jugi", "Jugend"]])
        self.assertEqual((entry.club, entry.squad), (self.club, self.jugi))

    def test_password_hash_is_never_stored(self):
        user = User.objects.get(persons=self.beat)
        user.set_password("ein-anderes-Passwort-43")
        with acting(self.admin):
            user.save()
        entry = entries_for(User, Action.UPDATE).get()
        self.assertEqual(entry.changes, [["Passwort", "", "geändert"]])
        self.assertIsNone(entry.club)
        stored = json.dumps(list(AuditEntry.objects.values_list("changes", flat=True)))
        self.assertNotIn(user.password, stored)
        self.assertNotIn("argon2", stored)

    def test_login_writes_no_entry(self):
        before = AuditEntry.objects.count()
        self.client.post(reverse("login"), {"username": "beat@example.ch", "password": PW})
        self.assertIsNotNone(User.objects.get(persons=self.beat).last_login)
        self.assertEqual(AuditEntry.objects.count(), before)

    def test_login_email_change_logs_login_and_persons(self):
        user = User.objects.get(persons=self.beat)
        with acting(self.admin):
            user.email = "beat.neu@example.ch"
            user.save()
        change = ["E-Mail", "beat@example.ch", "beat.neu@example.ch"]
        self.assertEqual(entries_for(User, Action.UPDATE).get().changes, [change])
        person_entry = entries_for(Person, Action.UPDATE).get()
        self.assertEqual(person_entry.changes, [change])
        self.assertEqual(person_entry.club, self.club)

    def test_bulk_delete_in_admin_logs_cascade(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("admin:training_person_changelist"),
            {"action": "delete_selected", "_selected_action": [self.anna.pk], "post": "yes"},
        )
        self.assertFalse(Person.objects.filter(pk=self.anna.pk).exists())
        for model in (Person, SquadLeadership, SquadAssignment):
            entry = entries_for(model, Action.DELETE).get()
            self.assertEqual(entry.actor, self.admin)
            self.assertEqual(entry.club, self.club)

    def test_deleted_squad_keeps_its_entries(self):
        squad_id = self.apparatus.pk
        self.apparatus.delete()  # cascades the assignment of carla
        entry = AuditEntry.objects.get(action=Action.DELETE, object_id=squad_id, squad_id=squad_id)
        self.assertEqual(entry.object_repr, "Geräte")
        self.assertEqual(entries_for(SquadAssignment, Action.DELETE).get().squad_id, squad_id)


class ChangeLogViewTest(Base):
    def setUp(self):
        self.zora_user = User.objects.create_user(email="zora@example.ch", password=PW)
        self.zora = Person.objects.create(
            first_name="zora", last_name="Test", email="zora@example.ch", club=self.club,
            is_club_admin=True, user=self.zora_user,
        )
        self.xaver = Person.objects.create(
            first_name="xaver", last_name="Fremd", email="xaver@example.ch", club=self.other_club
        )
        self.url = reverse("audit_entries")

    def test_only_admins(self):
        self.client.force_login(User.objects.get(persons=self.beat))
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.get(reverse("audit_export")).status_code, 403)
        self.assertNotContains(self.client.get(reverse("record")), "Änderungsprotokoll")
        self.client.force_login(self.zora_user)
        self.assertContains(self.client.get(reverse("record")), "Änderungsprotokoll")

    def test_club_admin_sees_only_own_club(self):
        self.client.force_login(self.zora_user)
        response = self.client.get(self.url)
        self.assertContains(response, "zora Test")
        self.assertNotContains(response, "xaver")
        self.assertNotContains(response, 'name="club"')
        # Logins belong to no club: their entries are for the main administrator only.
        self.assertFalse(response.context["page"].paginator.object_list.filter(club=None).exists())

    def test_main_admin_sees_all(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertContains(response, "xaver Fremd")
        self.assertTrue(response.context["page"].paginator.object_list.filter(club=None).exists())

    def entry_ids(self, **params):
        response = self.client.get(self.url, params)
        return {e.pk for e in response.context["page"].paginator.object_list}

    def test_filters(self):
        self.client.force_login(self.admin)
        with acting(self.zora_user):
            self.carla.birth_year = 1990
            self.carla.save()
            leadership = SquadLeadership.objects.create(
                person=self.carla, squad=self.apparatus, valid_from=today()
            )
        old = entries_for(SquadLeadership, Action.CREATE).get(object_id=leadership.pk)
        by_zora = set(AuditEntry.objects.filter(actor=self.zora_user).values_list("pk", flat=True))
        self.assertEqual(self.entry_ids(actor=self.zora_user.pk), by_zora)
        in_squad = self.entry_ids(squad=self.apparatus.pk)
        self.assertIn(old.pk, in_squad)
        self.assertEqual(in_squad, set(AuditEntry.objects.filter(squad=self.apparatus).values_list("pk", flat=True)))
        self.assertEqual(self.entry_ids(club=self.other_club.pk),
                         set(AuditEntry.objects.filter(club=self.other_club).values_list("pk", flat=True)))
        area = ContentType.objects.get_for_model(SquadLeadership).pk
        self.assertEqual(self.entry_ids(area=area, actor=self.zora_user.pk), {old.pk})
        self.assertNotIn(old.pk, self.entry_ids(actor="system"))

        # Period: local days, inclusive.
        AuditEntry.objects.filter(pk=old.pk).update(timestamp=timezone.now() - timedelta(days=40))
        self.assertNotIn(old.pk, self.entry_ids())
        since = (today() - timedelta(days=41)).isoformat()
        self.assertIn(old.pk, self.entry_ids(**{"from": since}))

    def test_club_admin_cannot_filter_foreign_squad(self):
        self.client.force_login(self.zora_user)
        ids = self.entry_ids(squad=self.foreign_squad.pk)
        self.assertFalse(AuditEntry.objects.filter(pk__in=ids, club=self.other_club).exists())

    def test_export(self):
        Person.objects.create(
            first_name='=HYPERLINK("http://x")', last_name="Test", email="h@example.ch", club=self.club
        )
        self.client.force_login(self.admin)
        response = self.client.get(reverse("audit_export"), {"format": "csv"})
        content = response.content.decode("utf-8-sig")
        self.assertIn("System;Person;Erstellt;zora Test;STV Test;;Name;;Test", content)
        self.assertIn("'=HYPERLINK", content)
        self.assertNotIn(";=HYPERLINK", content)
        response = self.client.get(reverse("audit_export"), {"format": "xlsx"})
        self.assertTrue(response.content.startswith(b"PK"))
