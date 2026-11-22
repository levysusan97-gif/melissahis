"""
API de MeliHealth HIS.
Instalar:  pip install fastapi uvicorn
Ejecutar (desde la carpeta backend):  uvicorn api:app --reload
Documentación interactiva:  http://127.0.0.1:8000/docs
"""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

RAIZ = Path(__file__).resolve().parent.parent
for carpeta in ("backend", "fhir", "hl7"):
    sys.path.insert(0, str(RAIZ / carpeta))
import fhir_mappers  # noqa: E402
import hl7_mappers  # noqa: E402
import permisos  # noqa: E402
from seguridad import crear_token, leer_token, verify_password  # noqa: E402

DB = RAIZ / "database" / "melihealth.db"

app = FastAPI(title="MeliHealth HIS")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def consulta(sql: str, params: tuple = ()) -> list[dict]:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        return [dict(f) for f in con.execute(sql, params)]
    finally:
        con.close()


def auditar(usuario: str, accion: str, modulo: str) -> None:
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO auditoria (fecha_hora, usuario, accion, modulo) VALUES (?,?,?,?)",
                (datetime.now().strftime("%Y-%m-%d %H:%M"), usuario, accion, modulo))
    con.commit()
    con.close()


def paciente_o_404(pid: int) -> dict:
    filas = consulta("SELECT * FROM pacientes WHERE id = ?", (pid,))
    if not filas:
        raise HTTPException(404, "Paciente no encontrado")
    return filas[0]


def usuario_actual(authorization: str = Header(default="")) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Debes iniciar sesión")
    datos = leer_token(authorization[7:])
    if not datos:
        raise HTTPException(401, "Sesión inválida o expirada")
    return datos


def requiere(modulo: str, accion: str = "ver"):
    """Exige sesión iniciada y que el rol tenga permiso sobre el módulo."""
    def dependencia(u: dict = Depends(usuario_actual)) -> dict:
        if not permisos.permitido(u["rol"], modulo, accion):
            auditar(u["usuario"], f"Acceso denegado ({modulo}:{accion})", modulo.capitalize())
            raise HTTPException(403, f"Tu rol ({u['rol']}) no tiene permiso para {modulo}:{accion}")
        return u
    return dependencia


class Login(BaseModel):
    usuario: str
    password: str


@app.post("/login")
def login(datos: Login):
    filas = consulta(
        "SELECT u.usuario, u.nombre, u.password_hash, r.nombre AS rol "
        "FROM usuarios u JOIN roles r ON r.id = u.rol_id WHERE u.usuario = ?", (datos.usuario,))
    if not filas or not verify_password(datos.password, filas[0]["password_hash"]):
        auditar(datos.usuario, "Inicio Sesión fallido", "Login")
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    u = filas[0]
    auditar(u["usuario"], "Inicio Sesión", "Login")
    token = crear_token({"usuario": u["usuario"], "nombre": u["nombre"], "rol": u["rol"]})
    return {"token": token, "usuario": u["usuario"], "nombre": u["nombre"], "rol": u["rol"],
            "permisos": permisos.permisos_de(u["rol"])}


@app.get("/me")
def yo(u: dict = Depends(usuario_actual)):
    return {**u, "permisos": permisos.permisos_de(u["rol"])}


@app.get("/roles/matriz")
def matriz_roles(u: dict = Depends(requiere("usuarios"))):
    return permisos.MATRIZ


@app.get("/patients")
def listar_pacientes(q: str = "", limit: int = Query(20, le=100), offset: int = 0,
                     u: dict = Depends(requiere("pacientes"))):
    like = f"%{q}%"
    return consulta(
        "SELECT * FROM pacientes WHERE nombres LIKE ? OR apellidos LIKE ? OR rut LIKE ? "
        "ORDER BY id LIMIT ? OFFSET ?", (like, like, like, limit, offset))


@app.get("/patients/{pid}")
def ver_paciente(pid: int, u: dict = Depends(requiere("pacientes"))):
    auditar(u["usuario"], f"Consulta ficha paciente {pid}", "Pacientes")
    return paciente_o_404(pid)


@app.get("/patients/{pid}/fhir")
def paciente_fhir(pid: int, u: dict = Depends(requiere("fhir"))):
    pac = paciente_o_404(pid)
    auditar(u["usuario"], f"Generación FHIR paciente {pid}", "FHIR")
    aten = consulta("SELECT * FROM atenciones WHERE paciente_id = ?", (pid,))
    diag = consulta("SELECT d.* FROM diagnosticos d JOIN atenciones a ON a.id = d.atencion_id "
                    "WHERE a.paciente_id = ?", (pid,))
    sig = consulta("SELECT * FROM signos_vitales WHERE paciente_id = ?", (pid,))
    profs = consulta("SELECT * FROM profesionales WHERE id IN "
                     "(SELECT profesional_id FROM atenciones WHERE paciente_id = ?)", (pid,))
    return fhir_mappers.bundle_paciente(pac, aten, diag, sig, profs)


@app.get("/patients/{pid}/hl7", response_class=PlainTextResponse)
def paciente_hl7(pid: int, tipo: str = "ADT_A04", u: dict = Depends(requiere("hl7"))):
    pac = paciente_o_404(pid)
    auditar(u["usuario"], f"Generación HL7 {tipo} paciente {pid}", "HL7")
    if tipo in ("ADT_A04", "ADT_A08"):
        prof = consulta("SELECT * FROM profesionales WHERE id IN "
                        "(SELECT profesional_id FROM atenciones WHERE paciente_id = ? LIMIT 1)", (pid,))
        msg = hl7_mappers.adt(tipo.split("_")[1], pac, prof[0] if prof else None)
    elif tipo == "ORU_R01":
        msg = hl7_mappers.oru_r01(pac, consulta("SELECT * FROM signos_vitales WHERE paciente_id = ?", (pid,)))
    else:
        raise HTTPException(400, "tipo debe ser ADT_A04, ADT_A08 o ORU_R01")
    return msg.replace("\r", "\n")  # el separador real es \r; \n solo para verlo en pantalla


@app.get("/professionals")
def profesionales(u: dict = Depends(requiere("agenda"))):
    return consulta("SELECT * FROM profesionales")


@app.get("/professionals/{prid}/fhir")
def profesional_fhir(prid: int, u: dict = Depends(requiere("fhir"))):
    filas = consulta("SELECT * FROM profesionales WHERE id = ?", (prid,))
    if not filas:
        raise HTTPException(404, "Profesional no encontrado")
    return fhir_mappers.practitioner(filas[0])


@app.get("/appointments")
def citas(fecha: str | None = None, u: dict = Depends(requiere("agenda"))):
    sql = ("SELECT c.*, p.nombres || ' ' || p.apellidos AS paciente, pr.nombre AS profesional "
           "FROM citas c JOIN pacientes p ON p.id = c.paciente_id "
           "JOIN profesionales pr ON pr.id = c.profesional_id")
    if fecha:
        return consulta(sql + " WHERE c.fecha = ? ORDER BY c.hora", (fecha,))
    return consulta(sql + " ORDER BY c.fecha, c.hora")


@app.get("/encounters")
def atenciones(paciente_id: int | None = None, u: dict = Depends(requiere("atenciones"))):
    sql = ("SELECT a.*, pr.nombre AS profesional FROM atenciones a "
           "JOIN profesionales pr ON pr.id = a.profesional_id")
    if paciente_id:
        return consulta(sql + " WHERE a.paciente_id = ?", (paciente_id,))
    return consulta(sql)


@app.get("/audit")
def auditoria(limit: int = 50, u: dict = Depends(requiere("auditoria"))):
    return consulta("SELECT * FROM auditoria ORDER BY id DESC LIMIT ?", (limit,))
