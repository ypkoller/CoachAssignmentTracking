# Trainingserfassung

Mobile-friendly browser app (PWA) for recording leader attendances per squad ("Riege"), with
reports and an export of the number of attendances. The user interface is in German.

## Tech stack

| Area | Technology | Purpose |
|---|---|---|
| Language | **Python 3.14** (`python:3.14-slim`) | |
| Package management | **Poetry 2.x** + `pyproject.toml` | Dependencies, lockfile (`poetry.lock`), virtual environment |
| Framework | **Django 6.x** | Backend, ORM, admin, auth, templates |
| Frontend | Django templates + **HTMX** | Dynamic interactions without page reloads, no separate JS frontend |
| Styling | **Tailwind CSS** (standalone CLI, built in the Docker image) | Mobile-first layout; HTMX and the Roboto font are served locally, no CDNs |
| PWA | Web app manifest + service worker | Home screen icon, full screen |
| Database | **PostgreSQL 17** (`postgres:17-alpine`) | Incl. partial unique index and exclusion constraints (`btree_gist`) for business rules |
| App server | **Gunicorn** | Production WSGI server in the container |
| Static files | **WhiteNoise** | Serves CSS/JS directly from Django |
| Export | `openpyxl` / CSV | Excel export of the number of attendances |
| Password hashing | Argon2 (`argon2-cffi`) | Django's PBKDF2 as fallback |
| Rate limiting | `django-axes` / `django-ratelimit` | Protects login and password reset |
| Type checking | **mypy** + `django-stubs` | Static checks of the code |
| Deployment | **Docker Compose → Coolify** | Coolify handles HTTPS, domain and DB backups |

## Authentication

- Email/password login with **Django sessions** (HttpOnly and Secure cookie, stored server-side in Postgres)
- Long sessions (1 year, extended on activity)
- Logout ends the current device. A password change ends all other sessions. Deactivated persons lose access immediately.
- **Registration only via invitation link:** the administrator creates a one-time token, the person registers themselves and is linked to their person record.
- **"Forgot password?":** one-time link valid for 1 h via the club's own SMTP server. The response is generic (no account enumeration) and rate-limited.

## Roles and permissions

A person can have several roles at the same time. A squad leader can, for example, be assigned as head or assistant leader in other squads they do not lead.

| Role | How is it granted? | Permissions |
|---|---|---|
| **Administrator** | Flag on the login account, **global** across all clubs | Always has all permissions. Maintains clubs, squads, persons and squad leaderships. Creates invitation links. |
| **Squad leader** (Riegenleiter) | Valid `SquadLeadership` (person ↔ squad, 1..n squads) | For **their** squads: assign or remove head and assistant leaders (by setting "valid until"), view all attendances, record, change or delete attendances for the assigned leaders (**up to 30 days back**) |
| **Leader** (head or assistant leader) | Valid `SquadAssignment` on the day | Record **their own** attendances, only for squads and days they are assigned to. View their own attendances. Record, change or delete their own attendances **up to 30 days back**. |

Permissions are checked per object, i.e. per squad and person, not just per role, and always on the server in every view. A leader only sees the squads they are assigned to on the selected date.

## Business requirements

- Leaders record their attendances continuously, logged in and only for their own squads.
- Recording must be quick: the date can be chosen freely (default: today, no dates in the future, at most 30 days back); there are no fixed training days and no schedule templates.
- **There is exactly one entry per squad, person and day.**
- A person can lead in several squads.
- At any point in time, a person has exactly one role per squad: **head leader** (Hauptleiter) or **assistant leader** (Hilfsleiter).
- **At most one head leader per squad and date.**
- **No compensation** is calculated. What is reported is the **number of attendances**.
- Export per period: number of attendances per person, squad and role.

## Data model

### Entities

```
Club ──< Squad
  │        │
  │        ├──< SquadLeadership >── Person   (squad leader role, valid from/until)
  │        │
  │        ├──< SquadAssignment >── Person   (head | assistant leader, valid from/until)
  │        │
  │        └──< Attendance >─────── Person   (date)
  │
  └──< Person
```

| Entity (German UI term) | Attributes |
|---|---|
| **Club** (Verein) | name |
| **Squad** (Riege) | name, club (FK) |
| **Person** | last name, first name, email (required, unique), birth year, active (yes/no), club (FK) |
| **SquadLeadership** (Riegenleitung) | person (FK), squad (FK), valid from, valid until (empty = open) |
| **SquadAssignment** (Riegenzuteilung) | person (FK), squad (FK), role (`HEAD_LEADER` / `ASSISTANT_LEADER`), valid from, valid until (empty = open) |
| **Attendance** (Einsatz) | person (FK), squad (FK), date, role (taken from the valid assignment on save) |
| **User** (Benutzer) | login account: email as username, password hash, 1:1 with a person. Deactivating the person also locks the login and ends all sessions. |
| **Invitation** (Einladung) | token (hashed), expiry, used at, linked person |

Every table also records **when and by whom** a row was created and last changed
(`created_at`, `created_by`, `updated_at`, `updated_by`). On creation, the "changed" values equal
the "created" values.

Of personal data, **only** last name, first name, email, birth year and active are stored.

### Business rules

| # | Rule |
|---|---|
| R1 | A squad belongs to exactly one club. |
| R2 | A person belongs to exactly one club. |
| R3 | The email is required and unique (case-insensitive), because it is the login. |
| R4 | A person has 0..n squad assignments, also to several squads. |
| R5 | Per person and squad at most one valid assignment at a time (no overlapping periods). |
| R6 | Per person and squad at most one valid squad leadership at a time. |
| R7 | "valid until" ≥ "valid from" (assignment and squad leadership). |
| R8 | Person and squad belong to the same club (assignment, squad leadership, attendance). |
| R9 | An attendance is only possible if the person is assigned to the squad on that date. The role is taken from the assignment. |
| R10 | Per person, squad and date at most one attendance. |
| R11 | Per squad and date at most one head leader. |
| R12 | Leaders and squad leaders may record, change or delete attendances only up to 30 days back. Administrators are exempt. |
| R13 | Attendances in the future are not allowed (for everyone, including administrators; time zone Europe/Zurich). |

## Architecture

```
Browser/phone → Coolify (Traefik, HTTPS) → Gunicorn → Django → PostgreSQL
```

One app container and one Postgres container, defined in `docker-compose.yml`.

## Development

### Locally with Docker (recommended)

```bash
docker compose up -d --build                         # start app + Postgres (http://localhost:8000)
docker compose exec web python manage.py seed_demo   # create demo data and logins
docker compose run --rm web python manage.py test    # run the tests against Postgres
docker compose exec web python manage.py createsuperuser
docker compose down                                  # stop (data is kept; add -v to delete it)
```

Demo logins (password `demo1234!`): `admin@example.ch` (administrator), `anna.muster@example.ch`
(squad leader Jugi), `beat.keller@example.ch`, `carla.meier@example.ch`, `dario.frei@example.ch`.

Without `EMAIL_HOST`, mails (password reset) are written to the container log (`docker compose logs web`).
The administrator invites persons in the admin, in one of three ways:

- When creating or editing a person: check *Login anlegen und Einladung senden*, optionally with a start
  password (then the person can log in right away).
- In the person list: select persons and run the action *Login anlegen und Einladung senden*. Inactive
  and already registered persons are skipped; persons who have not registered yet get a new link.
- Under *Admin → Einladungen*.

The link is mailed to the person and shown to the administrator only once.

### Locally without Docker

```bash
poetry install                     # install dependencies incl. dev tools
poetry run python manage.py migrate
poetry run python manage.py runserver
```

The CSS is built in the Docker image. Without Docker, build it once (or with `--watch`) using the
[Tailwind standalone CLI](https://github.com/tailwindlabs/tailwindcss/releases/tag/v3.4.16) v3.4.16:

```bash
tailwindcss -c frontend/tailwind.config.js -i frontend/app.css -o static/css/app.css --watch
```

### Type checking with mypy

```bash
DJANGO_SECRET_KEY=mypy poetry run mypy .          # bash
$env:DJANGO_SECRET_KEY="mypy"; poetry run mypy .  # PowerShell
```

## Configuration (environment variables)

| Variable | Description |
|---|---|
| `DJANGO_SECRET_KEY` | Secret key |
| `DJANGO_DEBUG` | `true` for development (default `false`) |
| `DJANGO_ALLOWED_HOSTS` | Domain(s) |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Origins for CSRF, e.g. `https://training.example.ch` |
| `DJANGO_SECURE_COOKIES` | `false` only locally without HTTPS (default: on unless `DJANGO_DEBUG`) |
| `DJANGO_PROXY_COUNT` | Number of trusted reverse proxies; `1` behind Coolify (default `0`: `X-Forwarded-For` is ignored) |
| `DJANGO_HSTS_SECONDS` | HSTS duration, e.g. `31536000` once HTTPS works (default `0` = off) |
| `DATABASE_URL` | e.g. `postgres://user:pass@db:5432/training` |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | SMTP for the password reset |
| `EMAIL_USE_TLS` / `EMAIL_USE_SSL` | STARTTLS (usually port 587, default) or SSL (usually port 465); set only one to `true` |
| `DEFAULT_FROM_EMAIL` | Sender address |
| `WEB_CONCURRENCY` | Number of Gunicorn workers (default `3`) |

## Deployment (Coolify v4)

The app is deployed with the **Dockerfile** build pack; PostgreSQL runs as a separate Coolify resource
with scheduled backups. `docker-compose.yml` is only used for local development.

**Prerequisites**

1. Point the domain to the server: in the DuckDNS dashboard set the server's public IP for
   `training-svfislisbach`. Ports 80 and 443 must be reachable (Let's Encrypt).
2. In Coolify, connect GitHub under *Sources → GitHub App* and grant access to the (private) repository.

**Database**

3. *Project → Environment → New Resource → Database → PostgreSQL*, image `postgres:17-alpine`.
   Do not make it publicly accessible. Start it and copy the **Postgres URL (internal)**.
4. Tab *Backups*: add a scheduled backup, frequency `0 3 * * *` (daily at 03:00), keep e.g. 14 backups.
   Run *Backup Now* once to check it works.

**App**

5. *New Resource → Private Repository (with GitHub App)*: this repository, branch `master`,
   build pack **Dockerfile** (the default is Nixpacks; check it under *General*), *Ports Exposes* `8000`, domain `https://training-svfislisbach.duckdns.org`.
   Do not map any ports to the host.
6. *Environment Variables* (runtime only, no build variables needed):

   | Variable | Value |
   |---|---|
   | `DJANGO_SECRET_KEY` | random, e.g. `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
   | `DJANGO_ALLOWED_HOSTS` | `training-svfislisbach.duckdns.org` |
   | `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://training-svfislisbach.duckdns.org` |
   | `DJANGO_PROXY_COUNT` | `1` |
   | `DATABASE_URL` | the internal Postgres URL from step 3 |
   | `DEFAULT_FROM_EMAIL`, `EMAIL_*` | once the SMTP account is known (until then mails go to the log) |

7. *Healthcheck*: enable, path `/health` (with or without trailing slash), port `8000` (the image contains `curl`; the Dockerfile also
   defines a `HEALTHCHECK`). `/health/` also checks the database connection.
8. *Advanced*: enable **Auto Deploy**, so that every push to `master` deploys.
9. *Deploy*. On start, the container runs the migrations and creates the cache table.
10. Create the first administrator in *Terminal* of the app: `python manage.py createsuperuser`.
    The Coolify terminal needs ports 6001/6002 to be reachable; alternatively via SSH on the server:
    `docker exec -it $(docker ps -qf name=<app-uuid>) python manage.py createsuperuser`.
11. Check login and recording on the domain. Once HTTPS works reliably, set `DJANGO_HSTS_SECONDS=31536000`
    and redeploy.

## Out of scope (for now)

- Compensation calculation (only the number of attendances is reported)
- Fixed training days and schedule templates
- Administrators per club (global only for now)
- Offline recording
- Native apps / JWT API (can be added later via `djangorestframework-simplejwt`)
