# MeliHealth HIS

## Puesta en marcha (Windows, desde C:\melihealth-his)
1. `pip install -r backend\requirements.txt`
2. `cd database` y `python cargar_datos.py`   (crea melihealth.db desde los 2 Excel)
3. `cd ..\backend` y `uvicorn api:app --reload`
4. Abre http://127.0.0.1:8000/docs para probar los endpoints.

## Conectar un HTML del frontend (ejemplo para pacientes.html)
    const r = await fetch("http://127.0.0.1:8000/patients?q=juan&limit=20");
    const pacientes = await r.json();

## Datos
- RUT de pacientes y profesionales son FICTICIOS (rangos 98/99 millones), solo para pruebas.
- Las contraseñas se guardan con hash; el "1234" del Excel ya no queda en la base.
- Pendiente: token (JWT) para proteger endpoints, y reemplazar RUT_SYSTEM en fhir/fhir_mappers.py por el de CL Core.

## Roles y permisos
- La matriz rol → módulo está en backend/permisos.py (edítala para ajustar perfiles).
- POST /login devuelve un `token` y los `permisos` del rol. Envíalo en cada llamada:
      fetch(url, { headers: { Authorization: "Bearer " + token } })
- Sin token responde 401; con un rol sin permiso responde 403 y queda en auditoría.
- Define la variable de entorno MELIHEALTH_SECRET antes de usarlo fuera de pruebas.
