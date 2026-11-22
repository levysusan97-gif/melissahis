"""Hash de contraseñas y tokens de sesión firmados (solo librería estándar)."""
import base64
import hashlib
import hmac
import json
import os
import time

ITERACIONES = 200_000
# En producción define la variable de entorno MELIHEALTH_SECRET con un valor largo y secreto.
SECRETO = os.environ.get("MELIHEALTH_SECRET", "clave-solo-para-desarrollo")


def hash_password(password: str) -> str:
    sal = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), sal, ITERACIONES)
    return f"pbkdf2_sha256${ITERACIONES}${sal.hex()}${h.hex()}"


def verify_password(password: str, guardado: str) -> bool:
    try:
        _, iters, sal, h = guardado.split("$")
        nuevo = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(sal), int(iters))
        return hmac.compare_digest(nuevo.hex(), h)
    except ValueError:
        return False


def _firmar(cuerpo_b64: str) -> str:
    return hmac.new(SECRETO.encode(), cuerpo_b64.encode(), hashlib.sha256).hexdigest()


def crear_token(datos: dict, minutos: int = 480) -> str:
    cuerpo = dict(datos, exp=int(time.time()) + minutos * 60)
    b64 = base64.urlsafe_b64encode(json.dumps(cuerpo).encode()).decode().rstrip("=")
    return f"{b64}.{_firmar(b64)}"


def leer_token(token: str) -> dict | None:
    """Devuelve los datos del token, o None si es inválido o expiró."""
    try:
        b64, firma = token.split(".")
        if not hmac.compare_digest(firma, _firmar(b64)):
            return None
        cuerpo = json.loads(base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4)))
        return cuerpo if cuerpo["exp"] >= time.time() else None
    except (ValueError, KeyError):
        return None
