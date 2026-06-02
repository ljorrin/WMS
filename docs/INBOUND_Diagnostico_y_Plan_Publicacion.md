# Diagnóstico de publicación y plan de habilitación

**Proyecto:** WMS Panamá · **Rama:** `feature/inbound-module` · **Fecha:** 2026-06-01
**Método:** ejecución real de comandos en el entorno; cada afirmación tiene evidencia reproducible.

---

## 1. Diagnóstico (evidencia real)

| Verificación | Resultado |
|---|---|
| Rama actual | `feature/inbound-module` |
| `git branch` | `* feature/inbound-module`, `main` |
| `git remote -v` | `origin https://github.com/ljorrin/WMS.git` (fetch y push) |
| `git status` | 20 modificados, 11 sin trackear (9 reales + 2 archivos de prueba) |
| Archivos creados | `POEditModal.tsx`, `docs/*.md`, `inbound_changes.patch` (+ los de sesión previa) |
| Archivos eliminados | ninguno |

### Errores exactos

**`git add` / `git commit`:**
```
fatal: Unable to create '/sessions/.../mnt/WMS/.git/index.lock': File exists.
... remove the file manually to continue.
```
exit **128**. Y al intentar quitar el lock:
```
rm: cannot remove '.git/index.lock': Operation not permitted   (exit 1)
```

**`git push origin feature/inbound-module`** (con `GIT_TERMINAL_PROMPT=0`):
```
fatal: could not read Username for 'https://github.com': terminal prompts disabled
```
exit **128**.

**Creación de Pull Request:**
```
gh: command not found        → GitHub CLI NO está instalado
```
No hay credential helper (`git config credential.helper` vacío), ni `~/.netrc`, ni `~/.git-credentials`, ni `~/.ssh`. No hay `GITHUB_TOKEN`/`GH_TOKEN` en el entorno (sí existe `CLAUDE_CODE_OAUTH_TOKEN`, que es de Claude, no de GitHub).

### Pruebas de aislamiento (clave para la causa raíz)

1. **Red a GitHub: FUNCIONA.** `git ls-remote https://github.com/ljorrin/WMS.git` → exit 0, devuelve `main d7172a03…`. El repo es legible públicamente; la red **no** es el problema.
2. **Montaje:** `/sessions/.../mnt/WMS` es un **FUSE** sobre `…/Documents/Claude/Projects/WMS`, con mounts auxiliares `.cowork-perm-req` / `.cowork-perm-resp` (canal de permisos de Cowork). El borrado de archivos está **mediado por la capa de permisos de Cowork**.
3. **Git fuera del mount: FUNCIONA.** Creé un repo en el scratchpad (`/sessions/.../_gittest`), `git add` + `git commit` → **OK**. Git en sí es plenamente funcional.
4. **Borrado en scratchpad: FUNCIONA** (`rm -rf _gittest` → exit 0); borrado dentro del mount **falla** (`Operation not permitted`).

---

## 2. Análisis de causa raíz

Hay **dos bloqueos independientes**, de orígenes distintos:

### Bloqueo A — No se puede hacer `commit` (operación: `git add`/`commit`)
- **Qué se bloquea:** el `unlink` (borrado) de archivos dentro del directorio montado `WMS`, incluido `.git/`.
- **Por qué:** Git necesita borrar/renombrar para quitar `.git/index.lock`, finalizar objetos en `.git/objects` y actualizar refs. El borrado está denegado.
- **Componente que genera la limitación:** la **capa de permisos del sandbox de Cowork** sobre el montaje FUSE (no es Git, ni el SO base, ni GitHub). Está demostrado: Git commitea perfectamente fuera del mount, y el borrado funciona en el scratchpad pero no en el mount. El borrado de archivos en carpetas montadas requiere **aprobación explícita del usuario** (herramienta `allow_cowork_file_delete`), que fue rechazada en intentos anteriores.
- **Clasificación:** restricción del **sandbox / permisos del sistema de archivos montado**. No es problema de credenciales, red ni configuración de Git.

### Bloqueo B — No se puede hacer `push` ni crear el PR
- **B1 (push):** **falta de credenciales de GitHub.** El error `could not read Username` indica que Git intentó autenticación HTTPS y no hay credencial alguna configurada. Clasificación: **autenticación/credenciales** (no red: la red funciona).
- **B2 (PR):** **`gh` no está instalado** y no hay sesión autenticada. Clasificación: **herramienta faltante + autenticación**.

> Resumen: el `commit` lo bloquea el **sandbox** (permiso de borrado); el `push`/`PR` los bloquean **credenciales + tooling**. Son problemas separados; resolver uno no resuelve el otro.

---

## 3. Plan de habilitación (qué necesito · para qué · cómo lo provees · cómo se verifica)

### Requisito 1 — Permiso de borrado en el directorio del proyecto (resuelve Bloqueo A)
- **Qué:** aprobar la solicitud de borrado de Cowork (`allow_cowork_file_delete`) para `WMS`.
- **Para qué:** poder eliminar `.git/index.lock` y permitir que Git finalice objetos/refs → habilita `git add`/`commit`.
- **Cómo lo provees:** cuando lance la solicitud de permiso de borrado, **aprobarla** (en intentos previos se rechazó).
- **Cómo lo verifico:** `rm -f .git/index.lock` → exit 0; luego `git add <archivo>` y `git commit` → exit 0; `git log --oneline` muestra el nuevo commit.

### Requisito 2 — Credencial de GitHub con permiso de escritura (resuelve Bloqueo B1, push)
Opción **A (recomendada): Personal Access Token (PAT) fine-grained**
- **Qué:** un PAT con alcance **Contents: Read/Write** y **Pull requests: Read/Write** sobre `ljorrin/WMS`.
- **Para qué:** autenticar `git push` por HTTPS y crear el PR vía API/gh.
- **Cómo lo provees (sin exponerlo en el chat):** configúralo tú en el entorno de la sesión como variable, p. ej. `GITHUB_TOKEN`, **o** colócalo en `~/.git-credentials` con `git config --global credential.helper store`. *No lo pegues en el chat* (por seguridad, y porque por política yo no debo introducir tokens manualmente).
- **Cómo lo verifico:** `git push --dry-run origin feature/inbound-module` → sin error de auth; o `git ls-remote` autenticado.

Opción **B: Llave SSH**
- **Qué:** par de llaves SSH; la pública añadida a la cuenta GitHub (`ljorrin`); remoto cambiado a `git@github.com:ljorrin/WMS.git`.
- **Para qué:** autenticación de push sin token en HTTPS.
- **Cómo lo provees:** colocar la privada en `~/.ssh/id_ed25519` (permisos 600) y la pública en GitHub → Settings → SSH keys; `git remote set-url origin git@github.com:ljorrin/WMS.git`.
- **Cómo lo verifico:** `ssh -T git@github.com` responde con saludo de GitHub; `git push --dry-run` OK.

### Requisito 3 — Herramienta para crear el PR (resuelve Bloqueo B2)
Opción **A: GitHub CLI**
- **Qué:** instalar `gh` y autenticarlo (`gh auth login` con el PAT, o `GH_TOKEN` en entorno).
- **Para qué:** `gh pr create --base main --head feature/inbound-module`.
- **Cómo lo verifico:** `gh auth status` → "Logged in"; `gh pr create …` devuelve la URL del PR.

Opción **B: API REST (si no se puede instalar `gh`)**
- **Qué:** usar el PAT con `curl -X POST https://api.github.com/repos/ljorrin/WMS/pulls`.
- **Cómo lo verifico:** la respuesta JSON incluye `"html_url"` del PR.

### (No requerido) Red y Git
- **Red a GitHub:** ya funciona (verificado). **Git:** ya funciona (verificado fuera del mount). No hay que cambiar nada aquí.

---

## 4. Procedimiento para habilitar la publicación automática en próximas sesiones

1. **Herramientas:** Git (ya presente) + `gh` instalado **o** `curl` (presente) para la API.
2. **Configuraciones:**
   - `git config --global credential.helper store` (o usar `GITHUB_TOKEN` en URL de push).
   - Remoto HTTPS (actual) **o** SSH.
3. **Permisos:**
   - Aprobar el borrado de archivos en el directorio `WMS` (Cowork) **una vez por sesión** para que Git opere.
   - El PAT/SSH debe tener escritura sobre `ljorrin/WMS` y permiso para abrir PRs hacia `main`.
4. **Credenciales:** PAT fine-grained (Contents R/W + PR R/W) **o** SSH key autorizada.
5. **Pasos de configuración (una vez provisto lo anterior):**
   ```bash
   # (a) desbloquear git en el mount
   rm -f .git/index.lock
   # (b) credencial (la defines tú en el entorno; ejemplo con token en variable)
   git remote set-url origin "https://x-access-token:${GITHUB_TOKEN}@github.com/ljorrin/WMS.git"
   # (c) commits
   git add -A && git commit -m "..."   # (o los 4 commits por área del plan)
   # (d) push
   git push -u origin feature/inbound-module
   # (e) PR
   gh pr create --base main --head feature/inbound-module --title "..." --body "..."
   #   o vía API:
   # curl -s -X POST -H "Authorization: Bearer $GITHUB_TOKEN" \
   #   https://api.github.com/repos/ljorrin/WMS/pulls \
   #   -d '{"title":"...","head":"feature/inbound-module","base":"main"}'
   ```
6. **Riesgos de seguridad:**
   - Un **PAT con escritura** es un secreto: si se filtra, permite modificar el repo. Usar **fine-grained**, mínimo alcance (solo `WMS`), **caducidad corta**, y **revocarlo** al terminar. No pegarlo en el chat; cargarlo como variable de entorno o credential store.
   - `credential.helper store` guarda el token **en claro** en `~/.git-credentials`. Preferible variable de entorno efímera de sesión.
   - Conceder permiso de borrado en el directorio permite que cualquier proceso de la sesión borre archivos del proyecto; es acotado a esta carpeta y a esta sesión.
   - Por mis reglas de operación, **no introduzco tokens ni contraseñas manualmente** ni hago push/PR sin tu confirmación explícita por acción; tú provees la credencial en el entorno y yo ejecuto los comandos con tu visto bueno.
7. **Alternativas (sin habilitar nada):**
   - Aplicar el parche `inbound_changes.patch` ya generado y hacer commit/push/PR **desde tu máquina** (camino más simple y seguro; no requiere darme credenciales).
   - O dividir en 4 `.patch` por commit para `git am`.

---

## 5. Conclusión

- **Por qué no pude hacer push:** dos causas encadenadas. (1) No pude **commitear** porque el sandbox bloquea el borrado en el directorio montado y no se aprobó el permiso para quitar `.git/index.lock`. (2) Aunque pudiera commitear, el **push** falla por **ausencia de credenciales de GitHub**, y el **PR** porque **`gh` no está instalado**. La red y Git funcionan.
- **Qué me falta:** (A) tu aprobación del permiso de borrado en `WMS`; (B) una credencial de escritura (PAT fine-grained o SSH) cargada en el entorno; (C) `gh` instalado/autenticado o uso de la API con el PAT.
- **Para automatizar commit + push + PR sin intervención manual** en una próxima sesión: provee A + B + C como se detalla arriba; con eso ejecuto el procedimiento de la sección 4 de principio a fin.
