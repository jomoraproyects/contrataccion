# Despliegue en cPanel con Passenger

## Requisitos del proveedor

- `Setup Python App` o `Application Manager` habilitado.
- Apache Passenger instalado.
- Python 3.12 o superior.
- Acceso a Terminal/SSH y variables de entorno.
- MySQL o MariaDB.

## 1. Subdominio

En cPanel crea, por ejemplo, `seleccion.tudominio.com`. Usa una carpeta de
aplicación separada, como `seleccion_personal`.

## 2. Código

Desde Terminal o Git Version Control:

```bash
git clone https://github.com/jomoraproyects/contrataccion.git seleccion_personal
cd seleccion_personal
```

También puedes subir un ZIP. No subas `.env`, `db.sqlite3` ni respaldos.

## 3. Aplicación Python

En **Software → Setup Python App → Create Application** selecciona:

- Python: 3.12 o superior.
- Application root: `seleccion_personal`.
- Application URL: el subdominio creado.
- Startup file: `passenger_wsgi.py`.
- Entry point: `application`.

Después instala las dependencias desde la terminal de la aplicación:

```bash
pip install -r requirements.txt
```

## 4. MySQL

Usa **MySQL Databases/Database Wizard** para crear una base y un usuario
exclusivos. cPanel puede anteponer el nombre de la cuenta, por ejemplo:
`cuenta_seleccion` y `cuenta_seleccion_app`.

Configura estas variables en la aplicación Python:

```text
SECRET_KEY=<valor-aleatorio-largo>
DEBUG=False
ALLOWED_HOSTS=seleccion.tudominio.com
CSRF_TRUSTED_ORIGINS=https://seleccion.tudominio.com
DATABASE_URL=mysql://cuenta_seleccion_app:<clave>@127.0.0.1:3306/cuenta_seleccion?charset=utf8mb4
TRUST_PROXY_HEADERS=True
```

## 5. Migraciones y archivos estáticos

```bash
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py check --deploy
```

Las cuentas se crean o actualizan con el comando seguro del proyecto:

```bash
python manage.py crear_gerente
```

## 6. Reinicio y comprobación

Después de cada actualización, reinicia Passenger desde Application Manager o
crea `tmp/restart.txt` dentro de la raíz de la aplicación. Comprueba el sitio
por HTTPS y revisa los errores de Passenger en **Errors** de cPanel.

No uses `runserver` en producción. PhpMyAdmin sirve para consultar/importar
datos, pero la creación de usuarios y permisos debe hacerse desde MySQL
Databases/Database Wizard.
