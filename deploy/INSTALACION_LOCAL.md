# Instalación en el servidor local de la empresa

Arquitectura recomendada: Ubuntu Server 24.04 LTS en una máquina virtual, IP fija,
Nginx por HTTPS, Gunicorn mediante socket Unix y MySQL en la misma máquina. Los
empleados solo necesitan un navegador y acceso a la red interna.

## Datos que debe definir la empresa

- IP fija o reserva DHCP del servidor.
- Nombre DNS interno, por ejemplo `seleccion.interno.empresa.com`.
- Subred autorizada para acceder.
- Certificado emitido por la autoridad certificadora interna y confiado en los cinco equipos.
- Ruta de un NAS o segundo dispositivo para los respaldos.
- Persona responsable de actualizaciones, respaldos y recuperación.

No use el servidor para trabajo de oficina y no publique los puertos 8000 ni 3306 en la red.
Para acceso desde fuera de la empresa utilice una VPN, nunca redirección directa de puertos.

## Paquetes y usuario del servicio

```bash
sudo apt update
sudo apt install python3-venv python3-dev build-essential default-libmysqlclient-dev pkg-config mysql-server nginx git
sudo adduser --system --group --home /var/www/seleccion seleccion
sudo install -d -o seleccion -g www-data -m 0750 /var/www/seleccion
sudo install -d -o root -g seleccion -m 0750 /etc/seleccion
```

Clone el repositorio en `/var/www/seleccion`, cree `.venv`, instale
`requirements.txt` y copie `deploy/seleccion.env.example` como
`/etc/seleccion/seleccion.env` con permisos `600`.

Genere la clave secreta con:

```bash
/var/www/seleccion/.venv/bin/python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## MySQL con privilegios separados

Ejecute como administrador el contenido ajustado de `deploy/mysql.sql.example`.
La aplicación diaria usa `seleccion`; para migrar utilice temporalmente la cuenta
`seleccion_migracion`:

```bash
sudo -u seleccion env DATABASE_URL='mysql://seleccion_migracion:CLAVE@127.0.0.1:3306/seleccion?charset=utf8mb4' \
  /var/www/seleccion/.venv/bin/python /var/www/seleccion/manage.py migrate --noinput
sudo -u seleccion /var/www/seleccion/.venv/bin/python /var/www/seleccion/manage.py collectstatic --noinput
sudo -u seleccion /var/www/seleccion/.venv/bin/python /var/www/seleccion/manage.py check --deploy
sudo -u seleccion /var/www/seleccion/.venv/bin/python /var/www/seleccion/manage.py crear_gerente
```

No guarde la contraseña de migración en el archivo permanente de la aplicación.

## Servicios y HTTPS interno

- Instale `deploy/seleccion.service` como `/etc/systemd/system/seleccion.service`.
- Ajuste `deploy/nginx-lan.conf.example` y actívelo en Nginx.
- Coloque certificado y clave con permisos restringidos en `/etc/seleccion/tls/`.
- Confíe la CA interna en los computadores de los usuarios.
- Permita por firewall únicamente HTTPS desde la red empresarial y SSH desde la red administrativa.

```bash
sudo systemctl daemon-reload
sudo nginx -t
sudo systemctl enable --now seleccion nginx
curl --fail --cacert /ruta/ca-interna.crt https://seleccion.interno.empresa.com/salud/
```

## Respaldos

Monte primero el NAS o segundo disco en la ruta configurada como `BACKUP_DIR`. Copie
el script como `/usr/local/sbin/seleccion-backup` y los dos archivos de systemd a
`/etc/systemd/system/`. El archivo `mysql-backup.cnf` debe usar la cuenta de solo lectura
y tener permisos `600`.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now seleccion-backup.timer
sudo systemctl start seleccion-backup.service
sudo systemctl status seleccion-backup.service
sudo systemctl list-timers seleccion-backup.timer
```

Copiar archivos al mismo disco no constituye un respaldo. Mantenga una segunda copia
cifrada y pruebe la restauración trimestralmente en una base aislada.

## Actualizaciones controladas

```bash
cd /var/www/seleccion
sudo -u seleccion git pull --ff-only origin main
sudo -u seleccion .venv/bin/pip install -r requirements.txt
sudo -u seleccion env DATABASE_URL='mysql://seleccion_migracion:CLAVE@127.0.0.1:3306/seleccion?charset=utf8mb4' .venv/bin/python manage.py migrate --noinput
sudo -u seleccion .venv/bin/python manage.py collectstatic --noinput
sudo -u seleccion .venv/bin/python manage.py check --deploy
sudo systemctl restart seleccion
```

Antes de actualizar, genere un respaldo y confirme que el repositorio no contiene
archivos `.env`, bases SQLite, claves ni datos reales.

## Comprobación de entrega

- `systemctl is-active seleccion mysql nginx` devuelve `active`.
- `/salud/` devuelve `{"estado":"ok"}` mediante HTTPS.
- Los cinco roles pueden iniciar sesión y únicamente ven sus rutas autorizadas.
- Se completa un proceso de prueba por las cuatro etapas.
- Un rechazo detiene el flujo y conserva motivo y etapa.
- La aplicación vuelve sola después de reiniciar la máquina virtual.
- El respaldo se genera, verifica y restaura correctamente en una base de prueba.
