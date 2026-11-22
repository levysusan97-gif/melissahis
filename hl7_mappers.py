"""Genera mensajes HL7 v2.5 (ADT y ORU) desde filas de la base (dict)."""
from datetime import datetime


def _esc(s) -> str:
    """Escapa los caracteres reservados de HL7 en un texto."""
    s = "" if s is None else str(s)
    return (s.replace("\\", "\\E\\").replace("|", "\\F\\").replace("^", "\\S\\")
             .replace("&", "\\T\\").replace("~", "\\R\\"))


def _fecha(s: str) -> str:
    return (s or "").replace("-", "")[:8]


def _msh(tipo: str, evento: str, ctrl: str) -> str:
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"MSH|^~\\&|MELIHEALTH|MELIHEALTH-HIS|DESTINO|DESTINO|{ts}||{tipo}^{evento}|{ctrl}|P|2.5"


def _pid(p: dict) -> str:
    campos = ["PID", "1", "", f'{_esc(p["rut"])}^^^RUN^NI', "",
              f'{_esc(p["apellidos"])}^{_esc(p["nombres"])}', "", _fecha(p["fecha_nacimiento"]),
              _esc(p["sexo"]), "", "", f'^^{_esc(p["ciudad"])}^^^CL', "", _esc(p["telefono"])]
    return "|".join(campos)


def _pv1(prof: dict | None) -> str:
    doc = ""
    if prof:
        doc = f'{_esc(prof["rut"])}^{_esc(prof["nombre"])}'
    return "|".join(["PV1", "1", "O", "", "", "", "", doc])  # PV1-7 = médico tratante


def adt(evento: str, paciente: dict, profesional: dict | None = None) -> str:
    """evento: 'A04' (registro) o 'A08' (actualización de datos)."""
    segs = [_msh("ADT", evento, f'ADT{paciente["id"]}'), f"EVN|{evento}", _pid(paciente), _pv1(profesional)]
    return "\r".join(segs)


def oru_r01(paciente: dict, signos: list) -> str:
    segs = [_msh("ORU", "R01", f'ORU{paciente["id"]}'), _pid(paciente),
            "OBR|1|||SV^Signos vitales^L"]
    n = 0

    def obx(tipo, cod, nombre, valor, unidad):
        nonlocal n
        n += 1
        segs.append(f"OBX|{n}|{tipo}|{cod}^{nombre}^LN||{_esc(valor)}|{_esc(unidad)}|||||F")

    for s in signos:
        obx("ST", "85354-9", "Presion arterial", s["pa"], "mm[Hg]")
        obx("NM", "8867-4", "Frecuencia cardiaca", s["fc"], "/min")
        obx("NM", "9279-1", "Frecuencia respiratoria", s["fr"], "/min")
        obx("NM", "8310-5", "Temperatura", s["temp"], "Cel")
        obx("NM", "2708-6", "Saturacion O2", s["sato2"], "%")
    return "\r".join(segs)
