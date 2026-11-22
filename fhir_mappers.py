"""Convierte filas de la base (dict) a recursos FHIR R4 en JSON."""

# Sistema del RUT: marcador. Reemplazar por el definido en la guía CL Core de HL7 Chile.
RUT_SYSTEM = "https://melihealth.local/rut"
ICD10_SYSTEM = "http://hl7.org/fhir/sid/icd-10"
LOINC = "http://loinc.org"
UCUM = "http://unitsofmeasure.org"


def patient(p: dict) -> dict:
    r = {
        "resourceType": "Patient",
        "id": str(p["id"]),
        "identifier": [{"system": RUT_SYSTEM, "value": p["rut"]}],
        "name": [{"family": p["apellidos"], "given": [p["nombres"]]}],
        "gender": {"M": "male", "F": "female"}.get(p["sexo"], "unknown"),
        "birthDate": p["fecha_nacimiento"],
        "telecom": [],
        "address": [{"city": p["ciudad"], "country": "CL"}],
    }
    if p.get("telefono"):
        r["telecom"].append({"system": "phone", "use": "home", "value": p["telefono"]})
    if p.get("email"):
        r["telecom"].append({"system": "email", "value": p["email"]})
    return r


def practitioner(pr: dict) -> dict:
    return {
        "resourceType": "Practitioner",
        "id": str(pr["id"]),
        "identifier": [{"system": RUT_SYSTEM, "value": pr["rut"]}],
        "name": [{"text": pr["nombre"]}],
        "qualification": [{"code": {"text": f'{pr["profesion"]} - {pr["especialidad"]}'}}],
    }


def encounter(a: dict) -> dict:
    return {
        "resourceType": "Encounter",
        "id": str(a["id"]),
        "status": "finished",
        "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB"},
        "subject": {"reference": f'Patient/{a["paciente_id"]}'},
        "participant": [{"individual": {"reference": f'Practitioner/{a["profesional_id"]}'}}],
        "period": {"start": a["fecha"]},
        "reasonCode": [{"text": a["motivo"]}],
    }


def condition(d: dict, paciente_id: int) -> dict:
    return {
        "resourceType": "Condition",
        "id": str(d["id"]),
        "code": {"coding": [{"system": ICD10_SYSTEM, "code": d["cie10"], "display": d["descripcion"]}]},
        "subject": {"reference": f"Patient/{paciente_id}"},
        "encounter": {"reference": f'Encounter/{d["atencion_id"]}'},
    }


def _obs(id_, paciente_id, fecha, loinc, nombre, **valor):
    return {
        "resourceType": "Observation",
        "id": id_,
        "status": "final",
        "category": [{"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "vital-signs"}]}],
        "code": {"coding": [{"system": LOINC, "code": loinc, "display": nombre}]},
        "subject": {"reference": f"Patient/{paciente_id}"},
        "effectiveDateTime": fecha,
        **valor,
    }


def _qty(v, unidad, codigo):
    return {"valueQuantity": {"value": v, "unit": unidad, "system": UCUM, "code": codigo}}


def vital_observations(s: dict) -> list:
    pid, f, i = s["paciente_id"], s["fecha"], s["id"]
    out = []
    if s.get("pa") and "/" in s["pa"]:
        sis, dia = (int(x) for x in s["pa"].split("/"))
        o = _obs(f"{i}-pa", pid, f, "85354-9", "Presión arterial")
        o["component"] = [
            {"code": {"coding": [{"system": LOINC, "code": "8480-6", "display": "Sistólica"}]},
             **_qty(sis, "mmHg", "mm[Hg]")},
            {"code": {"coding": [{"system": LOINC, "code": "8462-4", "display": "Diastólica"}]},
             **_qty(dia, "mmHg", "mm[Hg]")},
        ]
        out.append(o)
    out += [
        _obs(f"{i}-fc", pid, f, "8867-4", "Frecuencia cardiaca", **_qty(s["fc"], "/min", "/min")),
        _obs(f"{i}-fr", pid, f, "9279-1", "Frecuencia respiratoria", **_qty(s["fr"], "/min", "/min")),
        _obs(f"{i}-temp", pid, f, "8310-5", "Temperatura corporal", **_qty(s["temp"], "°C", "Cel")),
        _obs(f"{i}-sat", pid, f, "2708-6", "Saturación de oxígeno", **_qty(s["sato2"], "%", "%")),
    ]
    return out


def bundle_paciente(pac, atenciones, diagnosticos, signos, profesionales) -> dict:
    recursos = [patient(pac)]
    recursos += [practitioner(x) for x in profesionales]
    recursos += [encounter(a) for a in atenciones]
    recursos += [condition(d, pac["id"]) for d in diagnosticos]
    for s in signos:
        recursos += vital_observations(s)
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [{"resource": r} for r in recursos],
    }
