<#
  WMS Panamá — Actualización en producción (código + migraciones) en un solo comando.
  Uso (PowerShell):
      .\scripts\deploy.ps1                 # rama main
      .\scripts\deploy.ps1 -Rama otra-rama
      .\scripts\deploy.ps1 -SinBackup      # no recomendado
  Las migraciones (alembic upgrade head) las aplica el contenedor api al arrancar.
  Automatiza la sección 6 del RUNBOOK_Despliegue_y_Certificado.md.
#>
param(
  [string]$Rama = "main",
  [switch]$SinBackup
)
$ErrorActionPreference = "Stop"
$raiz = Split-Path $PSScriptRoot -Parent
Set-Location $raiz
$dc = @("compose", "--env-file", "wms-backend\.env.prod", "-f", "docker-compose.prod.yml")
$servicios = @("postgres", "redis", "meilisearch", "api", "celery-worker", "celery-beat", "nginx", "pgbackup")

function Paso($texto) { Write-Host "`n==> $texto" -ForegroundColor Cyan }
function Ejecutar([string[]]$argumentos) {
  & docker @argumentos
  if ($LASTEXITCODE -ne 0) { throw "Falló: docker $($argumentos -join ' ')" }
}

if (-not (Test-Path "wms-backend\.env.prod")) { throw "Falta wms-backend\.env.prod" }

# 1. Backup de la BD
if (-not $SinBackup) {
  Paso "Backup de la base de datos"
  New-Item -ItemType Directory -Force "backups" | Out-Null
  $archivo = "backups\wms_predeploy_$(Get-Date -Format 'yyyyMMdd_HHmmss').dump"
  Ejecutar ($dc + @("exec", "-T", "postgres", "sh", "-c", 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/deploy.dump'))
  Ejecutar ($dc + @("cp", "postgres:/tmp/deploy.dump", $archivo))
  Write-Host "Backup: $archivo"
}

# 2. Código nuevo
Paso "Actualizando código ($Rama)"
git fetch origin
git checkout $Rama
git pull --ff-only origin $Rama
if ($LASTEXITCODE -ne 0) { throw "git pull falló (¿cambios locales en el servidor?)" }

# 3. Frontend (dist/ no está en git: se compila aquí con Node en contenedor)
Paso "Compilando frontend"
Ejecutar @("run", "--rm", "-v", "${raiz}\wms-frontend:/app", "-w", "/app", "node:20-alpine", "sh", "-c", "npm ci && npm run build")

# 4. Imágenes del backend
Paso "Construyendo imágenes"
Ejecutar ($dc + @("build", "api", "celery-worker", "celery-beat"))

# 5. Recrear (alembic upgrade head corre al arrancar el api)
Paso "Recreando contenedores"
Ejecutar ($dc + @("up", "-d") + $servicios)

# 6. Permisos/roles nuevos (idempotente)
Paso "Sembrando permisos y roles"
Ejecutar ($dc + @("run", "--rm", "-v", "${raiz}\wms-backend\seeds:/app/seeds", "api", "python", "-m", "seeds.run_all"))

# 7. Nginx re-resuelve la IP del api recreado (evita 502)
Ejecutar ($dc + @("restart", "nginx"))

# 8. Verificación
Paso "Esperando a que el API esté sano"
$ok = $false
for ($i = 0; $i -lt 30; $i++) {
  try { Invoke-WebRequest "http://127.0.0.1:8080/api/v1/health/live" -UseBasicParsing -TimeoutSec 5 | Out-Null; $ok = $true; break }
  catch { Start-Sleep 5 }
}
& docker @($dc + @("ps"))
if ($ok) { Write-Host "`nWMS desplegado correctamente." -ForegroundColor Green }
else {
  Write-Host "`nEl API no respondió. Revisa: docker $($dc -join ' ') logs --tail 100 api" -ForegroundColor Red
  exit 1
}
