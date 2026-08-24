# db/students.py — alumnos (datos maestros compartidos)

from __future__ import annotations



from datetime import date, datetime



from db.connection import get_db

from db.groups import group_exists

from utils.text import normalize_for_sort



_STUDENT_SELECT = """

    SELECT

        id,

        grupo,

        alumno,

        sexo,

        email_student,

        email_mother,

        email_father,

        cie,

        doc,

        fecha_nacimiento,

        telefono1,

        telefono2,

        obs_tfno,

        difusion_imagen,

        transporte,

        repetidor,

        parada

    FROM students

"""





def ensure_students_schema() -> None:

    """Añade columnas nuevas de alumnado si la BD es anterior."""

    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                """

                ALTER TABLE students ADD COLUMN IF NOT EXISTS cie TEXT

                """

            )

            cur.execute(

                """

                ALTER TABLE students ADD COLUMN IF NOT EXISTS doc TEXT

                """

            )

            cur.execute(

                """

                ALTER TABLE students ADD COLUMN IF NOT EXISTS fecha_nacimiento DATE

                """

            )

            cur.execute(

                """

                ALTER TABLE students ADD COLUMN IF NOT EXISTS telefono1 TEXT

                """

            )

            cur.execute(

                """

                ALTER TABLE students ADD COLUMN IF NOT EXISTS telefono2 TEXT

                """

            )

            cur.execute(

                """

                ALTER TABLE students ADD COLUMN IF NOT EXISTS obs_tfno TEXT

                """

            )

            cur.execute(

                """

                ALTER TABLE students ADD COLUMN IF NOT EXISTS difusion_imagen BOOLEAN

                """

            )

            cur.execute(

                """

                ALTER TABLE students ADD COLUMN IF NOT EXISTS transporte BOOLEAN

                """

            )

            cur.execute(

                """

                ALTER TABLE students ADD COLUMN IF NOT EXISTS repetidor BOOLEAN

                """

            )

            cur.execute(

                """

                ALTER TABLE students ADD COLUMN IF NOT EXISTS parada TEXT

                """

            )

            cur.execute(

                """

                CREATE INDEX IF NOT EXISTS idx_students_cie

                ON students (cie) WHERE cie IS NOT NULL

                """

            )





def _norm_optional_text(v: str | None) -> str | None:

    if v is None:

        return None

    t = str(v).strip()

    return t if t else None





def parse_bool_import(value) -> bool | None:

    """Convierte sí/no, S/N, 1/0, etc. en booleano; None si vacío."""

    if value is None:

        return None

    if isinstance(value, bool):

        return value

    if isinstance(value, (int, float)):

        if value == 1:

            return True

        if value == 0:

            return False

        raise ValueError("Valor booleano no válido")

    s = str(value).strip().lower()

    if not s:

        return None

    if s in ("sí", "si", "s", "yes", "y", "1", "true", "verdadero", "x"):

        return True

    if s in ("no", "n", "0", "false", "falso"):

        return False

    raise ValueError("Valor booleano no válido (use Sí/No)")





def parse_date_import(value) -> date | None:

    if value is None:

        return None

    if isinstance(value, datetime):

        return value.date()

    if isinstance(value, date):

        return value

    s = str(value).strip()

    if not s:

        return None

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):

        try:

            return datetime.strptime(s[:10], fmt).date()

        except ValueError:

            continue

    raise ValueError("Fecha no válida (use AAAA-MM-DD o DD/MM/AAAA)")





def _bool_display(value: bool | None) -> str:

    if value is True:

        return "Sí"

    if value is False:

        return "No"

    return ""





def _row_to_student_dict(row: dict) -> dict:

    fd = row.get("fecha_nacimiento")

    if isinstance(fd, date):

        fecha_display = fd.strftime("%d/%m/%Y")

        fecha_iso = fd.isoformat()

    elif fd:

        fecha_display = str(fd)[:10]

        fecha_iso = str(fd)[:10]

    else:

        fecha_display = ""

        fecha_iso = ""



    dif = row.get("difusion_imagen")

    trans = row.get("transporte")

    rep = row.get("repetidor")



    return {

        "id": row.get("id"),

        "grupo": row["grupo"],

        "alumno": row["alumno"],

        "sexo": row.get("sexo"),

        "email_student": row.get("email_student"),

        "email_mother": row.get("email_mother"),

        "email_father": row.get("email_father"),

        "cie": row.get("cie"),

        "doc": row.get("doc"),

        "fecha_nacimiento": fd,

        "fecha_nacimiento_display": fecha_display,

        "fecha_nacimiento_iso": fecha_iso,

        "telefono1": row.get("telefono1"),

        "telefono2": row.get("telefono2"),

        "obs_tfno": row.get("obs_tfno"),

        "difusion_imagen": dif,

        "difusion_imagen_display": _bool_display(dif),

        "transporte": trans,

        "transporte_display": _bool_display(trans),

        "repetidor": rep,

        "repetidor_display": _bool_display(rep),

        "parada": row.get("parada"),

    }





def get_all_groups() -> list[str]:

    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                """

                SELECT DISTINCT grupo

                FROM students

                WHERE grupo IS NOT NULL

                """

            )

            grupos = [r["grupo"] for r in cur.fetchall()]



    grupos.sort(key=normalize_for_sort)

    return grupos





def get_all_students() -> list[dict]:

    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(_STUDENT_SELECT)

            rows = cur.fetchall()



    rows.sort(

        key=lambda r: (

            str(r.get("grupo") or ""),

            normalize_for_sort(str(r.get("alumno") or "")),

        )

    )



    return [_row_to_student_dict(r) for r in rows]





def get_students_by_group(grupo: str) -> list[str]:

    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                """

                SELECT alumno

                FROM students

                WHERE grupo = %s

                """,

                (grupo,),

            )

            alumnos = [r["alumno"] for r in cur.fetchall()]



    alumnos.sort(key=normalize_for_sort)

    return alumnos





def student_exists(*, grupo: str, alumno: str) -> bool:

    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                """

                SELECT 1

                FROM students

                WHERE grupo = %s

                  AND alumno = %s

                """,

                (grupo, alumno),

            )

            return cur.fetchone() is not None





def create_student_manual(*, grupo: str, alumno: str, sexo: str) -> None:

    """Alta manual: grupo, alumno y sexo obligatorios; el grupo debe existir en ``groups``."""

    grupo = (grupo or "").strip()

    alumno = (alumno or "").strip()

    sexo = (sexo or "").strip().upper()



    if not grupo or not alumno or not sexo:

        raise ValueError("Grupo, alumno y sexo son obligatorios")

    if sexo not in ("M", "V"):

        raise ValueError("Sexo debe ser M o V")

    if not group_exists(grupo):

        raise ValueError("Grupo no válido: debe existir en la tabla de grupos")

    if student_exists(grupo=grupo, alumno=alumno):

        raise ValueError("Ya existe un alumno con ese nombre en el grupo")



    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                """

                INSERT INTO students (grupo, alumno, sexo)

                VALUES (%s, %s, %s)

                """,

                (grupo, alumno, sexo),

            )





def create_student_if_not_exists(*, grupo: str, alumno: str) -> bool:

    """Inserta solo grupo+alumno si no existe. Legacy simple."""

    r = upsert_student_from_import(

        grupo=grupo,

        alumno=alumno,

    )

    return r == "created"





def upsert_student_from_import(

    *,

    grupo: str,

    alumno: str,

    sexo: str | None = None,

    email_student: str | None = None,

    email_mother: str | None = None,

    email_father: str | None = None,

    cie: str | None = None,

    doc: str | None = None,

    fecha_nacimiento: date | None = None,

    telefono1: str | None = None,

    telefono2: str | None = None,

    obs_tfno: str | None = None,

    difusion_imagen: bool | None = None,

    transporte: bool | None = None,

    repetidor: bool | None = None,

    parada: str | None = None,

) -> str:

    """

    Alta o actualización parcial por (grupo, alumno).

    Solo actualiza columnas cuyo argumento no es None.



    Devuelve: 'created' | 'updated' | 'unchanged'.

    """

    grupo = grupo.strip()

    alumno = alumno.strip()



    if not grupo or not alumno:

        raise ValueError("Grupo y alumno son obligatorios")

    if not group_exists(grupo):

        raise ValueError("Grupo no válido: debe existir en la tabla groups")



    if sexo is not None:

        sx = str(sexo).strip().upper()

        if sx == "":

            sexo = None

        elif sx in ("M", "V"):

            sexo = sx

        else:

            raise ValueError("Sexo debe ser M, V o vacío")



    email_student = _norm_optional_text(email_student)

    email_mother = _norm_optional_text(email_mother)

    email_father = _norm_optional_text(email_father)

    cie = _norm_optional_text(cie)

    doc = _norm_optional_text(doc)

    telefono1 = _norm_optional_text(telefono1)

    telefono2 = _norm_optional_text(telefono2)

    obs_tfno = _norm_optional_text(obs_tfno)

    parada = _norm_optional_text(parada)



    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                """

                SELECT

                    sexo, email_student, email_mother, email_father,

                    cie, doc, fecha_nacimiento, telefono1, telefono2, obs_tfno,

                    difusion_imagen, transporte, repetidor, parada

                FROM students

                WHERE grupo = %s AND alumno = %s

                """,

                (grupo, alumno),

            )

            row = cur.fetchone()



            if not row:

                cur.execute(

                    """

                    INSERT INTO students (

                        grupo, alumno, sexo,

                        email_student, email_mother, email_father,

                        cie, doc, fecha_nacimiento, telefono1, telefono2, obs_tfno,

                        difusion_imagen, transporte, repetidor, parada

                    )

                    VALUES (

                        %s, %s, %s,

                        %s, %s, %s,

                        %s, %s, %s, %s, %s, %s,

                        %s, %s, %s, %s

                    )

                    """,

                    (

                        grupo,

                        alumno,

                        sexo,

                        email_student,

                        email_mother,

                        email_father,

                        cie,

                        doc,

                        fecha_nacimiento,

                        telefono1,

                        telefono2,

                        obs_tfno,

                        difusion_imagen,

                        transporte,

                        repetidor,

                        parada,

                    ),

                )

                return "created"



            patch: dict = {}

            if sexo is not None:

                patch["sexo"] = sexo

            if email_student is not None:

                patch["email_student"] = email_student

            if email_mother is not None:

                patch["email_mother"] = email_mother

            if email_father is not None:

                patch["email_father"] = email_father

            if cie is not None:

                patch["cie"] = cie

            if doc is not None:

                patch["doc"] = doc

            if fecha_nacimiento is not None:

                patch["fecha_nacimiento"] = fecha_nacimiento

            if telefono1 is not None:

                patch["telefono1"] = telefono1

            if telefono2 is not None:

                patch["telefono2"] = telefono2

            if obs_tfno is not None:

                patch["obs_tfno"] = obs_tfno

            if difusion_imagen is not None:

                patch["difusion_imagen"] = difusion_imagen

            if transporte is not None:

                patch["transporte"] = transporte

            if repetidor is not None:

                patch["repetidor"] = repetidor

            if parada is not None:

                patch["parada"] = parada



            if not patch:

                return "unchanged"



            sets = ", ".join(f"{k} = %s" for k in patch)

            vals = list(patch.values())

            vals.extend([grupo, alumno])

            cur.execute(

                f"""

                UPDATE students

                SET {sets}

                WHERE grupo = %s AND alumno = %s

                """,

                vals,

            )

            return "updated"





def change_student_group(

    *,

    grupo_actual: str,

    alumno: str,

    nuevo_grupo: str,

) -> bool:

    alumno = alumno.strip()

    grupo_actual = grupo_actual.strip()

    nuevo_grupo = nuevo_grupo.strip()



    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                """

                UPDATE students

                SET grupo = %s

                WHERE grupo = %s

                  AND alumno = %s

                """,

                (nuevo_grupo, grupo_actual, alumno),

            )

            updated = cur.rowcount > 0



    return updated




def get_student_by_id(student_id: int) -> dict | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                {_STUDENT_SELECT.strip()}
                WHERE id = %s
                """,
                (int(student_id),),
            )
            row = cur.fetchone()
    if not row:
        return None
    return _row_to_student_dict(row)


def update_student_admin(
    *,
    student_id: int,
    grupo: str,
    alumno: str,
    sexo: str | None = None,
    email_student: str | None = None,
    email_mother: str | None = None,
    email_father: str | None = None,
    cie: str | None = None,
    doc: str | None = None,
    fecha_nacimiento: date | None = None,
    telefono1: str | None = None,
    telefono2: str | None = None,
    obs_tfno: str | None = None,
    difusion_imagen: bool | None = None,
    transporte: bool | None = None,
    repetidor: bool | None = None,
    parada: str | None = None,
) -> None:
    """Actualiza un alumno por id (gestión admin)."""
    grupo = (grupo or "").strip()
    alumno = (alumno or "").strip()
    sexo_v = (sexo or "").strip().upper() or None

    if not grupo or not alumno:
        raise ValueError("Grupo y alumno son obligatorios")
    if sexo_v is not None and sexo_v not in ("M", "V"):
        raise ValueError("Sexo debe ser M o V")
    if not group_exists(grupo):
        raise ValueError("Grupo no válido: debe existir en la tabla de grupos")

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM students WHERE id = %s",
                (int(student_id),),
            )
            if not cur.fetchone():
                raise ValueError("Alumno no encontrado")

            cur.execute(
                """
                SELECT id FROM students
                WHERE grupo = %s AND alumno = %s AND id <> %s
                """,
                (grupo, alumno, int(student_id)),
            )
            if cur.fetchone():
                raise ValueError("Ya existe un alumno con ese nombre en el grupo")

            cur.execute(
                """
                UPDATE students
                SET grupo = %s,
                    alumno = %s,
                    sexo = %s,
                    email_student = %s,
                    email_mother = %s,
                    email_father = %s,
                    cie = %s,
                    doc = %s,
                    fecha_nacimiento = %s,
                    telefono1 = %s,
                    telefono2 = %s,
                    obs_tfno = %s,
                    difusion_imagen = %s,
                    transporte = %s,
                    repetidor = %s,
                    parada = %s
                WHERE id = %s
                """,
                (
                    grupo,
                    alumno,
                    sexo_v,
                    _norm_optional_text(email_student),
                    _norm_optional_text(email_mother),
                    _norm_optional_text(email_father),
                    _norm_optional_text(cie),
                    _norm_optional_text(doc),
                    fecha_nacimiento,
                    _norm_optional_text(telefono1),
                    _norm_optional_text(telefono2),
                    _norm_optional_text(obs_tfno),
                    difusion_imagen,
                    transporte,
                    repetidor,
                    _norm_optional_text(parada),
                    int(student_id),
                ),
            )

