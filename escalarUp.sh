#!/usr/bin/env bash
# =============================================================================
# scale-up-c-prd.sh
# Restaura las réplicas guardadas por scale-down-c-prd.sh.
#
# Uso:
#   ./scale-up-c-prd.sh                                   # usa replicas-backup/latest.csv
#   ./scale-up-c-prd.sh replicas-backup/replicas-XXXX.csv # archivo específico
#   ./scale-up-c-prd.sh <archivo> --dry-run               # muestra qué haría
#   ./scale-up-c-prd.sh <archivo> --yes                   # sin confirmación
# =============================================================================
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./replicas-backup}"
EXCLUDE="${EXCLUDE:-mashery|redis}"   # namespaces excluidos (subida manual)
FILE=""
DRY_RUN=false
ASSUME_YES=false

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --yes|-y)  ASSUME_YES=true ;;
    *)         FILE="$arg" ;;
  esac
done

FILE="${FILE:-$BACKUP_DIR/latest.csv}"
[[ -f "$FILE" ]] || { echo "ERROR: no existe el archivo de respaldo '$FILE'"; exit 1; }

command -v oc >/dev/null || { echo "ERROR: 'oc' no está instalado"; exit 1; }
oc whoami >/dev/null 2>&1 || { echo "ERROR: no hay sesión activa en oc"; exit 1; }

# ---- Validar que estamos en el mismo cluster del respaldo -------------------
CURRENT="$(oc whoami --show-server)"
SAVED="$(grep -m1 '^# cluster=' "$FILE" | cut -d= -f2-)"

echo "Respaldo : $FILE"
echo "Cluster respaldo : ${SAVED:-desconocido}"
echo "Cluster actual   : $CURRENT"

if [[ -n "$SAVED" && "$SAVED" != "$CURRENT" ]]; then
  echo "ERROR: el respaldo es de otro cluster. Haz 'oc login' al cluster correcto."
  exit 1
fi

TOTAL=$(grep -vc '^#' "$FILE" || true)
echo "Recursos a restaurar: $TOTAL"

if $DRY_RUN; then
  column -t -s',' < <(grep -v '^#' "$FILE")
  exit 0
fi

if ! $ASSUME_YES; then
  read -r -p "¿Restaurar $TOTAL recursos en $CURRENT? (si/no): " ans
  [[ "$ans" == "si" ]] || { echo "Cancelado."; exit 0; }
fi

OK=0; FAIL=0; MISSING=0
while IFS=',' read -r ns kind name replicas; do
  [[ "$ns" =~ ^# || -z "$ns" ]] && continue

  if grep -qiE -- "$EXCLUDE" <<<"$ns"; then
    echo "EXCLUIDO $ns/$kind/$name (subida manual)"
    continue
  fi

  if ! oc get "$kind/$name" -n "$ns" >/dev/null 2>&1; then
    echo "NO EXISTE $ns/$kind/$name (se omite)"
    MISSING=$((MISSING + 1))
    continue
  fi

  if oc scale "$kind/$name" -n "$ns" --replicas="$replicas" >/dev/null 2>&1; then
    echo "OK    $ns/$kind/$name  0 -> $replicas"
    OK=$((OK + 1))
  else
    echo "ERROR $ns/$kind/$name"
    FAIL=$((FAIL + 1))
  fi
done < "$FILE"

echo "Terminado. OK: $OK | Errores: $FAIL | No encontrados: $MISSING"
