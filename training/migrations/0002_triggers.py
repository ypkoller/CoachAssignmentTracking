"""DB triggers for the cross-table rules R8 and R9 (in addition to Model.clean())."""

from django.db import migrations

SAME_CLUB = """
CREATE FUNCTION training_check_same_club() RETURNS trigger AS $$
BEGIN
    IF (SELECT club_id FROM training_person WHERE id = NEW.person_id)
       IS DISTINCT FROM (SELECT club_id FROM training_squad WHERE id = NEW.squad_id) THEN
        RAISE EXCEPTION 'R8: Person und Riege müssen zum selben Verein gehören.'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER squadleadership_same_club
    BEFORE INSERT OR UPDATE OF person_id, squad_id ON training_squadleadership
    FOR EACH ROW EXECUTE FUNCTION training_check_same_club();
CREATE TRIGGER squadassignment_same_club
    BEFORE INSERT OR UPDATE OF person_id, squad_id ON training_squadassignment
    FOR EACH ROW EXECUTE FUNCTION training_check_same_club();
CREATE TRIGGER attendance_same_club
    BEFORE INSERT OR UPDATE OF person_id, squad_id ON training_attendance
    FOR EACH ROW EXECUTE FUNCTION training_check_same_club();
"""

ATTENDANCE_ASSIGNMENT = """
CREATE FUNCTION training_attendance_assignment() RETURNS trigger AS $$
DECLARE
    assigned_role varchar;
BEGIN
    SELECT role INTO assigned_role
      FROM training_squadassignment
     WHERE person_id = NEW.person_id
       AND squad_id = NEW.squad_id
       AND valid_from <= NEW.date
       AND (valid_until IS NULL OR valid_until >= NEW.date);
    IF NOT FOUND THEN
        RAISE EXCEPTION 'R9: Die Person ist am % der Riege nicht zugeteilt.', NEW.date
            USING ERRCODE = 'check_violation';
    END IF;
    NEW.role := assigned_role;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER attendance_assignment
    BEFORE INSERT OR UPDATE ON training_attendance
    FOR EACH ROW EXECUTE FUNCTION training_attendance_assignment();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("training", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            SAME_CLUB,
            reverse_sql="""
                DROP TRIGGER squadleadership_same_club ON training_squadleadership;
                DROP TRIGGER squadassignment_same_club ON training_squadassignment;
                DROP TRIGGER attendance_same_club ON training_attendance;
                DROP FUNCTION training_check_same_club();
            """,
        ),
        migrations.RunSQL(
            ATTENDANCE_ASSIGNMENT,
            reverse_sql="""
                DROP TRIGGER attendance_assignment ON training_attendance;
                DROP FUNCTION training_attendance_assignment();
            """,
        ),
    ]
