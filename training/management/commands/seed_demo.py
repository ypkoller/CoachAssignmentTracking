from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import User
from training.models import (
    Attendance,
    Club,
    Person,
    Role,
    Squad,
    SquadAssignment,
    SquadLeadership,
    today,
)

PASSWORD = "demo1234!"


class Command(BaseCommand):
    help = "Creates demo data (club, squads, persons, assignments, attendances, logins)."

    @transaction.atomic
    def handle(self, *args, **options):
        if Club.objects.filter(name="STV Demo").exists():
            self.stdout.write("Demo data already exists.")
            return

        club = Club.objects.create(name="STV Demo")
        jugi = Squad.objects.create(name="Jugi", club=club)
        apparatus = Squad.objects.create(name="Geräteturnen", club=club)
        parent_child = Squad.objects.create(name="MUKI-Turnen", club=club)

        def person(first_name, last_name, birth_year, club=club, **extra):
            email = f"{first_name}.{last_name}@example.ch".lower()
            user = User.objects.filter(email=email).first() or User.objects.create_user(
                email=email, password=PASSWORD
            )
            return Person.objects.create(
                first_name=first_name,
                last_name=last_name,
                email=email,
                birth_year=birth_year,
                club=club,
                user=user,
                **extra,
            )

        anna = person("Anna", "Muster", 1985)
        beat = person("Beat", "Keller", 1992)
        carla = person("Carla", "Meier", 2001, is_club_admin=True)
        dario = person("Dario", "Frei", 2005)

        # Second club: Beat is a member of both (one login, club chosen at login).
        other_club = Club.objects.create(name="TV Beispiel")
        volleyball = Squad.objects.create(name="Volleyball", club=other_club)
        beat_other = person("Beat", "Keller", 1992, club=other_club)
        eva = person("Eva", "Brunner", 1990, club=other_club, is_club_admin=True)

        start = today() - timedelta(days=90)
        SquadLeadership.objects.create(person=anna, squad=jugi, valid_from=start)
        for p, squad, role in [
            (anna, jugi, Role.HEAD_LEADER),
            (beat, jugi, Role.ASSISTANT_LEADER),
            (carla, jugi, Role.ASSISTANT_LEADER),
            (beat, apparatus, Role.HEAD_LEADER),
            (dario, apparatus, Role.ASSISTANT_LEADER),
            (carla, parent_child, Role.HEAD_LEADER),
        ]:
            SquadAssignment.objects.create(person=p, squad=squad, role=role, valid_from=start)
        SquadLeadership.objects.create(person=eva, squad=volleyball, valid_from=start)
        SquadAssignment.objects.create(
            person=beat_other, squad=volleyball, role=Role.HEAD_LEADER, valid_from=start
        )

        for days in (2, 4, 9, 11, 16):
            day = today() - timedelta(days=days)
            for p, squad in [(anna, jugi), (beat, jugi), (beat, apparatus), (dario, apparatus)]:
                attendance = Attendance(person=p, squad=squad, date=day)
                attendance.full_clean()
                attendance.save()

        if not User.objects.filter(email="admin@example.ch").exists():
            User.objects.create_superuser(email="admin@example.ch", password=PASSWORD)

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo data created. Logins (password for all: {PASSWORD}): "
                "admin@example.ch (main administrator), carla.meier@example.ch (club "
                "administrator STV Demo), eva.brunner@example.ch (club administrator TV Beispiel), "
                "anna.muster@example.ch (squad leader Jugi), beat.keller@example.ch (both clubs), "
                "dario.frei@example.ch"
            )
        )
