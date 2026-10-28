# Actualizar la instalación existente de Serviciudad

Estos pasos corresponden a la instalación **existente**: código en
`/var/www/seleccion/app`, entorno Python en `/var/www/seleccion/.venv`, servicio
systemd `seleccion` y base MySQL `seleccion`. No recrean la base de datos ni
importan datos desde el equipo Windows.

Ejecute los comandos en la terminal de Ubuntu. Si ya está como `root`, puede
mantener los `sudo`; no necesita ejecutar `sudo su` otra vez.

## 1. Ubicarse y comprobar el repositorio

```bash
cd /var/www/seleccion/app
pwd
ls -l manage.py
sudo -u seleccion git -C /var/www/seleccion/app status --short
```

La última orden debe salir vacía. Si aparecen modificaciones o archivos
desconocidos, deténgase: no los descarte ni sobrescriba.

## 2. Respaldar el MySQL actual, sin borrar respaldos anteriores

Compruebe primero que la cuenta de respaldo esté configurada:

```bash
sudo test -r /etc/seleccion/mysql-backup.cnf && echo 'Cuenta de respaldo disponible'
```

Si no aparece ese mensaje, deténgase antes de actualizar. Si aparece, genere un
archivo nuevo, compruebe que es legible y anote la ruta impresa:

```bash
sudo install -d -m 700 /var/backups/seleccion
sudo bash -c 'set -euo pipefail; archivo=$(mktemp /var/backups/seleccion/antes-actualizacion-XXXXXX.sql.gz); mysqldump --defaults-extra-file=/etc/seleccion/mysql-backup.cnf --single-transaction --routines --events --no-tablespaces --databases seleccion | gzip -9 > "$archivo"; test -s "$archivo"; gzip -t "$archivo"; sha256sum "$archivo" > "$archivo.sha256"; echo "Respaldo: $archivo"'
```

Si falla, **no siga**. Guarde además una copia del respaldo fuera de la VM o
del disco del servidor. Esta orden no ejecuta la rotación que elimina copias
antiguas.

## 3. Descargar los cambios de GitHub

```bash
sudo -u seleccion git -C /var/www/seleccion/app pull --ff-only origin main
sudo -u seleccion git -C /var/www/seleccion/app log -1 --oneline
```

No ejecute `git pull` en `/var/www/seleccion`: allí no está `.git`. No copie
`.env`, `db.sqlite3` ni una base de datos del computador Windows al servidor.

## 4. Aplicar exclusivamente las migraciones previstas

La aplicación debe detenerse brevemente para no recibir cambios durante la
migración. La siguiente orden pedirá la clave de la cuenta MySQL
`seleccion_migracion`; no la escriba en el comando ni la envíe por chat.

```bash
sudo systemctl stop seleccion
sudo -u seleccion /var/www/seleccion/.venv/bin/python /var/www/seleccion/app/deploy/aplicar_migraciones_servidor.py
```

El programa verifica que está conectado a `seleccion` en MySQL local y que
solo estén pendientes `0015_separar_vinculacion_contratacion` y
`0016_decision_verificaciones` (o ninguna si ya se habían aplicado). Estas
migraciones conservan candidatos y decisiones existentes; cambian el rol y
nombre de la cuenta creadora original y agregan el campo de verificaciones.
Si informa migraciones inesperadas o un conflicto de cuentas, deténgase y
revise el mensaje antes de hacer otra cosa.

## 5. Publicar archivos estáticos y reiniciar

Continúe **solo si la migración terminó correctamente**:

```bash
sudo -u seleccion /var/www/seleccion/.venv/bin/python /var/www/seleccion/app/manage.py collectstatic --noinput
sudo systemctl start seleccion
sudo systemctl is-active seleccion
```

Debe aparecer `active`. Entre a la aplicación y compruebe que sigan los
candidatos y procesos anteriores, que se vea el login nuevo y que carguen las
pantallas de Gerencia. Si falla algún paso, no repita la migración a ciegas;
conserve el respaldo y revise `sudo journalctl -u seleccion -n 80 --no-pager`.

## Crear la cuenta final de Contratación

Después de aplicar las migraciones 0015 y 0016 y descargar el comando
`crear_contratacion`, puede crear la cuenta final sin tocar Vinculación ni los
procesos. No hay otra migración para esta cuenta. Esta ejecución carga el mismo
archivo de entorno del servicio para evitar crear por error el usuario en SQLite:

```bash
sudo systemd-run --wait --pty --collect --uid=seleccion --working-directory=/var/www/seleccion/app --property=EnvironmentFile=/etc/seleccion/seleccion.env /var/www/seleccion/.venv/bin/python manage.py crear_contratacion --exigir-mysql --permitir-clave-inicial-11
```

La contraseña se solicita dos veces sin mostrarse ni almacenarse en el código.
La opción de 11 caracteres se limita a esta creación inicial y no cambia la
política general de contraseñas. Use una contraseña única y más larga cuando
pueda; las cuentas compartidas reducen la seguridad y la atribución de acciones.
Si el usuario ya existe, no se modifica su contraseña ni su rol.
