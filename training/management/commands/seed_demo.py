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

        def person(first_name, last_name, birth_year):
            p = Person.objects.create(
                first_name=first_name,
                last_name=last_name,
                email=f"{first_name}.{last_name}@example.ch".lower(),
                birth_year=birth_year,
                club=club,
            )
            User.objects.create_user(email=p.email, password=PASSWORD, person=p)
            return p

        anna = person("Anna", "Muster", 1985)
        beat = person("Beat", "Keller", 1992)
        carla = person("Carla", "Meier", 2001)
        dario = person("Dario", "Frei", 2005)

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
                "admin@example.ch (administrator), anna.muster@example.ch "
                "(squad leader Jugi), beat.keller@example.ch, carla.meier@example.ch, "
                "dario.frei@example.ch"
            )
        )
