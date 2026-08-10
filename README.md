# Procesos de contratación

Aplicación web interna para gestionar procesos de selección de personal de forma clara y segura.

Permite registrar candidatos, llevarlos por Talento Humano, Psicología, Seguridad y Salud en el Trabajo y Contratación, registrar decisiones con observaciones obligatorias y conservar la trazabilidad completa.

## Funcionalidades

- Registro de candidatos sin adjuntar hojas de vida.
- Flujo secuencial sin saltar etapas.
- Aprobación o rechazo con observación obligatoria.
- Alertas dentro del sistema y días hábiles restantes.
- Historial de decisiones y trazabilidad resumida por candidato para Gerencia.
- Filtros de fechas, estado, etapa, vacante y cumplimiento, con detección de cuellos de botella.
- Procesos rechazados, contratados y archivados sin borrar información.
- Una persona solo puede tener un proceso abierto a la vez.
- Gestión de usuarios, roles, bloqueos y contraseñas.
- Login protegido con bcrypt, límites de intentos, sesiones seguras y auditoría.

## Roles

- **Contratación:** crea procesos y completa la contratación.
- **Talento Humano:** valida requisitos y antecedentes.
- **Psicología:** registra la entrevista.
- **Seguridad y Salud en el Trabajo:** registra exámenes.
- **Gerencia:** consulta el historial, gestiona usuarios y monitorea tiempos.

## Tecnologías

- Python y Django con templates.
- Bootstrap y JavaScript.
- SQLite para desarrollo y MySQL 8+ para producción.
- Gunicorn y Nginx para el VPS.
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

Los archivos de referencia para producción se encuentran en `deploy/`.

## Preparación para el VPS

La aplicación exige MySQL cuando `DEBUG=False` y no inicia con una base SQLite por error. Antes de publicar:

1. Copie `deploy/seleccion.env.example` a `/etc/seleccion/seleccion.env` y aplique permisos `600`.
2. Genere una `SECRET_KEY` distinta y configure dominio, origen HTTPS y `DATABASE_URL`.
3. Mantenga `TRUST_PROXY_HEADERS=True` únicamente porque Gunicorn se publica mediante el socket privado de Nginx incluido.
4. Ejecute migraciones y `collectstatic`, active el servicio y compruebe `/salud/`.
5. Configure el respaldo diario con `deploy/backup_mysql.sh` y pruebe una restauración antes de operar con datos reales.

Empiece con HSTS de una hora. Después de confirmar que HTTPS funciona correctamente, puede aumentarlo gradualmente.

El límite de intentos se aplica en Django: cinco intentos y 15 minutos para las cuentas operativas, además de protección por IP para usuarios desconocidos. El ejemplo de Nginx no agrega un bloqueo general porque bloquearía también los dos accesos esenciales que la aplicación debe mantener disponibles: Gerencia y Contratación.
