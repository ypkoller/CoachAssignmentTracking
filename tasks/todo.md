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

- ~~Tailwind und HTMX kommen noch per CDN~~ → erledigt im Branch `coolify-deployment`
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

# Coolify-Deployment – Branch `coolify-deployment`

Entscheide: App per **Dockerfile-Build-Pack**, Postgres als **eigene Coolify-Ressource** (mit Backups),
`docker-compose.yml` bleibt nur für lokal · Tailwind/HTMX werden **lokal ausgeliefert**.

## Gefundene Probleme für den Betrieb hinter dem Proxy

- **Login-Sperre trifft alle:** axes und django-ratelimit sehen hinter Traefik nur die Proxy-IP.
  5 Fehlversuche irgendeiner Person sperren alle für 1 h, das Passwort-Reset-Limit gilt global.
- `check --deploy`: HSTS nicht gesetzt (W004), kein SSL-Redirect in Django (W008, macht Traefik).
- Kein Healthcheck: Coolify kann nicht erkennen, ob ein neues Deployment bereit ist (Zero-Downtime).
- Tailwind-CDN ist laut Tailwind nicht für Produktion gedacht; Google Fonts lädt von Google (Datenschutz).

## Schritte

- [x] 1. Client-IP hinter dem Proxy: axes (`AXES_IPWARE_*`) und ratelimit (`RATELIMIT_IP_META_KEY`) auf
      `X-Forwarded-For` mit Proxy-Anzahl aus Env (`DJANGO_PROXY_COUNT`, Default 1); Tests dazu
- [x] 2. Security-Settings per Env: `DJANGO_HSTS_SECONDS` (Default 0, in Produktion z.B. 31536000);
      SSL-Redirect bleibt bei Traefik (W008 mit Begründung stummschalten)
- [x] 3. Healthcheck `/health/` (prüft DB-Verbindung) als Middleware vor dem Host-Check, damit er auch
      mit `Host: localhost` funktioniert; `curl` ins Image, `HEALTHCHECK` im Dockerfile; Test dazu
- [x] 4. Gunicorn: Worker-Anzahl über `WEB_CONCURRENCY` (Default 3), Timeout, Logs auf stdout
- [x] 5. Frontend lokal: Tailwind-Standalone-CLI im Docker-Build (gleiche Version 3.4.x, Konfiguration mit
      SVF-Farben aus `base.html`), HTMX 2.0.4 und Roboto-Schrift unter `static/`; CDN-Links entfernen
- [x] 6. Lokales Compose an das neue Image anpassen (weiterhin `docker compose up` für Entwicklung)
- [x] 7. Doku: README-Abschnitt «Deployment (Coolify)» mit Schritt-für-Schritt-Anleitung und Env-Tabelle,
      CLAUDE.md ergänzen
- [x] 8. Verifikation: Tests, mypy, `check --deploy` ohne Warnungen, Image mit Produktions-Env lokal starten,
      Healthcheck, UI ohne CDN im Browser/HTTP prüfen
- [ ] 9. Nach Freigabe: in Coolify einrichten (durch dich, mit Anleitung) → erstes Deployment →
      `createsuperuser` im Coolify-Terminal → Login und Erfassen auf der echten Domain testen

## Benötigte Angaben

1. Domain (z.B. `training.svfislisbach.ch`) – zeigt der DNS-Eintrag schon auf den Coolify-Server?
2. Coolify: Version (v4?), ist Server/Projekt eingerichtet? Ist das GitHub-Repo privat (dann GitHub App oder Deploy Key)?
3. Welcher Branch wird deployed (Empfehlung: `master` nach Merge) und Auto-Deploy bei Push ja/nein?
4. SMTP für den Passwort-Reset: Host, Port, TLS/SSL, Benutzer, Absenderadresse
   (Passwort **nicht** mir schicken, sondern direkt in Coolify eintragen)
5. Backups der DB: nur lokal auf dem Server oder auf S3? Gewünschter Rhythmus (Empfehlung: täglich)?
6. E-Mail für den ersten Administrator
7. Läuft vor Coolify noch ein weiterer Proxy (z.B. Cloudflare)? Wichtig für die Client-IP
8. Startdaten: werden Verein, Riegen und Personen von Hand im Admin erfasst, oder gibt es eine Liste zum Import?

### Antworten (2026-10-18)

Domain `training-svfislisbach.duckdns.org` (Server/Coolify v4 noch in Einrichtung) · Repo privat (GitHub App) ·
Auto-Deploy nur `master` · SMTP folgt später · Backups täglich nur auf dem Server · erster Admin per
`createsuperuser` (E-Mail nicht im Repo) · kein weiterer Proxy vor Coolify (Proxy-Anzahl 1) · Startdaten von Hand

## Review

- Client-IP über `config.client_ip` (rechter Eintrag von `X-Forwarded-For`, Proxy-Anzahl aus Env, Default 0);
  axes und ratelimit nutzen beide diese Funktion. Test: Sperre gilt nur noch für den betroffenen Client.
- `/health/` per Middleware (vor dem Host-Check), prüft die DB; Docker-`HEALTHCHECK` mit `curl`
- HSTS per `DJANGO_HSTS_SECONDS`, `includeSubDomains`; W008 (Redirect macht Traefik) und W021 (kein Preload) begründet stummgeschaltet
  → `check --deploy` mit Produktions-Env: keine Befunde
- Tailwind 3.4.16 Standalone-CLI im Docker-Build (Version + sha256 gepinnt, amd64/arm64), HTMX 2.0.4 (gleicher
  Hash wie vorher) und Roboto lokal → keine externen Quellen mehr
- Zusätzlich: `EMAIL_USE_SSL` für SMTP über Port 465 (z.B. Bluewin)
- 44 Tests grün, mypy ohne Befunde, Healthcheck «healthy», Seiten nach Login per HTTP geprüft
- Offen: Schritt 9 (Coolify einrichten) sobald der Server bereit ist; SMTP-Zugang
