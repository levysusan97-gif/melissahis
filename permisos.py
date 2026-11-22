"""
Perfilado de roles: qué puede hacer cada rol en cada módulo.
  "ver"      = solo consultar
  "escribir" = consultar y registrar/modificar
Si un módulo no aparece para un rol, ese rol no tiene acceso.
EDITA ESTA TABLA para ajustar los perfiles (principio de mínimo privilegio).
Los nombres de rol deben coincidir con la tabla `roles`.
"""

MATRIZ = {
    "Administrador": {
        "usuarios": "escribir", "auditoria": "ver", "pacientes": "ver", "agenda": "ver",
        "fhir": "ver", "hl7": "ver",
    },
    "Admisionista": {
        "pacientes": "escribir", "agenda": "escribir",
    },
    "Médico": {
        "pacientes": "ver", "agenda": "ver", "atenciones": "escribir",
        "diagnosticos": "escribir", "signos_vitales": "escribir",
    },
    "Enfermero": {
        "pacientes": "ver", "agenda": "ver", "atenciones": "ver",
        "diagnosticos": "ver", "signos_vitales": "escribir",
    },
    "TENS": {
        "pacientes": "ver", "agenda": "ver", "signos_vitales": "escribir",
    },
    "Administrativo": {
        "pacientes": "ver", "agenda": "escribir",
    },
    "Interoperabilidad HL7-FHIR": {
        "pacientes": "ver", "fhir": "ver", "hl7": "ver",
    },
}

NIVEL = {"ver": 1, "escribir": 2}


def permitido(rol: str, modulo: str, accion: str = "ver") -> bool:
    nivel = MATRIZ.get(rol, {}).get(modulo)
    return nivel is not None and NIVEL[nivel] >= NIVEL[accion]


def permisos_de(rol: str) -> dict:
    return MATRIZ.get(rol, {})
