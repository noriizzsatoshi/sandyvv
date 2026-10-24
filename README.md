# Sandy

Biblioteca de tickets y respuestas en español, basada en el proyecto del ZIP. Conserva su diseño, búsqueda, categorías, favoritos, respuestas y editor. Ahora incorpora cuentas, permisos y un catálogo compartido mediante Python y SQLite.

## Permisos

| Función | Usuario | Admin | Developer |
| --- | --- | --- | --- |
| Consultar y buscar tickets y respuestas | Sí | Sí | Sí |
| Copiar respuestas y guardar favoritos personales | Sí | Sí | Sí |
| Crear, editar y borrar tickets, categorías y respuestas | No | Sí | Sí |
| Cambiar apariencia, textos y opciones de la página | No | No | Sí |
| Importar, exportar o restablecer el catálogo | No | No | Sí |
| Crear cuentas y asignar sus roles | No | No | Sí |

Los permisos se comprueban en cada escritura del servidor. Ocultar los botones es una ayuda visual; modificar JavaScript o localStorage no otorga permisos. Developer personaliza las opciones existentes de Configuración; no ejecuta código arbitrario desde la página.

## Primer inicio

Requiere Python 3.10 o superior, sin paquetes externos. Desde la carpeta del proyecto:

```sh
python server.py --create-user mi-developer --role developer
python server.py
```

El primer comando pide la contraseña sin mostrarla (mínimo 12 caracteres). No existen cuentas ni contraseñas predeterminadas. Ingresá con esa cuenta; su primer acceso inicializa el catálogo de ejemplos. Después, en **Configuración → Cuentas**, creá los usuarios normales y administradores. También se pueden crear cuentas desde la terminal con `--create-user` y `--role usuario` o `--role admin`.

La aplicación se sirve en el puerto 8000 y escucha en la interfaz local de forma predeterminada. Para otro puerto o interfaz, usá `--port` y `--host`. Abrir `index.html` directamente ya no es suficiente: se necesita el servidor para autenticar y guardar.

## Cambiar o restablecer una contraseña

En una terminal dentro de la carpeta del proyecto, ejecutá:

```sh
python server.py --change-password mi-developer
```

Reemplazá `mi-developer` por el nombre de la cuenta si es otro. Escribí y repetí la nueva contraseña (mínimo 12 caracteres); no se muestra mientras la escribís. Se conservan los tickets, las cuentas y sus roles. Se cierran las sesiones de esa cuenta para que vuelva a ingresar con la nueva contraseña. En Windows podés usar `py` si `python` no se reconoce. Este restablecimiento requiere acceso a la terminal del servidor y no está disponible desde el navegador.

## Datos y sesiones

- Catálogo y cuentas en `.data/sandy.sqlite3`, excluido de Git. `SANDY_DATA_DIR` permite usar otra carpeta persistente.
- Contraseñas protegidas con scrypt y sal aleatoria; sesiones aleatorias en cookies HttpOnly y SameSite, con vencimiento a las 8 horas. Cerrar sesión invalida la sesión en el servidor.
- Favoritos personales por cuenta en el almacenamiento local del navegador; no se comparten entre dispositivos.
- Las escrituras usan revisiones: un cambio concurrente se rechaza y se recarga el catálogo vigente. En caso de conflicto, volvé a realizar la edición; no se sobrescriben cambios ajenos silenciosamente.
- Los respaldos JSON incluyen contenido, no cuentas ni sesiones. Copiá también la base SQLite mediante las herramientas de respaldo de SQLite para conservar cuentas.
- El contenido previo guardado por el prototipo en localStorage no se importa automáticamente. Un developer puede importar su respaldo JSON desde Configuración.

## Validación

```sh
python -m unittest discover -s tests -v
node --check app.js
```

La suite comprueba lecturas y escrituras reales por HTTP, permisos de cada rol, creación de cuentas, conflictos de revisión, logout, bloqueo de envíos sin el encabezado requerido y protección de archivos privados. Node solo se usa para comprobar la sintaxis; no se necesita para ejecutar la aplicación.

## Alcance del despliegue

Esta entrega sirve para desarrollo y pruebas del proyecto. Para acceso público, usá un servidor/proxy de producción con HTTPS, limitación de intentos de acceso, almacenamiento persistente y copias de seguridad. Configurá `SANDY_SECURE_COOKIE=1` al servir por HTTPS. No se incluyen recuperación de contraseñas por correo, edición/desactivación de cuentas ni auditoría de cambios. El servidor HTTP de la biblioteca estándar de Python no está pensado para publicación directa en Internet.
