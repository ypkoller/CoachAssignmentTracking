# Erste Version (v0.1) – lauffähig im lokalen Docker-Container

## Plan

- [x] Projektgerüst: `pyproject.toml` (Poetry, package-mode = false), `poetry.lock` im Container erzeugt
- [x] Django-Projekt `config` (Settings via Umgebungsvariablen, Europe/Zurich, de-ch, Argon2, Sessions 1 Jahr, WhiteNoise, axes)
- [x] App `accounts`: Custom `User` (E-Mail als Login, case-insensitive eindeutig), `Einladung` (Token gehasht), Login/Logout, Passwort vergessen (rate-limited), Passwort ändern, Registrierung per Einladungslink
- [x] App `einsaetze`: Modelle Verein, Riege, Person, Riegenleitung, Riegenzuteilung, Einsatz
  - [x] Constraints R1–R11 (inkl. `btree_gist`, Exclusion Constraints, Partial Unique Index)
  - [x] DB-Trigger für R8/R9 (Funktion wird aus Zuteilung übernommen)
  - [x] `clean()`-Validierung R8, R9, R13
- [x] Berechtigungen objektbezogen (`permissions.py`), R12 (30 Tage) in den Views
- [x] Views (HTMX + Tailwind, mobile-first, Farben von svfislisbach.ch):
  - [x] Erfassen: Datum wählen → eigene Riegen am Datum, Einsatz per Tipp an/aus
  - [x] Riege (Riegenleiter): alle zugeteilten Leiter am Datum an/aus, Zuteilungen verwalten (hinzufügen / beenden)
  - [x] Auswertung mit Zeitraumfilter
  - [x] Export (CSV / Excel): Anzahl Einsätze pro Person, Riege, Funktion
- [x] Django-Admin für alle Modelle, Einladungslink erstellen
- [x] PWA: Manifest, Service Worker, Icons (SVG + PNG 192/512)
- [x] Docker: Multi-Stage-`Dockerfile`, `docker-compose.yml` (app + postgres:17-alpine), Entrypoint (migrate, Cache-Tabelle, gunicorn)
- [x] Demo-Daten: `manage.py seed_demo`
- [x] Tests (Constraints, Trigger, Berechtigungen, Views): 32 Tests grün
- [x] Verifikation: `docker compose up`, Login, Erfassen, Riegenansicht, Export, PWA-Endpunkte per HTTP geprüft

## Review

- Farbschema aus dem CSS von svfislisbach.ch: `#33708C` (Hauptfarbe), `#125B76` (Header), `#1F9AC6` (Akzent),
  `#B4E3F3` / `#E7F5FA` (hell), Text `#333333`, Schrift Roboto.
- Zusatzregel: Eine Zuteilung kann nicht so verkürzt werden, dass erfasste Einsätze ausserhalb liegen
  (sonst wäre R9 nachträglich verletzt).

## Offen / nächste Schritte

- Tailwind und HTMX kommen noch per CDN → Tailwind-Build ins Docker-Image, HTMX lokal ausliefern
- Funktionswechsel einer Zuteilung ändert bereits erfasste Einsätze nicht (Funktion zum Erfassungszeitpunkt bleibt)
- Ansicht im Browser auf dem Handy prüfen (bisher nur per HTTP getestet)
- Coolify-Deployment (HTTPS, `DJANGO_SECURE_COOKIES` weglassen → Secure-Cookies aktiv)

# mypy als Prüfwerkzeug

- [x] `mypy` + `django-stubs[compatible-mypy]` als Dev-Abhängigkeit, Konfiguration in `pyproject.toml`
  (`check_untyped_defs`, Django-Plugin, Migrationen ausgenommen)
- [x] Gefundene Typfehler behoben: `UserManager` generisch, `GleicherVereinMixin` typisiert,
  `ZuteilungForm` (ModelChoiceField), `RegistrierungForm.clean`, `parse_datum` (Default `None`), Test-Attribute
- [x] `mypy .` → keine Fehler, `manage.py check` → keine Fehler
- [x] Testsuite in Docker: 32 Tests grün
- [ ] Optional: schrittweise auf `strict = true` umstellen (aktuell 274 Meldungen, v. a. fehlende Annotationen)

# Aufräumarbeiten: Englisch + Audit-Felder

Entscheide: alles inkl. Datenmodell übersetzen · Audit-FK auf `accounts.User` · Entwickler-Details aus README nach CLAUDE.md verschieben.
**UI-Texte (Labels, Meldungen, Templates-Text) bleiben deutsch**, nur Code, Bezeichner, Kommentare und DB-Schema werden englisch.

## Glossar (bitte prüfen)

| Deutsch | Englisch |
|---|---|
| App `einsaetze` | App `training` (Tabellen `training_*`) |
| Verein | `Club` |
| Riege | `Squad` |
| Person (name, vorname, jahrgang, aktiv, verein) | `Person` (`last_name`, `first_name`, `birth_year`, `is_active`, `club`) |
| Riegenleitung / Riegenleiter | `SquadLeadership` / squad leader |
| Riegenzuteilung | `SquadAssignment` |
| Funktion (HAUPTLEITER / HILFSLEITER) | `Role` (`HEAD_LEADER` / `ASSISTANT_LEADER`), Anzeige bleibt «Hauptleiter»/«Hilfsleiter» |
| Einsatz (datum, funktion) | `Attendance` (`date`, `role`) |
| gueltig_ab / gueltig_bis | `valid_from` / `valid_until` |
| Einladung (gueltig_bis, benutzt_am) | `Invitation` (`expires_at`, `used_at`) |
| heute(), fruehestes_datum(), gueltig_am() | `today()`, `earliest_date()`, `valid_on()` |
| darf_einsatz_bearbeiten, darf_riege_leiten, geleitete_riegen, sichtbare_einsaetze, datum_erlaubt, person_von | `can_edit_attendance`, `can_lead_squad`, `led_squads`, `visible_attendances`, `date_allowed`, `person_of` |
| Views erfassen, riege_tag, einsatz_umschalten, zuteilungen, einsaetze_liste, registrieren | `record`, `squad_day`, `toggle_attendance`, `assignments`, `attendance_list`, `register` |
| URL-Pfade `/erfassen/`, `/riege/…`, `/passwort-vergessen/` … | `/record/`, `/squad/…`, `/password-reset/` … (URL-Namen ebenso) |

## Schritte

- [x] 1. Umbenennen: App, Modelle, Felder, Funktionen/Methoden, Klassen, Variablen, Konstanten, Kommentare/Docstrings,
      Tests, Admin, Forms, Management-Command, URL-Namen/-Pfade, Template-Dateinamen und Template-Variablen
- [x] 2. DB-Trigger (R8/R9) mit englischen Tabellen-, Spalten- und Funktionsnamen neu schreiben
- [x] 3. Audit-Felder auf **allen eigenen Tabellen** (Club, Squad, Person, SquadLeadership, SquadAssignment, Attendance, User, Invitation):
      `created_at`, `created_by`, `updated_at`, `updated_by` (FK → User, `SET_NULL`, nicht editierbar)
  - abstrakte Basisklasse `AuditedModel` mit `save()`: beim Erzeugen **ein** Zeitstempel für `created_at` = `updated_at`
    und `created_by` = `updated_by`; beim Ändern nur `updated_*` (auch bei `save(update_fields=…)`)
  - aktueller User per Middleware in einer `contextvar` → gilt automatisch für Views, Admin und Formulare;
    ohne Request (seed_demo, Shell) bleibt der User leer
  - ersetzt die bisherigen Felder `Einsatz.erfasst_von/erfasst_am`, `Einladung.erstellt_am`, `User.date_joined`
  - reines Login (`last_login`) zählt nicht als Änderung
  - Admin: Audit-Felder schreibgeschützt anzeigen
- [x] 4. Migrationen neu erzeugen (statt Rename-Migrationen; die App ist noch nicht deployed).
      **Lokale DB wird dabei zurückgesetzt** (`docker compose down -v`, danach `seed_demo`)
- [x] 5. Tests übersetzen + neue Tests für die Audit-Felder (Erzeugen, Ändern, ohne Request)
- [x] 6. README auf Englisch; Entwickler-Details (Umsetzung R1–R13, Trigger, mypy, Konventionen, Befehle) nach CLAUDE.md
- [x] 7. Verifikation: mypy, ruff (nur neue Befunde), Tests in Docker, App starten und Login/Erfassen/Export per HTTP prüfen

## Review

- 38 Tests grün (32 übersetzt + 6 neue Audit-Tests), mypy ohne Befunde, `makemigrations --check` ohne Änderungen
- HTTP geprüft: Login, Erfassen, Riegenansicht, Zuteilungen, Auswertung, CSV-Export, Admin (Audit-Felder sichtbar)
- Alte Migrationen gelöscht und neu erzeugt, lokale DB zurückgesetzt und neu befüllt (`seed_demo`)
- Beim Erzeugen ist `updated_at == created_at` (ein Zeitstempel) und `updated_by == created_by`
- Ohne Request (seed_demo, Shell) bleiben `created_by`/`updated_by` leer; die Selbstregistrierung ebenso
- Ruff: nur die bekannten RUF012-Hinweise (Django-Meta/Admin-Listen)
