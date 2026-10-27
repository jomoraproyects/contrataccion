# Procesos de contratación

Aplicación web interna para gestionar procesos de selección de personal de forma clara y segura.

Permite registrar candidatos, llevarlos por Talento Humano, Psicología, Seguridad y Salud en el Trabajo y Contratación, registrar decisiones con observaciones obligatorias y conservar la trazabilidad completa.

## Funcionalidades

- Registro de candidatos sin adjuntar hojas de vida.
- Flujo secuencial sin saltar etapas.
- Aprobación o rechazo con observación obligatoria.
- Lista de verificación por etapa: cinco requisitos en Talento Humano; entrevista y prueba psicotécnica en Psicología; y en SST, Examen Panel X5, radiografía de columna, electromiografía y examen osteomuscular. Cada requisito se registra como Cumple o No cumple.
- Alertas dentro del sistema y tiempo laboral restante, contado de 7:00 a. m. a 4:00 p. m. en días hábiles.
- Validación de cédulas al crear un candidato: evita nuevos registros si existe un proceso previo y muestra la etapa y el motivo del rechazo anterior.
- Historial de decisiones y trazabilidad resumida por candidato para Gerencia.
- Filtros de fechas, estado, etapa, vacante y cumplimiento, con detección de cuellos de botella.
- Indicadores con gráficas y consulta por semana, mes o año, según la fecha de llegada de la hoja de vida. Al abrir muestran el mes actual; Excel y PDF respetan el periodo seleccionado.
- Procesos rechazados, contratados y archivados sin borrar información.
- Una persona solo puede tener un proceso abierto a la vez.
- Gestión de usuarios, roles, bloqueos y contraseñas.
- Login protegido con bcrypt, límites de intentos, sesiones seguras y auditoría.

## Roles

- **Vinculación:** registra candidatos, consulta antecedentes de su cédula y envía el proceso a Talento Humano. No aprueba etapas.
- **Talento Humano:** valida requisitos y antecedentes.
- **Psicología:** registra la entrevista.
- **Seguridad y Salud en el Trabajo:** registra exámenes.
- **Contratación:** recibe los candidatos aprobados por las tres áreas y completa únicamente la última etapa.
- **Gerencia:** consulta el historial, gestiona usuarios y monitorea tiempos.

## Tecnologías

- Python y Django con templates.
- Bootstrap y JavaScript.
- SQLite para desarrollo y MySQL 8+ para producción.
- Gunicorn y Nginx para el servidor local de la empresa.
- WhiteNoise y `holidays`.

## Uso local

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py crear_gerente
python manage.py runserver
```

Abra `http://127.0.0.1:8000/` e ingrese con la cuenta de Gerencia creada.

## Pruebas

```bash
python manage.py test
python manage.py check
```

Los archivos de referencia para producción se encuentran en `deploy/`. La guía para
Ubuntu, red interna, MySQL, HTTPS y respaldos está en `deploy/INSTALACION_LOCAL.md`.

## Preparación para producción local

La aplicación exige MySQL cuando `DEBUG=False` y no inicia con una base SQLite por error. Antes de publicar:

1. Copie `deploy/seleccion.env.example` a `/etc/seleccion/seleccion.env` y aplique permisos `600`.
2. Genere una `SECRET_KEY` distinta y configure dominio, origen HTTPS y `DATABASE_URL`.
3. Mantenga `TRUST_PROXY_HEADERS=True` únicamente porque Gunicorn se publica mediante el socket privado de Nginx incluido.
4. Ejecute migraciones y `collectstatic`, active el servicio y compruebe `/salud/`.
5. Configure el respaldo diario con `deploy/backup_mysql.sh` y pruebe una restauración antes de operar con datos reales.

Empiece con HSTS de una hora. Después de confirmar que HTTPS funciona correctamente, puede aumentarlo gradualmente.

El límite de intentos se aplica en Django: cinco intentos y 15 minutos para Talento Humano, Psicología y Seguridad y Salud en el Trabajo, además de protección por IP para usuarios desconocidos. Gerencia, Vinculación y Contratación mantienen la política de accesos esenciales sin bloqueo temporal ni desactivación manual.

## Actualización de Vinculación y Contratación

La migración `0015_separar_vinculacion_contratacion` convierte las cuentas que antes creaban candidatos con rol Contratación al nuevo rol Vinculación. La cuenta cuyo usuario era `contratacion` pasa a llamarse `vinculacion`, conservando exactamente la misma contraseña, identidad, procesos, decisiones y seguimientos. Si ya existe otra cuenta llamada `vinculacion`, la migración se detiene para evitar una colisión. No modifica las cuatro etapas ni sus plazos. Realice un respaldo antes de aplicar esta migración en el servidor.

Después de actualizar, Gerencia debe abrir **Equipo → Crear usuario** y crear la cuenta del responsable de la última etapa con rol **Contratación**, usando por ejemplo el nombre de acceso `contratacion` y una contraseña propia. No se crean contraseñas predeterminadas.

La migración de roles no tiene reversión automática: una cuenta de Contratación creada después no se debe confundir con las antiguas cuentas creadoras. El respaldo previo permite recuperar la configuración anterior si fuera necesario.

## Listas de verificación

Para aprobar Talento Humano, Psicología o SST se debe responder cada requisito como **Cumple**. Para rechazar, todos deben tener una respuesta y al menos uno debe ser **No cumple**; la observación sigue siendo obligatoria. Los requisitos pendientes no generan rechazos automáticos. Contratación conserva su decisión final habitual.

La migración `0016_decision_verificaciones` añade el registro de la lista a cada decisión. Los resultados y los nombres de los requisitos se conservan tal como fueron registrados. Las decisiones antiguas conservan su observación y aparecen sin lista histórica; no se inventan verificaciones anteriores. El motivo, la etapa y los requisitos no cumplidos se muestran a Gerencia, en Rechazados, al consultar la cédula y en Excel/PDF.
