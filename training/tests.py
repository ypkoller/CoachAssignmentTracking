from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from accounts.models import Invitation, User

from .models import (
    Attendance,
    Club,
    Person,
    Role,
    Squad,
    SquadAssignment,
    SquadLeadership,
    today,
)
from .permissions import can_edit_attendance, visible_attendances

PW = "ein-sicheres-Passwort-42"


class Base(TestCase):
    club: Club
    other_club: Club
    jugi: Squad
    apparatus: Squad
    foreign_squad: Squad
    start: date
    anna: Person
    beat: Person
    carla: Person
    a_anna: SquadAssignment
    admin: User

    @classmethod
    def setUpTestData(cls):
        cls.club = Club.objects.create(name="STV Test")
        cls.other_club = Club.objects.create(name="TV Anders")
        cls.jugi = Squad.objects.create(name="Jugi", club=cls.club)
        cls.apparatus = Squad.objects.create(name="Geräte", club=cls.club)
        cls.foreign_squad = Squad.objects.create(name="Fremd", club=cls.other_club)
        cls.start = today() - timedelta(days=60)

        def person(first_name):
            p = Person.objects.create(
                first_name=first_name,
                last_name="Test",
                email=f"{first_name}@example.ch",
                club=cls.club,
            )
            User.objects.create_user(email=p.email, password=PW, person=p)
            return p

        cls.anna = person("anna")  # squad leader Jugi, head leader Jugi
        cls.beat = person("beat")  # assistant leader Jugi
        cls.carla = person("carla")  # head leader apparatus
        SquadLeadership.objects.create(person=cls.anna, squad=cls.jugi, valid_from=cls.start)
        cls.a_anna = SquadAssignment.objects.create(
            person=cls.anna, squad=cls.jugi, role=Role.HEAD_LEADER, valid_from=cls.start
        )
        SquadAssignment.objects.create(
            person=cls.beat, squad=cls.jugi, role=Role.ASSISTANT_LEADER, valid_from=cls.start
        )
        SquadAssignment.objects.create(
            person=cls.carla, squad=cls.apparatus, role=Role.HEAD_LEADER, valid_from=cls.start
        )
        cls.admin = User.objects.create_superuser(email="admin@example.ch", password=PW)

    def attendance(self, person, squad, days_back=1):
        a = Attendance(person=person, squad=squad, date=today() - timedelta(days=days_back))
        a.full_clean()
        a.save()
        return a


class DatabaseRulesTest(Base):
    def test_r5_overlapping_assignment_rejected_by_db(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            SquadAssignment.objects.create(
                person=self.anna, squad=self.jugi, role=Role.ASSISTANT_LEADER,
                valid_from=today(),
            )

    def test_r5_consecutive_assignments_allowed(self):
        self.a_anna.valid_until = today() - timedelta(days=1)
        self.a_anna.save()
        SquadAssignment.objects.create(
            person=self.anna, squad=self.jugi, role=Role.ASSISTANT_LEADER, valid_from=today()
        )

    def test_r5_also_validated_in_clean(self):
        a = SquadAssignment(
            person=self.anna, squad=self.jugi, role=Role.ASSISTANT_LEADER, valid_from=today()
        )
        with self.assertRaises(ValidationError):
            a.full_clean()

    def test_r7_until_before_from(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            SquadLeadership.objects.create(
                person=self.beat, squad=self.apparatus, valid_from=today(),
                valid_until=today() - timedelta(days=1),
            )

    def test_r8_trigger_prevents_foreign_club(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            SquadAssignment.objects.create(
                person=self.anna, squad=self.foreign_squad, role=Role.ASSISTANT_LEADER
            )

    def test_r8_clean(self):
        a = SquadAssignment(person=self.anna, squad=self.foreign_squad, role=Role.ASSISTANT_LEADER)
        with self.assertRaises(ValidationError):
            a.full_clean()

    def test_r9_trigger_without_assignment(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Attendance.objects.create(person=self.beat, squad=self.apparatus, date=today())

    def test_r9_trigger_takes_role(self):
        # Deliberately wrong role: the trigger sets the role from the assignment.
        a = Attendance.objects.create(
            person=self.beat, squad=self.jugi, date=today(), role=Role.HEAD_LEADER
        )
        a.refresh_from_db()
        self.assertEqual(a.role, Role.ASSISTANT_LEADER)

    def test_r9_clean_takes_role(self):
        a = self.attendance(self.anna, self.jugi)
        self.assertEqual(a.role, Role.HEAD_LEADER)

    def test_r10_one_attendance_per_day(self):
        self.attendance(self.beat, self.jugi)
        with self.assertRaises(ValidationError):
            self.attendance(self.beat, self.jugi)

    def test_r11_one_head_leader_per_squad_and_day(self):
        dora = Person.objects.create(
            first_name="Dora", last_name="Test", email="dora@example.ch", club=self.club
        )
        SquadAssignment.objects.create(
            person=dora, squad=self.jugi, role=Role.HEAD_LEADER, valid_from=self.start
        )
        self.attendance(self.anna, self.jugi)
        with self.assertRaises(ValidationError):
            self.attendance(dora, self.jugi)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Attendance.objects.create(person=dora, squad=self.jugi, date=today() - timedelta(days=1))

    def test_r13_no_future(self):
        with self.assertRaises(ValidationError):
            self.attendance(self.anna, self.jugi, days_back=-1)

    def test_assignment_cannot_end_before_recorded_attendances(self):
        self.attendance(self.anna, self.jugi, days_back=1)
        self.a_anna.valid_until = today() - timedelta(days=5)
        with self.assertRaises(ValidationError):
            self.a_anna.full_clean()

    def test_email_case_insensitive_unique(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Person.objects.create(first_name="X", last_name="Y", email="ANNA@example.ch", club=self.club)


class PermissionsTest(Base):
    def user(self, person):
        return User.objects.get(person=person)

    def test_leader_may_edit_own_attendances(self):
        self.assertTrue(can_edit_attendance(self.user(self.beat), self.beat, self.jugi, today()))

    def test_leader_may_not_edit_others(self):
        self.assertFalse(can_edit_attendance(self.user(self.beat), self.anna, self.jugi, today()))

    def test_leader_only_for_assigned_squads(self):
        self.assertFalse(can_edit_attendance(self.user(self.beat), self.beat, self.apparatus, today()))

    def test_squad_leader_may_edit_for_assigned_leaders(self):
        self.assertTrue(can_edit_attendance(self.user(self.anna), self.beat, self.jugi, today()))

    def test_squad_leader_not_for_other_squad(self):
        self.assertFalse(can_edit_attendance(self.user(self.anna), self.carla, self.apparatus, today()))

    def test_r12_30_days(self):
        user = self.user(self.beat)
        self.assertTrue(can_edit_attendance(user, self.beat, self.jugi, today() - timedelta(days=30)))
        self.assertFalse(can_edit_attendance(user, self.beat, self.jugi, today() - timedelta(days=31)))

    def test_admin_without_30_day_limit_but_not_in_future(self):
        self.assertTrue(can_edit_attendance(self.admin, self.beat, self.jugi, today() - timedelta(days=50)))
        self.assertFalse(can_edit_attendance(self.admin, self.beat, self.jugi, today() + timedelta(days=1)))

    def test_visibility(self):
        a_beat = self.attendance(self.beat, self.jugi)
        a_carla = self.attendance(self.carla, self.apparatus)
        self.assertEqual(set(visible_attendances(self.user(self.beat))), {a_beat})
        self.assertEqual(set(visible_attendances(self.user(self.anna))), {a_beat})
        self.assertEqual(set(visible_attendances(self.admin)), {a_beat, a_carla})


class AuditTest(Base):
    def test_create_sets_updated_equal_to_created(self):
        club = Club.objects.create(name="Neu")
        self.assertIsNotNone(club.created_at)
        self.assertEqual(club.updated_at, club.created_at)
        self.assertIsNone(club.created_by)  # no request: no acting user
        self.assertIsNone(club.updated_by)

    def test_update_changes_only_updated_fields(self):
        created_at = self.jugi.created_at
        self.jugi.name = "Jugend"
        self.jugi.save()
        self.jugi.refresh_from_db()
        self.assertEqual(self.jugi.created_at, created_at)
        self.assertGreater(self.jugi.updated_at, created_at)

    def test_update_fields_include_audit_fields(self):
        created_at = self.beat.created_at
        self.beat.is_active = False
        self.beat.save(update_fields=["is_active"])
        self.beat.refresh_from_db()
        self.assertGreater(self.beat.updated_at, created_at)

    def test_login_is_not_a_change(self):
        user = User.objects.get(person=self.beat)
        updated_at = user.updated_at
        self.client.post(reverse("login"), {"username": user.email, "password": PW})
        user.refresh_from_db()
        self.assertIsNotNone(user.last_login)
        self.assertEqual(user.updated_at, updated_at)

    def test_request_user_is_recorded(self):
        user = User.objects.get(person=self.beat)
        self.client.force_login(user)
        data = {"person": self.beat.pk, "squad": self.jugi.pk, "date": today().isoformat()}
        self.client.post(reverse("toggle_attendance"), data)
        attendance = Attendance.objects.get()
        self.assertEqual(attendance.created_by, user)
        self.assertEqual(attendance.updated_by, user)
        self.assertEqual(attendance.updated_at, attendance.created_at)

    def test_update_by_other_user_keeps_creator(self):
        self.client.force_login(User.objects.get(person=self.anna))
        url = reverse("assignments", args=[self.jugi.pk])
        self.client.post(url, {"person": self.carla.pk, "role": Role.ASSISTANT_LEADER, "valid_from": today().isoformat()})
        assignment = SquadAssignment.objects.get(person=self.carla, squad=self.jugi)
        self.client.force_login(self.admin)
        self.client.post(
            reverse("admin:training_squadassignment_change", args=[assignment.pk]),
            {"person": self.carla.pk, "squad": self.jugi.pk, "role": Role.ASSISTANT_LEADER,
             "valid_from": today().isoformat(), "valid_until": today().isoformat()},
        )
        assignment.refresh_from_db()
        self.assertEqual(assignment.valid_until, today())
        self.assertEqual(assignment.created_by, User.objects.get(person=self.anna))
        self.assertEqual(assignment.updated_by, self.admin)


class ViewsTest(Base):
    def test_login_required(self):
        response = self.client.get(reverse("record"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('record')}")

    def test_login_with_email_case_insensitive(self):
        response = self.client.post(reverse("login"), {"username": "BEAT@example.ch", "password": PW})
        self.assertRedirects(response, reverse("record"))

    def test_record_shows_own_squads(self):
        self.client.force_login(User.objects.get(person=self.beat))
        response = self.client.get(reverse("record"))
        self.assertContains(response, "Jugi")
        self.assertNotContains(response, "Geräte")

    def test_toggle_records_and_deletes(self):
        self.client.force_login(User.objects.get(person=self.beat))
        data = {"person": self.beat.pk, "squad": self.jugi.pk, "date": today().isoformat()}
        response = self.client.post(reverse("toggle_attendance"), data)
        self.assertContains(response, "Erfasst")
        self.assertEqual(Attendance.objects.count(), 1)
        self.client.post(reverse("toggle_attendance"), data)
        self.assertEqual(Attendance.objects.count(), 0)

    def test_toggle_for_other_person_forbidden(self):
        self.client.force_login(User.objects.get(person=self.beat))
        data = {"person": self.anna.pk, "squad": self.jugi.pk, "date": today().isoformat()}
        self.assertEqual(self.client.post(reverse("toggle_attendance"), data).status_code, 403)

    def test_squad_page_only_for_squad_leaders(self):
        self.client.force_login(User.objects.get(person=self.beat))
        self.assertEqual(self.client.get(reverse("squad_day", args=[self.jugi.pk])).status_code, 403)
        self.client.force_login(User.objects.get(person=self.anna))
        self.assertContains(self.client.get(reverse("squad_day", args=[self.jugi.pk])), "beat Test")

    def test_squad_leader_assigns_and_ends(self):
        self.client.force_login(User.objects.get(person=self.anna))
        url = reverse("assignments", args=[self.jugi.pk])
        self.client.post(url, {"person": self.carla.pk, "role": "ASSISTANT_LEADER", "valid_from": today().isoformat()})
        a = SquadAssignment.objects.get(person=self.carla, squad=self.jugi)
        self.client.post(url, {"end": a.pk, "valid_until": today().isoformat()})
        a.refresh_from_db()
        self.assertEqual(a.valid_until, today())

    def test_export_csv_and_xlsx(self):
        self.attendance(self.beat, self.jugi, 1)
        self.attendance(self.beat, self.jugi, 2)
        self.client.force_login(self.admin)
        since = (today() - timedelta(days=10)).isoformat()
        response = self.client.get(reverse("export"), {"from": since, "format": "csv"})
        content = response.content.decode("utf-8-sig")
        self.assertIn("Test;beat;Jugi;Hilfsleiter;2", content)
        response = self.client.get(reverse("export"), {"from": since, "format": "xlsx"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"PK"))

    def test_inactive_person_loses_access_immediately(self):
        self.client.force_login(User.objects.get(person=self.beat))
        self.assertEqual(self.client.get(reverse("record")).status_code, 200)
        self.beat.is_active = False
        self.beat.save()
        self.assertEqual(self.client.get(reverse("record")).status_code, 302)

    def test_invitation_registration(self):
        dora = Person.objects.create(first_name="Dora", last_name="Neu", email="dora@example.ch", club=self.club)
        invitation = Invitation(person=dora)
        token = invitation.generate_token()
        invitation.save()
        url = reverse("register", args=[token])
        response = self.client.post(url, {"password1": PW, "password2": PW})
        self.assertRedirects(response, reverse("record"))
        self.assertTrue(User.objects.get(person=dora).check_password(PW))
        # One-time token: a second use fails.
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 404)
