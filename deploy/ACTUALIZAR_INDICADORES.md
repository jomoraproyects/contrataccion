# Actualizar indicadores y reportes sin migraciones

Instalación existente: repositorio `/var/www/seleccion/app`, entorno Python
`/var/www/seleccion/.venv`, servicio `seleccion`, MySQL `seleccion` y entorno
del servicio `/etc/seleccion/seleccion.env`.

Esta actualización cambia código, vistas y archivos estáticos. No incorpora
migraciones nuevas. No copie bases SQLite, archivos `.env` ni datos de Windows.
No ejecute comandos para recrear, importar o vaciar la base de datos.

## 1. Conectarse y comprobar el código del servidor

Desde PowerShell:

```powershell
ssh serviciudad@192.168.100.251
```

Los comandos siguientes se ejecutan en esa sesión de Ubuntu. La contraseña se
escribe únicamente en la terminal, nunca en el chat.

```bash
sudo -u seleccion git -C /var/www/seleccion/app status --short
```

Debe salir vacío. Si muestra cambios, deténgase: no los descarte.

## 2. Respaldar el MySQL del servidor

Estas órdenes usan la autenticación local de administrador mediante `sudo`,
que ya se utilizó en este servidor. Si falla, no continúe ni cambie usuarios
o contraseñas de MySQL para intentar resolverlo a ciegas.

```bash
sudo install -d -m 700 /var/backups/seleccion
sudo bash -c 'set -euo pipefail; archivo=$(mktemp /var/backups/seleccion/antes-indicadores-XXXXXX.sql.gz); mysqldump --single-transaction --routines --events --triggers --no-tablespaces --databases seleccion | gzip -9 > "$archivo"; test -s "$archivo"; gzip -t "$archivo"; sha256sum "$archivo" > "$archivo.sha256"; echo "Respaldo: $archivo"'
```

Debe terminar correctamente e imprimir la ruta de un respaldo nuevo. No borra
respaldos anteriores ni restaura nada sobre la base actual. Conserve también
una copia fuera de la VM; comprobar la compresión no sustituye una prueba de
restauración en una base separada.

## 3. Descargar y comprobar la actualización

```bash
sudo -u seleccion git -C /var/www/seleccion/app pull --ff-only origin main
sudo -u seleccion git -C /var/www/seleccion/app log -1 --oneline
sudo systemd-run --wait --pipe --collect --uid=seleccion --working-directory=/var/www/seleccion/app --property=EnvironmentFile=/etc/seleccion/seleccion.env /var/www/seleccion/.venv/bin/python manage.py check
```

Si alguna orden falla, deténgase y revise el error. Se carga el mismo entorno
del servicio para no usar accidentalmente SQLite u otra configuración. Las
dependencias de esta actualización no cambian.

## 4. Publicar el diseño y reiniciar

Antes del reinicio, avise a las personas que están usando el aplicativo para
que guarden los formularios abiertos. Los procesos guardados permanecen en
MySQL; el reinicio ocasiona una interrupción breve del acceso web.

```bash
sudo systemd-run --wait --pipe --collect --uid=seleccion --working-directory=/var/www/seleccion/app --property=EnvironmentFile=/etc/seleccion/seleccion.env /var/www/seleccion/.venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart seleccion
sudo systemctl is-active seleccion
```

Ejecute cada orden solo si la anterior termina bien. Debe aparecer `active`.
No necesita ejecutar `migrate`, crear usuarios ni restablecer contraseñas para
estos cambios.

## 5. Verificar en el navegador

Abra la dirección habitual del servidor y recargue con `Ctrl+F5`. Confirme:

- Los candidatos y procesos guardados anteriormente siguen disponibles.
- Indicadores conserva las seis gráficas, con filas completas y vacantes al
  final ocupando todo el ancho.
- La primera gráfica permite agrupar el histórico por semana, mes o año.
- Los filtros y los informes PDF/Excel conservan la selección aplicada.
- El listado sencillo de candidatos conserva etapa y motivo de rechazo.

El histórico cuenta recibidos por llegada de la HDV y resultados por fecha del
cierre válido. Puede incluir una contratación de un candidato recibido antes
del rango; no debe confundirse con el resumen por fecha de llegada.

Si el servicio no arranca:

```bash
sudo journalctl -u seleccion -n 60 --no-pager
```

No comparta contraseñas, el contenido del archivo de entorno ni información
personal de candidatos al solicitar soporte.
