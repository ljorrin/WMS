# Guía de Despliegue — WMS Panamá en Windows Server 2022 Standard

Despliegue **de producción** con **Docker Engine en WSL2** (contenedores Linux, sin salir de Windows Server), acceso por **dominio público con HTTPS real** y **stack esencial** (API, workers Celery, PostgreSQL, Redis, Meilisearch, Nginx y backups). Sin Prometheus/Grafana.

> **Restricción crítica de disco:** C: tiene solo ~5 GB libres. Toda la instalación (distro Linux, datos de Docker, imágenes, volúmenes, BD y código) debe vivir en **D:** (~150 GB). Esta guía está diseñada para **no llenar C:**.
>
> **Por qué Docker Engine y no Docker Desktop:** Docker Desktop no arranca como servicio (necesita sesión iniciada), tiene licencia de pago para empresas grandes y guarda datos en C: por defecto. Aquí usamos **Docker Engine dentro de WSL2**: corre el daemon como servicio, arranca al boot y no requiere licencia.

---

## 1. Requisitos

### Hardware (mínimo → recomendado)
| Recurso | Mínimo | Recomendado |
|---|---|---|
| CPU | 4 vCPU | 8 vCPU |
| RAM | 8 GB | 16 GB |
| Disco **en D:** | 60 GB | 150 GB (tienes) ✅ |
| Disco en C: | — | mantener ≥3 GB libres |

### Software
- Windows Server 2022 Standard actualizado, con **virtualización habilitada** (BIOS/hipervisor; en VM activar "nested virtualization").
- **WSL2** (Windows Subsystem for Linux 2).
- **Ubuntu Server 22.04** (sistema donde correrán los contenedores).
- **Docker Engine + Docker Compose v2** (se instalan dentro de Ubuntu).
- **Git**.

### Red / dominio
- Dominio (ej. `wms.tuempresa.pa`) con registro **A** a la IP pública del servidor.
- Puertos **80 y 443** abiertos (firewall Windows + perimetral).
- Salida a Internet para descargar imágenes y validar el certificado.

### Arquitectura de contenedores
```
Internet ─▶ 443/80 ─▶ [nginx] (SSL + sirve frontend)
                         ├─▶ [api] FastAPI (Uvicorn ×4)
             ┌───────────┼──────┬───────────┐
             ▼           ▼      ▼           ▼
       [postgres]     [redis] [meilisearch]
             ▲           ▲
   [celery-worker]───────┤   [celery-beat]───┘   [pgbackup] ─▶ backups diarios
```

---

## 2. Habilitar WSL2 (uso mínimo de C:)

PowerShell **como Administrador**:
```powershell
wsl --install --no-distribution
wsl --update
wsl --set-default-version 2
```
Reinicia si lo pide. Esto instala solo la plataforma WSL (unos cientos de MB en C:).

---

## 3. Instalar Ubuntu y MOVERLO a D: (paso clave para no llenar C:)

Por defecto la distro se instala en C:. La instalamos y la movemos a D: **de inmediato**, antes de descargar nada pesado.

```powershell
# 1) Instala Ubuntu (usa ~1.5 GB temporales en C: — cabe en tus 5 GB)
wsl --install -d Ubuntu-22.04
```
Cuando abra la consola de Ubuntu, crea tu usuario y contraseña. Luego, de vuelta en PowerShell:

```powershell
# 2) Apaga WSL y mueve TODO el almacenamiento de la distro a D:
wsl --shutdown
mkdir D:\WSL
wsl --manage Ubuntu-22.04 --move D:\WSL\Ubuntu-22.04
```
Desde ahora, la distro **y todos los datos de Docker** (que viven dentro de ella) crecen en **D:**, no en C:.

> **Alternativa cero-C::** si no quieres ni el uso temporal en C:, descarga el rootfs de Ubuntu WSL a D: e impórtalo directo:
> ```powershell
> wsl --import Ubuntu-22.04 D:\WSL\Ubuntu-22.04 D:\WSL\ubuntu-rootfs.tar.gz
> ```

---

## 4. Limitar recursos y sacar el swap de C:

Crea `C:\Users\<tu-usuario>\.wslconfig` (archivo diminuto) con:
```ini
[wsl2]
memory=12GB
processors=6
swap=8GB
swapFile=D:\\WSL\\swap.vhdx
```
Aplica con `wsl --shutdown` y reabrir Ubuntu. Esto evita que el swap de WSL ocupe C:.

---

## 5. Activar systemd (para que Docker corra como servicio)

Dentro de **Ubuntu**, edita `/etc/wsl.conf`:
```bash
sudo tee /etc/wsl.conf >/dev/null <<'EOF'
[boot]
systemd=true
EOF
```
Cierra la terminal, ejecuta `wsl --shutdown` en PowerShell y reabre Ubuntu.

---

## 6. Instalar Docker Engine

Dentro de Ubuntu:
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
sudo systemctl enable --now docker
# cierra y reabre la terminal para aplicar el grupo docker
docker version
docker compose version
```
Como la distro está en D:, `/var/lib/docker` (imágenes, volúmenes, BD) **ya reside en D:** automáticamente.

---

## 7. Obtener el código en D:

Dentro de Ubuntu, clona en el **sistema de archivos nativo de Linux** (rápido y ya está en D:):
```bash
mkdir -p ~/WMS && cd ~/WMS
git clone https://github.com/ljorrin/WMS.git .
git checkout feature/inbound-module
```
> Puedes editar estos archivos desde Windows en `\\wsl$\Ubuntu-22.04\home\<usuario>\WMS`. Evita clonar en `/mnt/d/...`: el I/O de bind-mount es lento para Docker.

---

## 8. Correcciones del compose (ya aplicadas en el repo)

Estas tres correcciones ya están hechas en el repositorio; solo verifica que las tengas tras el `git clone`:

1. **Módulo Celery:** `celery-worker` y `celery-beat` usan `-A app.tasks.celery_app` (no `app.celery_app`).
2. **`scripts/postgres/init.sql`** existe (habilita extensiones `pgcrypto` y `pg_trgm`).
3. **Nginx** sin el bloque `location /grafana/` (evita que Nginx no arranque por el host `grafana` inexistente).

---

## 9. Variables de entorno (`.env.prod`)

`wms-backend/.env.prod` trae placeholders. Genera secretos fuertes:
```bash
openssl rand -hex 32   # ejecútalo para SECRET_KEY, POSTGRES_PASSWORD, REDIS_PASSWORD, MEILI_MASTER_KEY
```
Fija (coherente con los nombres de servicio `postgres`, `redis`, `meilisearch`):
```dotenv
ENVIRONMENT=production
DEBUG=false

POSTGRES_DB=wmsdb
POSTGRES_USER=wms
POSTGRES_PASSWORD=<secreto>
DATABASE_URL=postgresql+asyncpg://wms:<secreto>@postgres:5432/wmsdb
DATABASE_SYNC_URL=postgresql+psycopg2://wms:<secreto>@postgres:5432/wmsdb

REDIS_PASSWORD=<secreto>
REDIS_URL=redis://:<secreto>@redis:6379/0

MEILI_MASTER_KEY=<secreto>
MEILI_URL=http://meilisearch:7700

SECRET_KEY=<secreto>

DOMAIN=wms.tuempresa.pa
CORS_ORIGINS=https://wms.tuempresa.pa

SUPERADMIN_EMAIL=admin@tuempresa.pa
SUPERADMIN_PASSWORD=<password_fuerte>

SMTP_HOST=smtp.tuempresa.pa
SMTP_PORT=587
SMTP_TLS=true
EMAIL_FROM=wms@tuempresa.pa
```
> El `.env.prod` tiene secretos: confirma que esté en `.gitignore` y nunca lo subas al repo.

---

## 10. Certificado SSL (HTTPS real)

Nginx espera en `~/WMS/nginx/ssl/`:
- `fullchain.pem` (certificado + cadena)
- `privkey.pem` (clave privada)

Y en `nginx/nginx.prod.conf` cambia `server_name wms.tuempresa.pa;` por **tu dominio**.

**Opción A — Let's Encrypt (gratis).** Desde Ubuntu, con el dominio ya apuntando al servidor y Nginx aún sin levantar:
```bash
sudo apt-get update && sudo apt-get install -y certbot
sudo certbot certonly --standalone -d wms.tuempresa.pa
sudo cp /etc/letsencrypt/live/wms.tuempresa.pa/fullchain.pem ~/WMS/nginx/ssl/
sudo cp /etc/letsencrypt/live/wms.tuempresa.pa/privkey.pem  ~/WMS/nginx/ssl/
```
Programa la renovación (cron) y recarga Nginx tras renovar:
```bash
docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

**Opción B — Certificado comprado.** Une certificado + intermedios en `fullchain.pem`, coloca la clave en `privkey.pem`, cópialos a `nginx/ssl/`.

---

## 11. Compilar el frontend

El cliente usa por defecto la ruta relativa `/api/v1` (Nginx la enruta al backend), así que **no** necesitas `VITE_API_URL`. Compila con un contenedor Node:
```bash
cd ~/WMS
docker run --rm -v "$PWD/wms-frontend":/app -w /app node:20-alpine sh -c "npm ci && npm run build"
```
Esto regenera `wms-frontend/dist`, que Nginx sirve.

---

## 12. Levantar el stack esencial

```bash
cd ~/WMS
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d \
  postgres redis meilisearch api celery-worker celery-beat nginx pgbackup
docker compose -f docker-compose.prod.yml ps   # todo debe quedar "healthy"
```
El servicio `api` corre `alembic upgrade head` (migraciones) automáticamente al arrancar.

---

## 13. Sembrar datos iniciales

Las migraciones crean el esquema pero **no** siembran permisos/roles/superadmin:
```bash
docker compose -f docker-compose.prod.yml exec api python -m seeds.run_all
```
> Los permisos de Outbound e IA ya fueron reconciliados en `seeds/run_all.py`, así que esos módulos no darán 403 a roles no-superadmin.

---

## 14. Verificación

```bash
docker compose -f docker-compose.prod.yml exec api curl -f http://localhost:8000/api/v1/health/live
# Desde fuera:
#   https://wms.tuempresa.pa/api/docs  → OpenAPI
#   https://wms.tuempresa.pa/          → frontend
docker compose -f docker-compose.prod.yml logs -f api    # si algo falla
```
Prueba login con el superadmin y recorre un flujo (PO→recepción o una SO).

---

## 15. Firewall (en Windows Server)

```powershell
New-NetFirewallRule -DisplayName "WMS HTTP"  -Direction Inbound -Protocol TCP -LocalPort 80  -Action Allow
New-NetFirewallRule -DisplayName "WMS HTTPS" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow
```
En instalaciones WSL2 recientes el reenvío de 80/443 del host a la distro funciona directo; **verifícalo con una prueba externa**. Si no, ajústalo con `netsh interface portproxy`. No publiques 5432/6379/7700/8000 (el compose de producción solo expone Nginx).

---

## 16. Arranque automático tras reiniciar el servidor (clave en producción)

Con systemd activo (paso 5), Docker y los contenedores (`restart: unless-stopped`) vuelven solos **cuando la distro arranca**. Para que la distro WSL arranque al encender el servidor **sin necesidad de iniciar sesión**, crea una tarea programada:

```powershell
$action  = New-ScheduledTaskAction -Execute "wsl.exe" -Argument "-d Ubuntu-22.04 -u root -e /bin/true"
$trigger = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName "WSL-WMS-Boot" -Action $action -Trigger $trigger `
  -User "SYSTEM" -RunLevel Highest
```
Al bootear, la tarea "despierta" la distro; systemd inicia Docker y los contenedores se levantan solos.

---

## 17. Backups

`pgbackup` hace backup diario de PostgreSQL en `~/WMS/backups` (retención 7 días / 4 semanas / 6 meses).
- Verifica que se generen archivos ahí.
- **Copia los backups fuera del servidor** (unidad de red / nube) periódicamente.
- Restauración de ejemplo:
  ```bash
  docker compose -f docker-compose.prod.yml exec -T postgres psql -U wms -d wmsdb < backup.sql
  ```

---

## Operación diaria (chuleta)

```bash
cd ~/WMS
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f api
docker compose -f docker-compose.prod.yml restart api

# Actualizar versión:
git pull
docker run --rm -v "$PWD/wms-frontend":/app -w /app node:20-alpine sh -c "npm ci && npm run build"
docker compose -f docker-compose.prod.yml build api celery-worker celery-beat
docker compose -f docker-compose.prod.yml up -d api celery-worker celery-beat nginx
```

**Vigilar espacio en D::**
```bash
df -h /            # uso dentro de la distro
docker system df   # uso por imágenes/volúmenes
docker system prune -f   # limpia capas/imágenes sin usar (con cuidado)
```

---

## Checklist final

- [ ] WSL2 instalado **y distro movida a `D:\WSL\`**.
- [ ] `.wslconfig` con swap en D:.
- [ ] systemd activo y Docker Engine como servicio (`systemctl enable docker`).
- [ ] Verificado que C: no crece: `/var/lib/docker` vive en D:.
- [ ] Repo clonado en `~/WMS`, rama correcta.
- [ ] Correcciones del compose presentes (Celery, `init.sql`, sin Grafana).
- [ ] `.env.prod` con secretos reales; `DOMAIN`/`CORS_ORIGINS` con tu dominio.
- [ ] DNS (registro A) al servidor; puertos 80/443 abiertos.
- [ ] Certificado en `nginx/ssl/`; `server_name` = tu dominio.
- [ ] Frontend compilado (`wms-frontend/dist`).
- [ ] Stack esencial `healthy`; seed ejecutado; login OK.
- [ ] Tarea de arranque automático configurada (paso 16).
- [ ] Backups en `~/WMS/backups` y copiados fuera del servidor.
