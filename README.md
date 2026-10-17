# Trainingserfassung

Mobile-taugliche Browser-App (PWA) zur Erfassung von Leitereinsätzen pro Riege, mit Auswertung und Export der Anzahl Einsätze.

## Tech-Stack

| Bereich | Technologie | Zweck |
|---|---|---|
| Sprache | **Python 3.14** (`python:3.14-slim`) | |
| Paketverwaltung | **Poetry 2.x** + `pyproject.toml` | Abhängigkeiten, Lockfile (`poetry.lock`), virtuelle Umgebung |
| Framework | **Django 6.x** | Backend, ORM, Admin, Auth, Templates |
| Frontend | Django-Templates + **HTMX** | Dynamische Interaktionen ohne Neuladen, kein separates JS-Frontend |
| Styling | **Tailwind CSS** | Mobile-first Layout |
| PWA | Web App Manifest + Service Worker | Icon auf dem Home-Bildschirm, Vollbild |
| Datenbank | **PostgreSQL 17** (`postgres:17-alpine`) | Inkl. Partial Unique Index und Exclusion Constraints (`btree_gist`) für Geschäftsregeln |
| App-Server | **Gunicorn** | Produktiver WSGI-Server im Container |
| Statische Dateien | **WhiteNoise** | Auslieferung von CSS/JS direkt aus Django |
| Export | `openpyxl` / CSV | Excel-Export der Anzahl Einsätze |
| Passwort-Hashing | Argon2 (`argon2-cffi`) | Alternativ Django-Standard PBKDF2 |
| Rate-Limiting | `django-axes` / `django-ratelimit` | Schutz von Login und Passwort-Reset |
| Deployment | **Docker Compose → Coolify** | Coolify übernimmt HTTPS, Domain und DB-Backups |

## Authentifizierung

- E-Mail/Passwort-Login mit **Django-Sessions** (HttpOnly- und Secure-Cookie, serverseitig in Postgres gespeichert)
- Lange Sessions (z. B. 1 Jahr, verlängert bei Aktivität)
- Logout beendet das aktuelle Gerät. Eine Passwortänderung beendet alle anderen Sessions. Deaktivierte Personen verlieren den Zugriff sofort.
- **Registrierung nur per Einladungslink:** Der Administrator erstellt einen Einmal-Token, die Person registriert sich selbst und wird mit ihrer Person verknüpft.
- **«Passwort vergessen?»:** Einmal-Link mit 1 h Gültigkeit über den eigenen SMTP-Server. Die Antwort ist generisch (keine Account-Enumeration) und rate-limited.

## Rollen und Berechtigungen

Eine Person kann mehrere Rollen gleichzeitig haben. Ein Riegenleiter kann z. B. in anderen Riegen, die er nicht leitet, als Hauptleiter oder Hilfsleiter eingeteilt sein.

| Rolle | Wie entsteht sie? | Rechte |
|---|---|---|
| **Administrator** | Flag am Login-Account, **global** über alle Vereine | Hat immer alle Rechte. Pflegt Vereine, Riegen, Personen und Riegenleitungen. Erstellt Einladungslinks. |
| **Riegenleiter** | Gültige `Riegenleitung` (Person ↔ Riege, 1..n Riegen) | Für **seine** Riegen: Hauptleiter und Hilfsleiter zuteilen oder entfernen (durch Setzen von «gültig bis»), alle Einsätze ansehen, Einsätze für die zugeteilten Leiter erfassen, ändern oder löschen (**bis 30 Tage in die Vergangenheit**) |
| **Leiter** (Hauptleiter oder Hilfsleiter) | Gültige `Riegenzuteilung` am Einsatztag | **Eigene** Einsätze erfassen, aber nur für Riegen und Tage, an denen er zugeteilt ist. Eigene Einsätze ansehen. Eigene Einsätze **bis 30 Tage in die Vergangenheit** erfassen, ändern oder löschen. |

Berechtigungen werden objektbezogen geprüft, also pro Riege und Person, nicht nur pro Rolle. Die Prüfung erfolgt serverseitig in jeder View. Ein Leiter sieht im UI nur die Riegen, für die er zum jeweiligen Datum zugeteilt ist.

## Fachliche Anforderungen

- Leiter erfassen ihre Einsätze fortlaufend, mit Login und nur für die eigenen Riegen.
- Die Erfassung muss schnell gehen: Das Datum ist frei wählbar (Vorschlag: heute, keine Daten in der Zukunft, höchstens 30 Tage zurück), es gibt keine festen Trainingstage und keine Terminvorlagen.
- **Pro Riege, Person und Tag gibt es genau einen Eintrag.**
- Eine Person kann in mehreren Riegen leiten.
- Eine Person hat pro Riege zu einem Zeitpunkt genau eine Funktion: **Hauptleiter** oder **Hilfsleiter**.
- **Pro Riege und Datum höchstens ein Hauptleiter.**
- Es werden **keine Vergütungen** berechnet. Ausgewertet wird die **Anzahl Einsätze**.
- Export pro Zeitraum: Anzahl Einsätze pro Person, Riege und Funktion.

## Datenmodell

### Entitäten

```
Verein ──< Riege
   │         │
   │         ├──< Riegenleitung >──── Person   (Rolle Riegenleiter, gültig ab/bis)
   │         │
   │         ├──< Riegenzuteilung >── Person   (Hauptleiter | Hilfsleiter, gültig ab/bis)
   │         │
   │         └──< Einsatz >────────── Person   (Datum)
   │
   └──< Person
```

| Entität | Attribute |
|---|---|
| **Verein** | Name |
| **Riege** | Name, Verein (FK) |
| **Person** | Name, Vorname, E-Mail (Pflicht, eindeutig), Jahrgang, Aktiv (ja/nein), Verein (FK) |
| **Riegenleitung** | Person (FK), Riege (FK), gültig ab, gültig bis (leer = offen) |
| **Riegenzuteilung** | Person (FK), Riege (FK), Funktion (`HAUPTLEITER` / `HILFSLEITER`), gültig ab, gültig bis (leer = offen) |
| **Einsatz** | Person (FK), Riege (FK), Datum, Funktion (wird beim Speichern aus der gültigen Zuteilung übernommen) |

Personenbezogen werden **nur** Name, Vorname, E-Mail, Jahrgang und Aktiv gespeichert.

### Regeln und ihre Durchsetzung

| # | Regel | Umsetzung |
|---|---|---|
| R1 | Eine Riege gehört genau zu einem Verein. | `NOT NULL` FK |
| R2 | Eine Person gehört genau zu einem Verein. | `NOT NULL` FK |
| R3 | Die E-Mail ist Pflicht und eindeutig, weil sie als Login dient. | `NOT NULL` und `UNIQUE` (case-insensitive) |
| R4 | Eine Person hat 0..n Riegenzuteilungen, auch zu mehreren Riegen. | 1:n-Beziehung |
| R5 | Pro Person und Riege höchstens eine gültige Zuteilung zu einem Zeitpunkt (keine überlappenden Zeiträume). | **Exclusion Constraint**: `EXCLUDE USING gist (person WITH =, riege WITH =, daterange(gueltig_ab, gueltig_bis, '[]') WITH &&)` |
| R6 | Pro Person und Riege höchstens eine gültige Riegenleitung zu einem Zeitpunkt. | Exclusion Constraint wie R5 |
| R7 | `gültig bis` ≥ `gültig ab` (Zuteilung und Riegenleitung) | `CheckConstraint` |
| R8 | Person und Riege gehören zum selben Verein (Zuteilung, Riegenleitung, Einsatz). | Validierung im Model (`clean()`) und zusätzlich DB-Trigger |
| R9 | Ein Einsatz ist nur möglich, wenn die Person am Datum der Riege zugeteilt ist. | Validierung im Model (`clean()`) und zusätzlich DB-Trigger. Die Funktion wird dabei aus der Zuteilung übernommen. |
| R10 | Pro Person, Riege und Datum höchstens ein Einsatz. | `UniqueConstraint(person, riege, datum)` |
| R11 | Pro Riege und Datum höchstens ein Hauptleiter. | **Partial Unique Index** `(riege, datum) WHERE funktion = 'HAUPTLEITER'` |
| R12 | Leiter und Riegenleiter dürfen Einsätze nur bis 30 Tage in die Vergangenheit erfassen, ändern oder löschen. | Berechtigungsprüfung in der View (`datum >= heute − 30 Tage`). Administratoren sind davon ausgenommen. |
| R13 | Einsätze in der Zukunft sind nicht erlaubt (gilt für alle, auch Administratoren). | Validierung im Model (`datum <= heute`, Zeitzone Europe/Zurich). Im Formular ist `max` auf heute gesetzt. |

R8 und R9 betreffen mehrere Tabellen und lassen sich nicht als einfache Constraint ausdrücken. Sie werden deshalb in Django validiert und über Trigger zusätzlich in der DB abgesichert.

### Technische Ergänzungen

- `User` (Login-Account, Django-Auth): Passwort-Hash und Login-Daten, 1:1 mit einer `Person` verknüpft, verwendet deren E-Mail als Benutzernamen. Wird eine Person auf «inaktiv» gesetzt, ist auch ihr Login gesperrt, und alle Sessions werden beendet.
- `Einladung`: Token (gehasht), Ablaufdatum, benutzt am, verknüpfte Person

## Architektur

```
Browser/Handy → Coolify (Traefik, HTTPS) → Gunicorn → Django → PostgreSQL
```

Ein App-Container und ein Postgres-Container, definiert in `docker-compose.yml`.

## Entwicklung

```bash
poetry install                     # Abhängigkeiten inkl. Dev-Tools installieren
poetry run python manage.py migrate
poetry run python manage.py runserver
```

Im Docker-Image werden nur die Produktionsabhängigkeiten installiert (`poetry install --only main --no-root`), und zwar in einem Multi-Stage-Build, damit Poetry selbst nicht im finalen Image landet.

## Konfiguration (Umgebungsvariablen)

| Variable | Beschreibung |
|---|---|
| `DJANGO_SECRET_KEY` | Geheimer Schlüssel |
| `DJANGO_ALLOWED_HOSTS` | Domain(s) |
| `DATABASE_URL` | z. B. `postgres://user:pass@db:5432/training` |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` | SMTP für den Passwort-Reset |
| `DEFAULT_FROM_EMAIL` | Absenderadresse |

## Nicht im Scope (vorerst)

- Vergütungsberechnung (es wird nur die Anzahl Einsätze ausgewertet)
- Feste Trainingstage und Terminvorlagen
- Administratoren pro Verein (vorerst nur global)
- Offline-Erfassung
- Native Apps / JWT-API (bei Bedarf später via `djangorestframework-simplejwt` nachrüstbar)
