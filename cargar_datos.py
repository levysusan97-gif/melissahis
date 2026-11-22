"""
Carga los dos Excel a una base SQLite (melihealth.db).
Uso (desde la carpeta database):  python cargar_datos.py
Requiere: pip install pandas openpyxl
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "backend"))
from seguridad import hash_password  # noqa: E402

DB = AQUI / "melihealth.db"
XLS_HIS = AQUI / "meli_prueba_his.xlsx"
XLS_PAC = AQUI / "melissa_pacientes_de_prueba.xlsx"

# RUT ficticios: rangos 98/99 millones (de personas jurídicas), no chocan con personas reales.
BASE_RUT_PACIENTE = 99_000_000
BASE_RUT_PROFESIONAL = 98_000_000


def dv_rut(n: int) -> str:
    suma, mult = 0, 2
    for d in reversed(str(n)):
        suma += int(d) * mult
        mult = 2 if mult == 7 else mult + 1
    r = 11 - suma % 11
    return "0" if r == 11 else "K" if r == 10 else str(r)


def rut_ficticio(base: int, i: int) -> str:
    n = base + i
    return f"{n}-{dv_rut(n)}"


def limpia_nombre(s: str) -> str:
    for pref in ("Dr. ", "Dra. "):
        s = s.replace(pref, "")
    return s.strip().lower()


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE roles (id INTEGER PRIMARY KEY, nombre TEXT UNIQUE NOT NULL);
CREATE TABLE usuarios (
  id INTEGER PRIMARY KEY, usuario TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
  nombre TEXT NOT NULL, rol_id INTEGER NOT NULL REFERENCES roles(id));
CREATE TABLE especialidades (id INTEGER PRIMARY KEY, nombre TEXT UNIQUE NOT NULL);
CREATE TABLE pacientes (
  id INTEGER PRIMARY KEY, rut TEXT UNIQUE NOT NULL, nombres TEXT NOT NULL, apellidos TEXT NOT NULL,
  fecha_nacimiento TEXT, sexo TEXT, telefono TEXT, email TEXT, ciudad TEXT);
CREATE TABLE profesionales (
  id INTEGER PRIMARY KEY, usuario_id INTEGER REFERENCES usuarios(id), rut TEXT UNIQUE NOT NULL,
  nombre TEXT NOT NULL, profesion TEXT, especialidad TEXT);
CREATE TABLE citas (
  id INTEGER PRIMARY KEY, paciente_id INTEGER NOT NULL REFERENCES pacientes(id),
  fecha TEXT, hora TEXT, profesional_id INTEGER NOT NULL REFERENCES profesionales(id), estado TEXT);
CREATE TABLE atenciones (
  id INTEGER PRIMARY KEY, paciente_id INTEGER NOT NULL REFERENCES pacientes(id),
  fecha TEXT, profesional_id INTEGER NOT NULL REFERENCES profesionales(id), motivo TEXT);
CREATE TABLE diagnosticos (
  id INTEGER PRIMARY KEY, atencion_id INTEGER NOT NULL REFERENCES atenciones(id),
  cie10 TEXT NOT NULL, descripcion TEXT);
CREATE TABLE signos_vitales (
  id INTEGER PRIMARY KEY, paciente_id INTEGER NOT NULL REFERENCES pacientes(id),
  fecha TEXT, pa TEXT, fc INTEGER, fr INTEGER, temp REAL, sato2 INTEGER);
CREATE TABLE auditoria (
  id INTEGER PRIMARY KEY AUTOINCREMENT, fecha_hora TEXT, usuario TEXT, accion TEXT, modulo TEXT);
CREATE TABLE interop_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, paciente_id INTEGER REFERENCES pacientes(id),
  estandar TEXT, tipo TEXT, estado TEXT, fecha TEXT);
"""


def main() -> None:
    his = pd.read_excel(XLS_HIS, sheet_name=None, dtype=str)
    pac = pd.read_excel(XLS_PAC, dtype=str)

    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)

    # Roles y usuarios (contraseñas con hash, nunca en texto plano)
    con.executemany("INSERT INTO roles VALUES (?,?)", [(int(r.ID), r.Rol) for r in his["Roles"].itertuples()])
    rol_id = {r.Rol: int(r.ID) for r in his["Roles"].itertuples()}
    for fila in his["Usuarios"].to_dict("records"):
        con.execute(
            "INSERT INTO usuarios VALUES (?,?,?,?,?)",
            (int(fila["ID"]), fila["Usuario"], hash_password(fila["Contraseña"]), fila["Nombre"], rol_id[fila["Rol"]]),
        )
    usuario_por_nombre = {limpia_nombre(r.Nombre): int(r.ID) for r in his["Usuarios"].itertuples()}

    con.executemany("INSERT INTO especialidades VALUES (?,?)",
                    [(int(r.ID), r.Especialidad) for r in his["Especialidades"].itertuples()])

    # Pacientes: el ID es el orden de la fila (1..100), igual que PacienteID en las otras hojas
    for i, r in enumerate(pac.itertuples(), start=1):
        con.execute(
            "INSERT INTO pacientes VALUES (?,?,?,?,?,?,?,?,?)",
            (i, rut_ficticio(BASE_RUT_PACIENTE, i), r.fname, r.lname, str(r.DOB)[:10],
             r.sex, r.phone_home, r.email, r.city),
        )

    # Profesionales: se vinculan con su usuario por nombre
    for r in his["Profesionales"].itertuples():
        con.execute(
            "INSERT INTO profesionales VALUES (?,?,?,?,?,?)",
            (int(r.ID), usuario_por_nombre.get(limpia_nombre(r.Nombre)),
             rut_ficticio(BASE_RUT_PROFESIONAL, int(r.ID)), r.Nombre, r.Profesion, r.Especialidad),
        )

    for r in his["Citas"].itertuples():
        con.execute("INSERT INTO citas VALUES (?,?,?,?,?,?)",
                    (int(r.ID), int(r.PacienteID), str(r.Fecha)[:10], str(r.Hora)[:5], int(r.ProfesionalID), r.Estado))
    for r in his["Atenciones"].itertuples():
        con.execute("INSERT INTO atenciones VALUES (?,?,?,?,?)",
                    (int(r.ID), int(r.PacienteID), str(r.Fecha)[:10], int(r.ProfesionalID), r.MotivoConsulta))
    for r in his["Diagnosticos"].itertuples():
        con.execute("INSERT INTO diagnosticos VALUES (?,?,?,?)",
                    (int(r.ID), int(r.AtencionID), r.CIE10, r.Diagnostico))
    for r in his["SignosVitales"].itertuples():
        con.execute("INSERT INTO signos_vitales VALUES (?,?,?,?,?,?,?,?)",
                    (int(r.ID), int(r.PacienteID), str(r.Fecha)[:10], r.PA, int(r.FC), int(r.FR),
                     round(float(r.Temp), 1), int(r.SatO2)))
    for r in his["Auditoria"].itertuples():
        con.execute("INSERT INTO auditoria (fecha_hora, usuario, accion, modulo) VALUES (?,?,?,?)",
                    (r.FechaHora, r.Usuario, r.Accion, r.Modulo))
    for r in his["FHIR"].itertuples():
        con.execute("INSERT INTO interop_log (paciente_id, estandar, tipo, estado, fecha) VALUES (?,?,?,?,NULL)",
                    (int(r.PacienteID), "FHIR", r.ResourceType, r.Estado))
    for r in his["HL7"].itertuples():
        con.execute("INSERT INTO interop_log (paciente_id, estandar, tipo, estado, fecha) VALUES (?,?,?,?,?)",
                    (int(r.PacienteID), "HL7", r.TipoMensaje, "Generado", str(r.Fecha)[:10]))

    con.commit()
    for t in ["roles", "usuarios", "pacientes", "profesionales", "citas", "atenciones",
              "diagnosticos", "signos_vitales", "auditoria", "interop_log"]:
        print(f"{t:15} {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]} filas")
    con.close()
    print(f"\nBase creada: {DB}")


if __name__ == "__main__":
    main()
