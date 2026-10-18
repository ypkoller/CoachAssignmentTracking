from datetime import date, timedelta

from django.core import mail
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from accounts.clubs import SESSION_KEY
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
            email = f"{first_name}@example.ch"
            user = User.objects.create_user(email=email, password=PW)
            return Person.objects.create(
                first_name=first_name, last_name="Test", email=email, club=cls.club, user=user
            )

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

    def test_email_case_insensitive_unique_per_club(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Person.objects.create(first_name="X", last_name="Y", email="ANNA@example.ch", club=self.club)
        # In another club the same email is allowed (R3).
        Person.objects.create(first_name="X", last_name="Y", email="ANNA@example.ch", club=self.other_club)

    def test_person_email_belongs_to_login(self):
        self.anna.email = "neu@example.ch"
        with self.assertRaises(ValidationError):
            self.anna.full_clean()

    def test_login_email_change_updates_its_persons(self):
        user = User.objects.get(persons=self.anna)
        user.email = "Neu@Example.ch"
        user.save()
        self.anna.refresh_from_db()
        self.assertEqual(self.anna.email, "neu@example.ch")


class PermissionsTest(Base):
    def user(self, person):
        user = User.objects.get(persons=person)
        user.person = person  # club chosen at login
        return user

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
        user = User.objects.get(persons=self.beat)
        updated_at = user.updated_at
        self.client.post(reverse("login"), {"username": user.email, "password": PW})
        user.refresh_from_db()
        self.assertIsNotNone(user.last_login)
        self.assertEqual(user.updated_at, updated_at)

    def test_request_user_is_recorded(self):
        user = User.objects.get(persons=self.beat)
        self.client.force_login(user)
        data = {"person": self.beat.pk, "squad": self.jugi.pk, "date": today().isoformat()}
        self.client.post(reverse("toggle_attendance"), data)
        attendance = Attendance.objects.get()
        self.assertEqual(attendance.created_by, user)
        self.assertEqual(attendance.updated_by, user)
        self.assertEqual(attendance.updated_at, attendance.created_at)

    def test_update_by_other_user_keeps_creator(self):
        self.client.force_login(User.objects.get(persons=self.anna))
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
        self.assertEqual(assignment.created_by, User.objects.get(persons=self.anna))
        self.assertEqual(assignment.updated_by, self.admin)


class ViewsTest(Base):
    def test_login_required(self):
        response = self.client.get(reverse("record"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('record')}")

    def test_login_with_email_case_insensitive(self):
        response = self.client.post(reverse("login"), {"username": "BEAT@example.ch", "password": PW})
        self.assertRedirects(response, reverse("record"))

    def test_record_shows_own_squads(self):
        self.client.force_login(User.objects.get(persons=self.beat))
        response = self.client.get(reverse("record"))
        self.assertContains(response, "Jugi")
        self.assertNotContains(response, "Geräte")

    def test_toggle_records_and_deletes(self):
        self.client.force_login(User.objects.get(persons=self.beat))
        data = {"person": self.beat.pk, "squad": self.jugi.pk, "date": today().isoformat()}
        response = self.client.post(reverse("toggle_attendance"), data)
        self.assertContains(response, "Erfasst")
        self.assertEqual(Attendance.objects.count(), 1)
        self.client.post(reverse("toggle_attendance"), data)
        self.assertEqual(Attendance.objects.count(), 0)

    def test_toggle_for_other_person_forbidden(self):
        self.client.force_login(User.objects.get(persons=self.beat))
        data = {"person": self.anna.pk, "squad": self.jugi.pk, "date": today().isoformat()}
        self.assertEqual(self.client.post(reverse("toggle_attendance"), data).status_code, 403)

    def test_squad_page_only_for_squad_leaders(self):
        self.client.force_login(User.objects.get(persons=self.beat))
        self.assertEqual(self.client.get(reverse("squad_day", args=[self.jugi.pk])).status_code, 403)
        self.client.force_login(User.objects.get(persons=self.anna))
        self.assertContains(self.client.get(reverse("squad_day", args=[self.jugi.pk])), "beat Test")

    def test_squad_leader_assigns_and_ends(self):
        self.client.force_login(User.objects.get(persons=self.anna))
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
        self.client.force_login(User.objects.get(persons=self.beat))
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
        self.assertTrue(User.objects.get(persons=dora).check_password(PW))
        # One-time token: a second use fails.
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 404)


class PersonLoginAdminTest(Base):
    add_url = reverse("admin:training_person_add")

    def setUp(self):
        self.client.force_login(self.admin)

    def add_person(self, email="dora@example.ch", **extra):
        data = {
            "last_name": "Neu",
            "first_name": "Dora",
            "email": email,
            "is_active": "on",
            "club": self.club.pk,
            "create_login": "on",
            **extra,
        }
        return self.client.post(self.add_url, data, follow=True)

    def invitation_link(self):
        return mail.outbox[-1].body.split("http://testserver")[1].split()[0]

    def test_create_login_sends_invitation(self):
        response = self.add_person()
        self.assertContains(response, "Einladungslinks")
        user = User.objects.get(persons__email="dora@example.ch")
        self.assertFalse(user.has_usable_password())
        self.assertEqual(mail.outbox[-1].to, ["dora@example.ch"])
        response = self.client.post(self.invitation_link(), {"password1": PW, "password2": PW})
        self.assertRedirects(response, reverse("record"))
        user.refresh_from_db()
        self.assertTrue(user.check_password(PW))

    def test_create_login_with_start_password(self):
        self.add_person(password=PW)
        self.assertTrue(User.objects.get(persons__email="dora@example.ch").check_password(PW))
        self.assertEqual(len(mail.outbox), 1)

    def test_weak_start_password_rejected(self):
        response = self.add_person(password="1234")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Person.objects.filter(email="dora@example.ch").exists())

    def test_existing_login_is_linked_without_invitation(self):
        response = self.add_person(email="anna@example.ch", club=self.other_club.pk)
        self.assertContains(response, "bestehender Login verknüpft")
        person = Person.objects.get(email="anna@example.ch", club=self.other_club)
        self.assertEqual(person.user, self.anna.user)
        self.assertEqual(len(mail.outbox), 0)

    def test_no_start_password_for_existing_login(self):
        self.add_person(email="anna@example.ch", club=self.other_club.pk, password=PW + "x")
        self.assertFalse(Person.objects.filter(email="anna@example.ch", club=self.other_club).exists())
        self.assertTrue(User.objects.get(persons=self.anna).check_password(PW))

    def test_without_checkbox_no_login(self):
        self.add_person(create_login="")
        self.assertFalse(User.objects.filter(email="dora@example.ch").exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_registered_person_has_no_login_fields(self):
        response = self.client.get(reverse("admin:training_person_change", args=[self.anna.pk]))
        self.assertContains(response, "registriert")
        self.assertNotContains(response, 'name="create_login"')

    def test_action_invites_only_unregistered_active_persons(self):
        dora = Person.objects.create(first_name="Dora", last_name="Neu", email="dora@example.ch", club=self.club)
        emil = Person.objects.create(
            first_name="Emil", last_name="Alt", email="emil@example.ch", club=self.club, is_active=False
        )
        data = {"action": "invite_selected", "_selected_action": [dora.pk, emil.pk, self.anna.pk]}
        response = self.client.post(reverse("admin:training_person_changelist"), data, follow=True)
        self.assertContains(response, "Übersprungen")
        self.assertEqual([m.to for m in mail.outbox], [["dora@example.ch"]])
        self.assertFalse(User.objects.get(persons=dora).has_usable_password())
        self.assertFalse(User.objects.filter(persons=emil).exists())
        # Not yet registered: running it again issues a new invitation.
        self.client.post(reverse("admin:training_person_changelist"), data)
        self.assertEqual(len(mail.outbox), 2)


    def test_resend_invitation_renews_link(self):
        self.add_person()
        old_link = self.invitation_link()
        invitation = Invitation.objects.get(person__email="dora@example.ch")
        Invitation.objects.filter(pk=invitation.pk).update(expires_at=invitation.created_at)
        used = Invitation.objects.create(person=self.anna, token_hash="x", used_at=invitation.created_at)
        data = {"action": "resend_selected", "_selected_action": [invitation.pk, used.pk]}
        response = self.client.post(reverse("admin:accounts_invitation_changelist"), data, follow=True)
        self.assertContains(response, "Einladungslinks")
        self.assertContains(response, "Übersprungen")
        self.assertEqual(len(mail.outbox), 2)
        self.assertNotEqual(self.invitation_link(), old_link)
        self.assertEqual(self.client.get(old_link).status_code, 404)
        self.assertEqual(self.client.get(self.invitation_link()).status_code, 200)

class ClubLoginTest(Base):
    def setUp(self):
        # Anna is also a member of the other club (same login).
        self.anna_other = Person.objects.create(
            first_name="anna", last_name="Test", email="anna@example.ch", club=self.other_club,
            user=self.anna.user,
        )

    def login(self, email, club=None):
        data = {"username": email, "password": PW, **({"club": club.pk} if club else {})}
        return self.client.post(reverse("login"), data)

    def test_single_club_needs_no_club(self):
        self.assertRedirects(self.login("beat@example.ch"), reverse("record"))
        self.assertEqual(self.client.session[SESSION_KEY], self.club.pk)

    def test_several_clubs_need_club(self):
        self.assertContains(self.login("anna@example.ch"), "mehreren Vereinen")
        self.assertRedirects(self.login("anna@example.ch", self.other_club), reverse("record"))
        self.assertEqual(self.client.session[SESSION_KEY], self.other_club.pk)

    def test_club_without_person_rejected(self):
        self.assertContains(self.login("beat@example.ch", self.other_club), "nicht erfasst")

    def test_main_admin_needs_no_club(self):
        self.assertRedirects(self.login("admin@example.ch"), reverse("record"))
        self.assertIsNone(self.client.session[SESSION_KEY])

    def test_switch_club(self):
        self.login("anna@example.ch", self.club)
        self.assertContains(self.client.get(reverse("record")), "Wechseln zu TV Anders")
        response = self.client.post(reverse("switch_club"), {"club": self.other_club.pk})
        self.assertRedirects(response, reverse("record"))
        self.assertEqual(self.client.session[SESSION_KEY], self.other_club.pk)
        # Squad leader of Jugi only in the first club.
        self.assertEqual(self.client.get(reverse("squad_day", args=[self.jugi.pk])).status_code, 403)

    def test_switch_to_foreign_club_forbidden(self):
        self.login("beat@example.ch")
        response = self.client.post(reverse("switch_club"), {"club": self.other_club.pk})
        self.assertEqual(response.status_code, 403)

    def test_deactivated_person_ends_session_in_that_club(self):
        self.login("anna@example.ch", self.other_club)
        self.anna_other.is_active = False
        self.anna_other.save()
        self.assertRedirects(
            self.client.get(reverse("record")), f"{reverse('login')}?next={reverse('record')}"
        )
        # The login still works in the other club.
        self.assertRedirects(self.login("anna@example.ch"), reverse("record"))

    def test_admin_login_uses_normal_login(self):
        response = self.client.get("/admin/login/?next=/admin/")
        self.assertRedirects(response, f"{reverse('login')}?next=/admin/", fetch_redirect_response=False)
        self.login("beat@example.ch")
        self.assertEqual(self.client.get("/admin/login/?next=/admin/").status_code, 403)


class ClubAdminTest(Base):
    def setUp(self):
        self.zora_user = User.objects.create_user(email="zora@example.ch", password=PW)
        self.zora = Person.objects.create(
            first_name="zora", last_name="Test", email="zora@example.ch", club=self.club,
            is_club_admin=True, user=self.zora_user,
        )
        self.xaver = Person.objects.create(
            first_name="xaver", last_name="Fremd", email="xaver@example.ch", club=self.other_club
        )
        SquadAssignment.objects.create(
            person=self.xaver, squad=self.foreign_squad, role=Role.HEAD_LEADER, valid_from=self.start
        )
        self.client.force_login(self.zora_user)

    def user(self):
        self.zora_user.person = self.zora
        return self.zora_user

    def test_admin_shows_only_club_models(self):
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, "Personen")
        self.assertContains(response, reverse("admin:accounts_invitation_changelist"))
        self.assertNotContains(response, reverse("admin:training_club_changelist"))
        self.assertNotContains(response, reverse("admin:accounts_user_changelist"))
        self.assertEqual(self.client.get(reverse("admin:accounts_user_changelist")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:training_club_changelist")).status_code, 403)

    def test_only_own_club_visible(self):
        response = self.client.get(reverse("admin:training_person_changelist"))
        self.assertContains(response, "anna")
        self.assertNotContains(response, "xaver")
        response = self.client.get(reverse("admin:training_person_change", args=[self.xaver.pk]))
        self.assertEqual(response.status_code, 302)  # "does not exist"
        response = self.client.get(reverse("admin:training_squadassignment_changelist"))
        self.assertNotContains(response, "Fremd")

    def test_foreign_person_cannot_be_assigned(self):
        data = {"person": self.xaver.pk, "squad": self.jugi.pk, "role": Role.ASSISTANT_LEADER,
                "valid_from": today().isoformat()}
        response = self.client.post(reverse("admin:training_squadassignment_add"), data)
        self.assertEqual(response.status_code, 200)  # form error
        self.assertFalse(SquadAssignment.objects.filter(person=self.xaver, squad=self.jugi).exists())

    def test_person_only_in_own_club(self):
        data = {"last_name": "Neu", "first_name": "Ida", "email": "ida@example.ch", "is_active": "on",
                "club": self.other_club.pk}
        self.client.post(reverse("admin:training_person_add"), data)
        self.assertFalse(Person.objects.filter(email="ida@example.ch").exists())
        self.client.post(reverse("admin:training_person_add"), {**data, "club": self.club.pk})
        self.assertTrue(Person.objects.filter(email="ida@example.ch", club=self.club).exists())

    def test_can_appoint_club_admin(self):
        data = {"last_name": "Test", "first_name": "beat", "email": "beat@example.ch", "is_active": "on",
                "is_club_admin": "on", "club": self.club.pk}
        self.client.post(reverse("admin:training_person_change", args=[self.beat.pk]), data)
        self.beat.refresh_from_db()
        self.assertTrue(self.beat.is_club_admin)

    def test_attendances_like_admin_in_own_club(self):
        user = self.user()
        self.assertTrue(can_edit_attendance(user, self.beat, self.jugi, today() - timedelta(days=50)))
        self.assertFalse(can_edit_attendance(user, self.xaver, self.foreign_squad, today()))
        a_beat = self.attendance(self.beat, self.jugi)
        self.attendance(self.xaver, self.foreign_squad)
        self.assertEqual(set(visible_attendances(user)), {a_beat})
        self.assertContains(self.client.get(reverse("squad_day", args=[self.apparatus.pk])), "carla Test")
