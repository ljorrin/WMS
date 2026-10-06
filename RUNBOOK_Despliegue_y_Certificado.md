# Runbook — Despliegue WMS/TMS en Windows + Laragon + Docker Desktop

Guía reutilizable para publicar una app (WMS, TMS, …) con **Docker Desktop** detrás de **Laragon (Apache) como reverse proxy** y certificado **Let's Encrypt (win-acme)**.

> Para un dominio nuevo (ej. el TMS), reemplaza en toda la guía:
> - `<DOMINIO>` → p. ej. `wms.gs1pa.org` o `tms.gs1pa.org`
> - `<PROYECTO>` → carpeta del proyecto, p. ej. `E:\laragon\www\WMS`
> - `<PUERTO_INTERNO>` → puerto del Nginx del contenedor en el host (WMS usa `8080`; para el TMS usa otro distinto, p. ej. `8081`)

---

## 0. Arquitectura

```
Internet :443/:80 ─▶ Laragon Apache (Windows, dueño de 80/443)
     ├─ otras apps de Laragon
     └─ vhost <DOMINIO>  (SSL win-acme)
            └─ proxy ─▶ 127.0.0.1:<PUERTO_INTERNO> ─▶ Nginx del contenedor ─▶ API + frontend
```

Puntos clave de este montaje:
- Laragon mantiene 80/443; cada app Docker expone un **puerto interno distinto** (8080, 8081, …) y Laragon le hace proxy por dominio.
- El SSL se gestiona en **Windows con win-acme** (no con certbot dentro del contenedor), porque Laragon es quien atiende el puerto 80.
- Docker Desktop guarda sus datos en **D:** (Settings → Resources → Disk image location = `D:\DockerData`) para no llenar C:.

---

## 1. Requisitos antes de desplegar

- Docker Desktop instalado, datos en `D:\DockerData`.
- Registro **DNS A** de `<DOMINIO>` apuntando a la IP pública del servidor. Verifica:
  ```powershell
  nslookup <DOMINIO>
  ```
- Puertos **80 y 443** abiertos en el firewall de Windows:
  ```powershell
  New-NetFirewallRule -DisplayName "HTTP"  -Direction Inbound -Protocol TCP -LocalPort 80  -Action Allow
  New-NetFirewallRule -DisplayName "HTTPS" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow
  ```
- Módulos de Apache habilitados en `E:\laragon\bin\apache\<version>\conf\httpd.conf` (sin `#`):
  ```apache
  LoadModule proxy_module modules/mod_proxy.so
  LoadModule proxy_http_module modules/mod_proxy_http.so
  LoadModule proxy_wstunnel_module modules/mod_proxy_wstunnel.so
  LoadModule ssl_module modules/mod_ssl.so
  LoadModule headers_module modules/mod_headers.so
  LoadModule rewrite_module modules/mod_rewrite.so
  ```

---

## 2. Configurar el `.env.prod` (dentro del proyecto)

En `<PROYECTO>\wms-backend\.env.prod`. **Lo crítico:** los hosts deben ser los **nombres de servicio** de Docker, NO `localhost`.

```dotenv
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO

SECRET_KEY=<genera: openssl rand -hex 32>

POSTGRES_USER=wms_user
POSTGRES_PASSWORD=<contraseña fuerte>
POSTGRES_DB=wms_db
DATABASE_URL=postgresql+asyncpg://wms_user:<contraseña>@postgres:5432/wms_db
DATABASE_SYNC_URL=postgresql+psycopg2://wms_user:<contraseña>@postgres:5432/wms_db

REDIS_PASSWORD=<contraseña fuerte>
REDIS_URL=redis://:<contraseña>@redis:6379/0

MEILI_MASTER_KEY=<contraseña fuerte>
MEILI_URL=http://meilisearch:7700

DOMAIN=<DOMINIO>
CORS_ORIGINS=["https://<DOMINIO>"]

SUPERADMIN_EMAIL=admin@gs1pa.org
SUPERADMIN_PASSWORD=<contraseña fuerte, mín 8>
```

> Si cambias `POSTGRES_PASSWORD` cuando el volumen ya existe, la BD conserva la clave vieja: habría que recrear el volumen o cambiarla con `ALTER USER` dentro de `psql`.

---

## 3. Levantar los contenedores (stack esencial)

Desde `<PROYECTO>` en PowerShell. **Siempre con `--env-file`** (si no, las contraseñas quedan en blanco):

```powershell
cd <PROYECTO>

docker compose --env-file wms-backend\.env.prod -f docker-compose.prod.yml build

docker compose --env-file wms-backend\.env.prod -f docker-compose.prod.yml up -d `
  postgres redis meilisearch api celery-worker celery-beat nginx pgbackup

docker compose --env-file wms-backend\.env.prod -f docker-compose.prod.yml ps
```

Sembrar permisos/roles/superadmin (la carpeta `seeds/` no está en la imagen, se monta):

```powershell
docker compose --env-file wms-backend\.env.prod -f docker-compose.prod.yml run --rm `
  -v "${PWD}\wms-backend\seeds:/app/seeds" api python -m seeds.run_all
```

Verificar:
```powershell
curl.exe http://localhost:<PUERTO_INTERNO>/api/v1/health/live
```
Debe devolver `{"status":"alive",...}`.

---

## 4. Certificado con win-acme (paso a paso, respuestas exactas)

Ejecuta `wacs.exe` **como administrador** (descárgalo de win-acme.com, p. ej. en `E:\win-acme`).

| Prompt del asistente | Qué elegir |
|---|---|
| Menú principal | `M` → *Create certificate (full options)* |
| Fuente del certificado | Opción de **entrada manual** de host |
| Host | `<DOMINIO>` |
| `Friendly name '[Manual] ...'` | **Enter** (aceptar el nombre por defecto) |
| Convertir en múltiples certificados | `4` → **Single certificate** |
| Validación | **[http-01] Save verification files on (network) path** |
| `Path` (webroot) | `E:\laragon\www\acme` |
| `Copy default web.config before validation?` | `n` (es solo para IIS) |
| Tipo de llave (CSR) | `2` → **RSA key** |
| Almacén del certificado | **PEM encoded files (Apache, nginx, etc.)** |
| `File path` | `E:\certs` |
| Password del `.pem` | `1` → **None** (si no, Apache la pediría al arrancar) |
| `store it in another way too?` | `5` → **No (additional) store steps** |
| Paso de instalación | `3` → **No (additional) installation steps** |
| `Open in default application?` (ToS) | `n` |
| `Do you agree to the terms?` | `y` |
| Email de avisos | uno real (ej. `admin@gs1pa.org`) |
| `specify the user the task will run as?` | `n` (correrá como SYSTEM) |

**Requisito para que valide:** el vhost `:80` del dominio (paso 5) debe estar activo y sirviendo `E:\laragon\www\acme`, y el dominio debe resolver a este servidor.

Al terminar, en `E:\certs` quedan:
- `<DOMINIO>-chain.pem` (certificado + cadena)
- `<DOMINIO>-key.pem` (clave privada)

win-acme crea además una **tarea programada** de renovación automática (cada ~60 días).

Verifica:
```powershell
dir E:\certs\<DOMINIO>*
```

---

## 5. Vhost de Laragon (plantilla por dominio)

Crea `E:\laragon\etc\apache2\sites-enabled\<DOMINIO>.conf`.

> Primero crea la carpeta de validación (una sola vez, sirve para todos los dominios):
> ```powershell
> mkdir E:\laragon\www\acme
> ```

**Para emitir el certificado**, basta el bloque `:80`. **Después** de tener el `.pem`, añade el bloque `:443`.

```apache
# ── Puerto 80: validación ACME + redirección a HTTPS ──
<VirtualHost *:80>
    ServerName <DOMINIO>
    DocumentRoot "E:/laragon/www/acme"
    <Directory "E:/laragon/www/acme">
        Require all granted
    </Directory>
    RewriteEngine On
    RewriteCond %{REQUEST_URI} !^/\.well-known/acme-challenge/
    RewriteRule ^ https://%{HTTP_HOST}%{REQUEST_URI} [R=301,L]
</VirtualHost>

# ── Puerto 443: SSL + reverse proxy al contenedor ──
<VirtualHost *:443>
    ServerName <DOMINIO>

    SSLEngine on
    SSLCertificateFile    "E:/certs/<DOMINIO>-chain.pem"
    SSLCertificateKeyFile "E:/certs/<DOMINIO>-key.pem"

    ProxyPreserveHost On
    RequestHeader set X-Forwarded-Proto "https"

    # WebSocket (/ws/)
    RewriteEngine On
    RewriteCond %{HTTP:Upgrade} =websocket [NC]
    RewriteRule ^/(.*)$ ws://127.0.0.1:<PUERTO_INTERNO>/$1 [P,L]

    # Todo el tráfico al Nginx del contenedor (sirve front + /api)
    ProxyPass        / http://127.0.0.1:<PUERTO_INTERNO>/
    ProxyPassReverse / http://127.0.0.1:<PUERTO_INTERNO>/
</VirtualHost>
```

Recarga: **Laragon → Menu → Apache → Reload**.

Prueba final:
```powershell
curl.exe https://<DOMINIO>/api/v1/health/live
```

---

## 6. Proceso de ACTUALIZACIÓN (código nuevo, conservando datos)

Cuando hay módulos o migraciones nuevas. **Nunca uses `down -v`** (borra los datos).

```powershell
cd <PROYECTO>

# 0. Backup de la BD antes de nada
docker compose --env-file wms-backend\.env.prod -f docker-compose.prod.yml exec postgres `
  pg_dump -U wms_user -d wms_db -Fc -f /tmp/backup.dump
docker compose --env-file wms-backend\.env.prod -f docker-compose.prod.yml cp postgres:/tmp/backup.dump .\backup.dump

# 1. Traer código nuevo
git pull

# 2. Reconstruir imágenes
docker compose --env-file wms-backend\.env.prod -f docker-compose.prod.yml build api celery-worker celery-beat

# 3. Recompilar frontend si cambió
docker run --rm -v "${PWD}\wms-frontend:/app" -w /app node:20-alpine sh -c "npm ci && npm run build"

# 4. Recrear (alembic aplica migraciones nuevas solo, sin borrar datos)
docker compose --env-file wms-backend\.env.prod -f docker-compose.prod.yml up -d `
  postgres redis meilisearch api celery-worker celery-beat nginx pgbackup

# 5. Re-sembrar permisos nuevos (idempotente)
docker compose --env-file wms-backend\.env.prod -f docker-compose.prod.yml run --rm `
  -v "${PWD}\wms-backend\seeds:/app/seeds" api python -m seeds.run_all

# 6. Reiniciar nginx para que re-resuelva la IP del api
docker compose --env-file wms-backend\.env.prod -f docker-compose.prod.yml restart nginx
```

---

## 7. Traer datos desde otra BD/servidor

```powershell
# A. Backup del destino actual (seguridad)
docker compose --env-file wms-backend\.env.prod -f docker-compose.prod.yml exec postgres `
  pg_dump -U wms_user -d wms_db -Fc -f /tmp/antes.dump
docker compose --env-file wms-backend\.env.prod -f docker-compose.prod.yml cp postgres:/tmp/antes.dump .\antes.dump

# B. Exportar del ORIGEN
#   - Si es contenedor:   docker exec <orig> pg_dump -U <user> -d <db> -Fc -f /tmp/origen.dump ; docker cp <orig>:/tmp/origen.dump .\origen.dump
#   - Si es otro servidor: pg_dump -h <IP> -p <puerto> -U <user> -d <db> -Fc -f origen.dump

# C. Restaurar en el destino (reemplaza datos existentes)
docker compose --env-file wms-backend\.env.prod -f docker-compose.prod.yml cp .\origen.dump postgres:/tmp/origen.dump
docker compose --env-file wms-backend\.env.prod -f docker-compose.prod.yml exec postgres `
  pg_restore -U wms_user -d wms_db --no-owner --clean --if-exists /tmp/origen.dump

# D. Arrancar api (alembic aplica migraciones faltantes)
docker compose --env-file wms-backend\.env.prod -f docker-compose.prod.yml up -d api
```

Requisitos: origen del **mismo sistema** (mismo esquema), PostgreSQL del origen **≤ 16**.

---

## 8. Problemas frecuentes (y cómo se resolvieron)

| Síntoma | Causa | Solución |
|---|---|---|
| `api` en `Restarting`, no conecta a BD | `DATABASE_URL`/`REDIS_URL`/`MEILI_URL` apuntan a `localhost` | Usar nombres de servicio: `@postgres`, `@redis`, `meilisearch` |
| Warnings `POSTGRES_PASSWORD ... not set` | Falta `--env-file` | Añadir `--env-file wms-backend\.env.prod` a cada comando compose |
| `ModuleNotFoundError: No module named 'app'` (alembic) | `alembic` no agrega `/app` al path | Comando api: `PYTHONPATH=/app python -m alembic upgrade head && ...` |
| `celery-beat`: `Permission denied: 'celerybeat-schedule'` | Usuario no-root no puede escribir en `/app` | Comando beat: `... beat --schedule /tmp/celerybeat-schedule` |
| `No module named 'seeds'` | La imagen no incluye `seeds/` | Montar: `run --rm -v "${PWD}\wms-backend\seeds:/app/seeds" api python -m seeds.run_all` (o `COPY seeds/ ./seeds/` en el Dockerfile) |
| `502 Bad Gateway` por Nginx | Nginx cacheó la IP vieja del `api` tras recrearlo | `docker compose ... restart nginx` (o resolver dinámico en `nginx.laragon.conf`) |
| Certbot/win-acme 404 en validación | Otro web server (Laragon) atiende el 80 | Usar Laragon como reverse proxy + win-acme (este runbook) |
| `(unhealthy)` en celery | Heredan el healthcheck del Dockerfile (curl a :8000) | Cosmético; opcional `healthcheck: disable: true` en celery |

---

## 9. Checklist para un dominio NUEVO (ej. TMS)

- [ ] DNS A de `<DOMINIO>` → IP del servidor (`nslookup`).
- [ ] Proyecto con su `.env.prod` (hosts = nombres de servicio, `DOMAIN`/`CORS_ORIGINS` con el dominio nuevo).
- [ ] Puerto interno distinto al de otras apps (ej. `8081`).
- [ ] `docker compose ... up -d` + seed; `curl http://localhost:<PUERTO_INTERNO>/api/v1/health/live` OK.
- [ ] Vhost `:80` creado y Apache recargado.
- [ ] win-acme (tabla del paso 4) → certificado en `E:\certs`.
- [ ] Añadir vhost `:443` con las rutas del `.pem`; recargar Apache.
- [ ] `curl https://<DOMINIO>/api/v1/health/live` OK con candado válido.
