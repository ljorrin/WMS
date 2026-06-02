# Guía de habilitación Git + GitHub en macOS (para publicar el WMS)

**Repositorio:** `https://github.com/ljorrin/WMS.git` · **Cuenta:** `ljorrin` · **Rama de trabajo:** `feature/inbound-module`
**SO:** macOS (Apple Silicon o Intel). Todos los comandos son para la app **Terminal** de macOS.

---

## ⚠️ Aclaración técnica imprescindible (léela primero)

Cowork se ejecuta en una **VM Linux aislada (sandbox)** que solo "ve" tu carpeta del proyecto montada por FUSE. Esa VM **no comparte** ni el **Keychain de macOS** ni el `gh` que instales en tu Mac ni tus variables de entorno de macOS.

Consecuencia práctica:

- Instalar y autenticar `gh` **en tu Mac** te habilita a **ti** para publicar (y es necesario para generar el token). **Recomendado y más seguro.**
- Para que **yo (en el sandbox)** publique de forma autónoma, el **token debe estar disponible dentro de la sesión del sandbox** (no basta el Keychain de macOS) **y** debes **aprobar el permiso de borrado** del directorio (para que Git pueda quitar `.git/index.lock`). Más abajo detallo ambas vías y sus riesgos.

Por eso esta guía cubre las dos cosas: (1) dejar tu Mac listo para publicar tú mismo, y (2) qué hace falta exactamente si quieres delegarme la publicación en el sandbox.

---

## 1. GitHub CLI (`gh`) en macOS

1. **URL oficial:** https://cli.github.com  (releases: https://github.com/cli/cli/releases)
2. **Método recomendado:** Homebrew.
3. **Comandos exactos:**
   ```bash
   # Si no tienes Homebrew:
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   # (Apple Silicon) añade brew al PATH si el instalador lo pide:
   echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile && eval "$(/opt/homebrew/bin/brew shellenv)"

   # Instalar GitHub CLI:
   brew install gh
   ```
   Alternativas sin Homebrew: descargar el `.pkg` desde los releases oficiales, o `sudo port install gh` (MacPorts).
4. **Verificar instalación:**
   ```bash
   gh --version        # debe imprimir "gh version x.y.z"
   which gh            # /opt/homebrew/bin/gh (Apple Silicon) o /usr/local/bin/gh (Intel)
   ```

---

## 2. Autenticación con GitHub

1. **Método recomendado:** `gh auth login` (gestiona el token y configura Git por ti).
   ```bash
   gh auth login
   # Elige:  GitHub.com  →  HTTPS  →  "Login with a web browser" (o "Paste an authentication token")
   gh auth setup-git    # hace que Git use gh como credential helper
   ```
2. **Permisos mínimos requeridos:**
   - **Fine-grained PAT (recomendado, mínimo alcance):** Repository access = **solo `ljorrin/WMS`**; Permissions → **Contents: Read and write**, **Pull requests: Read and write**, **Metadata: Read-only** (obligatorio).
   - **Si usas el flujo web de `gh`:** solicitará los scopes `repo`, `read:org` y `workflow` (clásicos). Es válido pero más amplio que el fine-grained.
3. **Cómo generar el token (si usas PAT en vez del flujo web):**
   GitHub → tu avatar → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens** → **Generate new token** → elige repo `WMS`, los permisos del punto 2, una **caducidad corta** (p. ej. 7 días) → **Generate** y copia el token (empieza por `github_pat_…`).
4. **Dónde se configura en macOS:**
   - Con `gh auth login`: el token queda en el **Keychain de macOS** y `gh auth setup-git` deja el credential helper de Git apuntando a `gh`.
   - Para Git "puro": `git config --global credential.helper osxkeychain` (helper nativo de macOS; guarda en Keychain, no en texto plano).
5. **Verificar que la autenticación funciona:**
   ```bash
   gh auth status      # "✓ Logged in to github.com as ljorrin"
   ```
6. **Verificar acceso de ESCRITURA al repo:**
   ```bash
   gh repo view ljorrin/WMS --json viewerPermission -q .viewerPermission
   # Debe devolver  WRITE  o  ADMIN  (READ = no podrías hacer push)
   # Alternativa con Git, sin publicar nada:
   git -C <ruta-al-WMS> push --dry-run origin feature/inbound-module
   ```

---

## 3. Git en macOS

1. **¿Instalado?**
   ```bash
   git --version        # si falta: xcode-select --install   (o brew install git)
   ```
2. **Configuración de usuario** (debe coincidir con la identidad del repo: `Alejo / aguevarar@gmail.com`):
   ```bash
   git config --global user.name      # si vacío:
   git config --global user.name  "Alejo"
   git config --global user.email     # si vacío:
   git config --global user.email "aguevarar@gmail.com"
   ```
3. **Configuración de credenciales:**
   ```bash
   git config --global credential.helper   # esperado: osxkeychain  o  "!/opt/homebrew/bin/gh auth git-credential"
   ```
4. **Acceso al remoto:**
   ```bash
   cd <ruta-al-WMS>
   git remote -v                                   # origin https://github.com/ljorrin/WMS.git
   git ls-remote origin >/dev/null && echo "remoto OK"
   ```

---

## 4. Permisos del entorno (sandbox) — protocolo que seguiré

Cuando vaya a commitear dentro del sandbox, Git necesita borrar/renombrar dentro de `.git` (p. ej. quitar `.git/index.lock`). Ese borrado está bloqueado por la capa de permisos de Cowork. Por eso:

- **Qué permiso solicitaré:** `allow_cowork_file_delete` para `…/mnt/WMS/.git/index.lock` (y, si hace falta, para limpiar archivos de prueba sueltos en el directorio).
- **Cuándo lo solicitaré:** justo **antes del primer `git add`/`commit`** de la sesión de publicación.
- **Cómo verificaré que se concedió:**
  ```bash
  rm -f .git/index.lock && echo "lock eliminado OK"   # exit 0 = permiso concedido
  ```
  Si sigue dando `Operation not permitted`, el permiso no se aplicó y me detendré a avisarte.

---

## 5. Checklist de validación (entorno listo para publicar)

Marca cada ítem; todos deben pasar:

```bash
# — Git —
git --version                                   # ✔ imprime versión
git config --global user.name                   # ✔ no vacío
git config --global user.email                  # ✔ no vacío
git config --global credential.helper           # ✔ osxkeychain o gh

# — GitHub CLI / Auth —
gh --version                                    # ✔ instalado
gh auth status                                  # ✔ "Logged in ... as ljorrin"
gh repo view ljorrin/WMS --json viewerPermission -q .viewerPermission   # ✔ WRITE o ADMIN

# — Repo / remoto —
cd <ruta-al-WMS>
git remote -v                                   # ✔ origin = ljorrin/WMS
git ls-remote origin >/dev/null && echo OK      # ✔ acceso de lectura
git push --dry-run origin feature/inbound-module# ✔ sin error de autenticación

# — Sandbox (cuando publique yo) —
rm -f .git/index.lock && echo lock-OK           # ✔ borrado permitido (tras aprobar el permiso)
```

Si los 4 grupos pasan, el entorno permite: `git add`, `git commit`, `git push` y creación de PR.

---

## 6. Resultado esperado — qué debes hacer en macOS

### Opción A (recomendada y más segura): publicas tú desde tu Mac
1. `brew install gh && gh auth login && gh auth setup-git`
2. `cd <ruta-al-WMS>` y aplica el parche que ya generé:
   ```bash
   git checkout -b feature/inbound-module        # si no existe
   git apply inbound_changes.patch
   ```
3. Commits, push y PR:
   ```bash
   git add -A
   git commit -m "feat(inbound): estabilización backend + gestión de Órdenes de Compra"
   git push -u origin feature/inbound-module
   gh pr create --base main --head feature/inbound-module \
     --title "Inbound: estabilización + Órdenes de Compra" \
     --body "Ver docs/INBOUND_Analisis_y_Plan.md y docs/INBOUND_Validacion_Tecnica.md"
   ```
   → No me das ninguna credencial. Cero riesgo de filtración.

### Opción B: que yo publique automáticamente desde el sandbox
Para que en la próxima ejecución yo haga commit + push + PR + gestión de ramas **sin intervención manual**, necesito **las tres cosas** a la vez:
1. **Permiso de borrado** en `WMS`: aprobar mi solicitud `allow_cowork_file_delete` (te la pediré al iniciar la publicación).
2. **Token disponible dentro de la sesión del sandbox** (el Keychain de macOS NO llega al sandbox). En la práctica esto significa exponer un **PAT fine-grained** como variable de entorno de la sesión de Cowork (p. ej. `GITHUB_TOKEN`). Si Cowork no permite inyectar variables a la sesión, esta opción no es posible y habría que ir por la Opción A.
3. **Tooling de PR:** que yo pueda instalar `gh` en el sandbox (lo intento con su gestor de paquetes) **o** usar la API REST con el PAT.

Con (1)+(2)+(3), yo ejecutaría:
```bash
rm -f .git/index.lock
git remote set-url origin "https://x-access-token:${GITHUB_TOKEN}@github.com/ljorrin/WMS.git"
git add -A && git commit -m "..."         # o varios commits por área
git push -u origin feature/inbound-module
gh pr create --base main --head feature/inbound-module --title "..." --body "..."
# (o vía API: curl -X POST -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/repos/ljorrin/WMS/pulls -d '{...}')
```

### Riesgos de seguridad y mi política
- Un **PAT con escritura** es un secreto: úsalo **fine-grained**, solo sobre `WMS`, con **caducidad corta**, y **revócalo** al terminar.
- **No pegues el token en el chat.** Por mis reglas de operación **no introduzco tokens/contraseñas manualmente** ni hago push/PR sin tu confirmación explícita por acción. En la Opción B tú cargas el token en el entorno; yo solo invoco los comandos que lo leen.
- Exponer un token como variable de entorno de sesión es menos seguro que el Keychain de macOS: por eso la **Opción A es la preferible** salvo que realmente quieras delegar la publicación.

---

## 7. Recordatorio funcional (independiente de la publicación)

Habilitar Git/GitHub **no cambia** el estado del código: hoy **solo Purchase Orders es funcional**; GRN, QC y Putaway están escritos pero fallan al crear (`TypeError` por desalineación schema↔modelo). Antes de abrir un PR que diga "Inbound completo", conviene reconciliar esos tres módulos con el mismo método aplicado a PO. Detalle en `docs/INBOUND_Validacion_Tecnica.md`.
