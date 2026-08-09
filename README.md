# Procesos de contratación

Aplicación web interna para gestionar procesos de selección de personal de forma clara y segura.

Permite registrar candidatos, llevarlos por Talento Humano, Psicología, Seguridad y Salud en el Trabajo y Contratación, registrar decisiones con observaciones obligatorias y conservar la trazabilidad completa.

## Funcionalidades

- Registro de candidatos sin adjuntar hojas de vida.
- Flujo secuencial sin saltar etapas.
- Aprobación o rechazo con observación obligatoria.
- Alertas dentro del sistema y días hábiles restantes.
- Historial de decisiones, tiempos y trazabilidad para Gerencia.
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
- SQLite para desarrollo y PostgreSQL para producción.
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
