/* MeliHealth HIS – lógica del lado del navegador (sin servidor, sin instalar nada).
   DEMO: la seguridad real (claves, permisos) solo puede garantizarla un backend. */
const HIS = (() => {
  // ---------- SHA-256 (para no guardar contraseñas en texto plano) ----------
  const primos = [];
  for (let n = 2; primos.length < 64; n++) if (primos.every(p => n % p)) primos.push(n);
  const frac = x => Math.floor((x - Math.floor(x)) * 4294967296);
  const K = primos.map(p => frac(Math.cbrt(p)));
  const H0 = primos.slice(0, 8).map(p => frac(Math.sqrt(p)));
  const rotr = (x, n) => (x >>> n) | (x << (32 - n));
  function sha256(msg) {
    const b = new TextEncoder().encode(msg), l = b.length;
    const m = new Uint8Array(((l + 9 + 63) >> 6) << 6);
    m.set(b); m[l] = 0x80;
    const dv = new DataView(m.buffer);
    dv.setUint32(m.length - 4, (l * 8) >>> 0);
    dv.setUint32(m.length - 8, Math.floor(l * 8 / 4294967296));
    const h = H0.slice(), w = new Uint32Array(64);
    for (let o = 0; o < m.length; o += 64) {
      for (let i = 0; i < 16; i++) w[i] = dv.getUint32(o + i * 4);
      for (let i = 16; i < 64; i++) {
        const s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >>> 3);
        const s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >>> 10);
        w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
      }
      let [a, b2, c, d, e, f, g, hh] = h;
      for (let i = 0; i < 64; i++) {
        const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25), ch = (e & f) ^ (~e & g);
        const t1 = (hh + S1 + ch + K[i] + w[i]) >>> 0;
        const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22), mj = (a & b2) ^ (a & c) ^ (b2 & c);
        const t2 = (S0 + mj) >>> 0;
        hh = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b2; b2 = a; a = (t1 + t2) >>> 0;
      }
      [a, b2, c, d, e, f, g, hh].forEach((v, i) => (h[i] = (h[i] + v) >>> 0));
    }
    return h.map(x => x.toString(16).padStart(8, '0')).join('');
  }

  // ---------- Almacenamiento (datos base + lo que se registra en el navegador) ----------
  const CLAVE = 'melihealth_extra_v1';
  const vacio = () => ({ pacientes: [], signos_vitales: [], auditoria: [], atenciones: [], diagnosticos: [] });
  let extra = vacio();
  try { extra = Object.assign(vacio(), JSON.parse(localStorage.getItem(CLAVE) || '{}')); } catch (e) {}
  const guardar = () => { try { localStorage.setItem(CLAVE, JSON.stringify(extra)); } catch (e) {} };
  const datos = () => ({
    ...DATOS,
    pacientes: [...DATOS.pacientes, ...extra.pacientes],
    signos_vitales: [...DATOS.signos_vitales, ...extra.signos_vitales],
    auditoria: [...DATOS.auditoria, ...extra.auditoria],
    atenciones: [...DATOS.atenciones, ...extra.atenciones],
    diagnosticos: [...DATOS.diagnosticos, ...extra.diagnosticos],
  });
  const restablecer = () => { extra = vacio(); try { localStorage.removeItem(CLAVE); } catch (e) {} };

  // ---------- Roles y permisos (misma matriz que backend/permisos.py) ----------
  const MATRIZ = {
    'Administrador': { usuarios: 'escribir', auditoria: 'ver', pacientes: 'ver', agenda: 'ver', fhir: 'ver', hl7: 'ver' },
    'Admisionista': { pacientes: 'escribir', agenda: 'escribir' },
    'Médico': { pacientes: 'ver', agenda: 'ver', atenciones: 'escribir', diagnosticos: 'escribir', signos_vitales: 'escribir' },
    'Enfermero': { pacientes: 'ver', agenda: 'ver', atenciones: 'ver', diagnosticos: 'ver', signos_vitales: 'escribir' },
    'TENS': { pacientes: 'ver', agenda: 'ver', signos_vitales: 'escribir' },
    'Administrativo': { pacientes: 'ver', agenda: 'escribir' },
    'Interoperabilidad HL7-FHIR': { pacientes: 'ver', fhir: 'ver', hl7: 'ver' },
  };
  const NIVEL = { ver: 1, escribir: 2 };
  const permitido = (rol, mod, acc = 'ver') => {
    const n = (MATRIZ[rol] || {})[mod];
    return !!n && NIVEL[n] >= NIVEL[acc];
  };

  // ---------- Sesión y auditoría ----------
  let sesion = null;
  try { sesion = JSON.parse(sessionStorage.getItem('melihealth_sesion') || 'null'); } catch (e) {}
  const ahora = () => {
    const d = new Date(), p = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  };
  function auditar(usuario, accion, modulo) {
    extra.auditoria.push({ fecha_hora: ahora(), usuario, accion, modulo });
    guardar();
  }
  function login(usuario, password) {
    const u = DATOS.usuarios.find(x => x.usuario === usuario.trim());
    if (!u || u.hash !== sha256(u.usuario + ':' + password)) {
      auditar(usuario.trim() || '(vacío)', 'Inicio Sesión fallido', 'Login');
      return null;
    }
    sesion = { usuario: u.usuario, nombre: u.nombre, rol: u.rol };
    try { sessionStorage.setItem('melihealth_sesion', JSON.stringify(sesion)); } catch (e) {}
    auditar(u.usuario, 'Inicio Sesión', 'Login');
    return sesion;
  }
  function logout() {
    if (sesion) auditar(sesion.usuario, 'Cierre Sesión', 'Login');
    sesion = null;
    try { sessionStorage.removeItem('melihealth_sesion'); } catch (e) {}
  }

  // ---------- Registro de pacientes y signos vitales ----------
  function dvRut(n) {
    let s = 0, m = 2;
    for (const d of String(n).split('').reverse()) { s += +d * m; m = m === 7 ? 2 : m + 1; }
    const r = 11 - (s % 11);
    return r === 11 ? '0' : r === 10 ? 'K' : String(r);
  }
  function nuevoPaciente(p) {
    const id = Math.max(...datos().pacientes.map(x => x.id)) + 1;
    const reg = { id, rut: `${99000000 + id}-${dvRut(99000000 + id)}`, ...p };
    extra.pacientes.push(reg); guardar();
    return reg;
  }
  function nuevoSigno(s) {
    const id = Math.max(0, ...datos().signos_vitales.map(x => x.id)) + 1;
    const reg = { id, ...s };
    extra.signos_vitales.push(reg); guardar();
    return reg;
  }

  function nuevaAtencion(a) {
    const id = Math.max(0, ...datos().atenciones.map(x => x.id)) + 1;
    const reg = { id, ...a };
    extra.atenciones.push(reg); guardar();
    return reg;
  }
  function nuevoDiagnostico(dx) {
    const id = Math.max(0, ...datos().diagnosticos.map(x => x.id)) + 1;
    const reg = { id, ...dx };
    extra.diagnosticos.push(reg); guardar();
    return reg;
  }

  // ---------- FHIR R4 ----------
  const RUT_SYSTEM = 'https://melihealth.local/rut'; // reemplazar por el de CL Core (HL7 Chile)
  const LOINC = 'http://loinc.org', UCUM = 'http://unitsofmeasure.org';
  const qty = (v, unit, code) => ({ valueQuantity: { value: v, unit, system: UCUM, code } });
  const obs = (id, pid, fecha, loinc, nombre, extraProps) => ({
    resourceType: 'Observation', id, status: 'final',
    category: [{ coding: [{ system: 'http://terminology.hl7.org/CodeSystem/observation-category', code: 'vital-signs' }] }],
    code: { coding: [{ system: LOINC, code: loinc, display: nombre }] },
    subject: { reference: `Patient/${pid}` }, effectiveDateTime: fecha, ...extraProps,
  });
  const fhirPaciente = p => ({
    resourceType: 'Patient', id: String(p.id),
    identifier: [{ system: RUT_SYSTEM, value: p.rut }],
    name: [{ family: p.apellidos, given: [p.nombres] }],
    gender: { M: 'male', F: 'female' }[p.sexo] || 'unknown', birthDate: p.fecha_nacimiento,
    telecom: [
      ...(p.telefono ? [{ system: 'phone', use: 'home', value: p.telefono }] : []),
      ...(p.email ? [{ system: 'email', value: p.email }] : []),
    ],
    address: [{ city: p.ciudad, country: 'CL' }],
  });
  const fhirProfesional = x => ({
    resourceType: 'Practitioner', id: String(x.id),
    identifier: [{ system: RUT_SYSTEM, value: x.rut }], name: [{ text: x.nombre }],
    qualification: [{ code: { text: `${x.profesion} - ${x.especialidad}` } }],
  });
  function fhirSignos(s) {
    const out = [], pid = s.paciente_id, f = s.fecha, i = s.id;
    if (s.pa && s.pa.includes('/')) {
      const [sis, dia] = s.pa.split('/').map(Number);
      out.push(obs(`${i}-pa`, pid, f, '85354-9', 'Presión arterial', {
        component: [
          { code: { coding: [{ system: LOINC, code: '8480-6', display: 'Sistólica' }] }, ...qty(sis, 'mmHg', 'mm[Hg]') },
          { code: { coding: [{ system: LOINC, code: '8462-4', display: 'Diastólica' }] }, ...qty(dia, 'mmHg', 'mm[Hg]') },
        ],
      }));
    }
    out.push(
      obs(`${i}-fc`, pid, f, '8867-4', 'Frecuencia cardiaca', qty(s.fc, '/min', '/min')),
      obs(`${i}-fr`, pid, f, '9279-1', 'Frecuencia respiratoria', qty(s.fr, '/min', '/min')),
      obs(`${i}-temp`, pid, f, '8310-5', 'Temperatura corporal', qty(s.temp, '°C', 'Cel')),
      obs(`${i}-sat`, pid, f, '2708-6', 'Saturación de oxígeno', qty(s.sato2, '%', '%')));
    return out;
  }
  function fhirBundle(pid) {
    const d = datos(), p = d.pacientes.find(x => x.id === pid);
    const aten = d.atenciones.filter(a => a.paciente_id === pid);
    const ids = new Set(aten.map(a => a.id));
    const recursos = [fhirPaciente(p)];
    d.profesionales.filter(x => aten.some(a => a.profesional_id === x.id)).forEach(x => recursos.push(fhirProfesional(x)));
    aten.forEach(a => recursos.push({
      resourceType: 'Encounter', id: String(a.id), status: 'finished',
      class: { system: 'http://terminology.hl7.org/CodeSystem/v3-ActCode', code: 'AMB' },
      subject: { reference: `Patient/${pid}` },
      participant: [{ individual: { reference: `Practitioner/${a.profesional_id}` } }],
      period: { start: a.fecha }, reasonCode: [{ text: a.motivo }],
    }));
    d.diagnosticos.filter(x => ids.has(x.atencion_id)).forEach(x => recursos.push({
      resourceType: 'Condition', id: String(x.id),
      code: { coding: [{ system: 'http://hl7.org/fhir/sid/icd-10', code: x.cie10, display: x.descripcion }] },
      subject: { reference: `Patient/${pid}` }, encounter: { reference: `Encounter/${x.atencion_id}` },
    }));
    d.signos_vitales.filter(s => s.paciente_id === pid).forEach(s => recursos.push(...fhirSignos(s)));
    return { resourceType: 'Bundle', type: 'collection', entry: recursos.map(resource => ({ resource })) };
  }

  // ---------- HL7 v2.5 ----------
  const esc = s => String(s ?? '').replace(/\\/g, '\\E\\').replace(/\|/g, '\\F\\').replace(/\^/g, '\\S\\').replace(/&/g, '\\T\\').replace(/~/g, '\\R\\');
  const msh = (tipo, ev, ctrl) => {
    const d = new Date(), p = n => String(n).padStart(2, '0');
    const ts = `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
    return `MSH|^~\\&|MELIHEALTH|MELIHEALTH-HIS|DESTINO|DESTINO|${ts}||${tipo}^${ev}|${ctrl}|P|2.5`;
  };
  const pid = p => ['PID', '1', '', `${esc(p.rut)}^^^RUN^NI`, '', `${esc(p.apellidos)}^${esc(p.nombres)}`, '',
    (p.fecha_nacimiento || '').replace(/-/g, ''), esc(p.sexo), '', '', `^^${esc(p.ciudad)}^^^CL`, '', esc(p.telefono)].join('|');
  function hl7(tipo, pacienteId) {
    const d = datos(), p = d.pacientes.find(x => x.id === pacienteId);
    if (tipo === 'ADT_A04' || tipo === 'ADT_A08') {
      const ev = tipo.split('_')[1];
      const a = d.atenciones.find(x => x.paciente_id === pacienteId);
      const pr = a && d.profesionales.find(x => x.id === a.profesional_id);
      return [msh('ADT', ev, `ADT${p.id}`), `EVN|${ev}`, pid(p),
        ['PV1', '1', 'O', '', '', '', '', pr ? `${esc(pr.rut)}^${esc(pr.nombre)}` : ''].join('|')].join('\n');
    }
    const seg = [msh('ORU', 'R01', `ORU${p.id}`), pid(p), 'OBR|1|||SV^Signos vitales^L'];
    let n = 0;
    const obx = (t, c, nom, v, u) => seg.push(`OBX|${++n}|${t}|${c}^${nom}^LN||${esc(v)}|${esc(u)}|||||F`);
    d.signos_vitales.filter(s => s.paciente_id === pacienteId).forEach(s => {
      obx('ST', '85354-9', 'Presion arterial', s.pa, 'mm[Hg]');
      obx('NM', '8867-4', 'Frecuencia cardiaca', s.fc, '/min');
      obx('NM', '9279-1', 'Frecuencia respiratoria', s.fr, '/min');
      obx('NM', '8310-5', 'Temperatura', s.temp, 'Cel');
      obx('NM', '2708-6', 'Saturacion O2', s.sato2, '%');
    });
    return seg.join('\n'); // el separador real HL7 es \r; aquí \n solo para leerlo en pantalla
  }

  return {
    sha256, datos, restablecer, MATRIZ, permitido, auditar, login, logout,
    get sesion() { return sesion; }, nuevoPaciente, nuevoSigno, nuevaAtencion, nuevoDiagnostico, fhirBundle, hl7,
  };
})();
if (typeof module !== 'undefined') module.exports = HIS;
