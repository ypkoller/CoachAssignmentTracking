# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workflow Orchestration

### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop
- After ANY correction from the user: update tasks/lessons.md with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes — don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests — then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how


## Task Management

1. Plan First: Write plan to `tasks/todo.md` with checkable items
2. Verify Plan: Check in before starting implementation
3. Track Progress: Mark items complete as you go
4. Explain Changes: High-level summary at each step
5. Document Results: Add review section to `tasks/todo.md`
6. Capture Lessons: Update `tasks/lessons.md` after corrections


## Core Principles

- **Simplicity First:** Make every change as simple as possible. Impact minimal code.
- **No Laziness:** Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact:** Only touch what's necessary. No side effects with new bugs.

## Project: Trainingserfassung

Django 6 app (Python 3.14, Postgres 17, HTMX, Tailwind built locally). See README.md for the domain,
roles and business rules R1–R13.

### Commands

```bash
docker compose up -d --build                         # app + Postgres on http://localhost:8000
docker compose exec web python manage.py seed_demo   # demo data, password demo1234!
docker compose run --rm web python manage.py test    # tests need Postgres (constraints, triggers)
DJANGO_SECRET_KEY=mypy .venv/Scripts/mypy .          # type check (django-stubs loads the settings)
.venv/Scripts/ruff check .                           # lint (RUF012 on Django Meta/admin lists is known noise)
```

- The Docker image contains only production dependencies; mypy/ruff run from the local `.venv`
  (`poetry install`). Poetry is not installed globally on this machine.
- New migrations: generate them in the container with the code mounted, e.g.
  `docker compose run --rm --no-deps --entrypoint "" -v "<repo>:/src" -w /src -e DJANGO_SECRET_KEY=x web python manage.py makemigrations`
  (mounting onto `/app` would hide the image's `.venv`).

### Conventions

- **Code is English** (identifiers, comments, docstrings, URL paths, DB schema).
  **Everything the user sees is German** (verbose names, labels, messages, template text, export headers).
  Glossary: Verein=`Club`, Riege=`Squad`, Riegenleitung=`SquadLeadership`, Riegenzuteilung=`SquadAssignment`,
  Einsatz=`Attendance`, Funktion=`Role` (`HEAD_LEADER`/`ASSISTANT_LEADER`), Einladung=`Invitation`.
- Every model inherits `accounts.audit.AuditedModel` (`created_at/by`, `updated_at/by`). The acting user
  comes from `CurrentUserMiddleware` (contextvar); outside requests it is `None`. Do not set these fields
  by hand. `QuerySet.update()`/`bulk_create()` bypass `save()` and therefore the audit fields; avoid them.
  Admin classes use `AuditedAdmin` / `AuditedAdminMixin`.
- The admin creates logins and invitations through `accounts/invitations.py` (`invite`, `send_invitation`);
  a login without a usable password counts as invited but not registered.
- Permissions are object-level and live in `training/permissions.py`; every view checks through them.
- Clubs: a `User` has one `Person` per club (`Person.user`). The club chosen at login is in the session;
  `accounts.clubs.ClubMiddleware` sets `request.user.person` (person in that club) and `club_persons`.
  Permissions always use `user.person`, never `user.persons`. `user.is_admin` = main administrator
  (`is_superuser`), `user.is_club_admin` = club administrator in the chosen club, `user.is_staff` = either.
- Admin classes for club data inherit `training.admin_scope.ClubScopedAdmin` (set `club_lookup`) or
  `ClubScopedInline`; they filter querysets, foreign key choices and list filters to the club.
  `UserAdmin` and `ClubAdmin` are main-administrator only (Django permissions; club admins have none).
- Dates are local (`training.models.today()`, Europe/Zurich).
- Frontend assets are local: Tailwind is built in the Docker `assets` stage from `frontend/`
  (`static/css/` is generated, not committed); HTMX and Roboto live in `static/`. The Tailwind CLI is
  pinned by version and sha256 in the Dockerfile; update both together. No CDNs.
- Client IP for axes and ratelimit comes from `config.client_ip.client_ip` (`DJANGO_PROXY_COUNT`;
  production behind Coolify/Traefik = 1). Never read `REMOTE_ADDR` or `X-Forwarded-For` directly.
- `/health/` is answered by `config.health.HealthCheckMiddleware` (first middleware, before the host
  check); used by the Docker `HEALTHCHECK` and Coolify.
- Deployment: Coolify v4, Dockerfile build pack, separate Coolify Postgres; see README "Deployment".

### How the business rules are enforced

| Rule | Enforcement |
|---|---|
| R1, R2 | `NOT NULL` FK |
| R3 | `UniqueConstraint(Lower("email"))` on `User`, `(Lower("email"), club)` on `Person`; `Person.clean()` keeps the email equal to the login's; login looks up `email__iexact` |
| R5, R6 | `ExclusionConstraint` (`btree_gist`): person =, squad =, `daterange(valid_from, valid_until, '[]')` && |
| R7 | `CheckConstraint` |
| R8 | `SameClubMixin.clean()` + DB trigger `training_check_same_club` |
| R9 | `Attendance.clean()` + DB trigger `training_attendance_assignment` (also sets `role`) |
| R10 | `UniqueConstraint(person, squad, date)` |
| R11 | partial unique index `(squad, date) WHERE role = 'HEAD_LEADER'` |
| R12 | `permissions.date_allowed()` in the views (admins exempt) |
| R13 | `Attendance.clean()`; date inputs have `max` = today |

- Triggers live in `training/migrations/0002_triggers.py` (raw SQL); keep them in sync with table/column names.
- `SquadAssignment.clean()` additionally prevents shortening an assignment so that recorded attendances
  would fall outside it (R9 after the fact).
- A role change of an assignment does not change already recorded attendances.
