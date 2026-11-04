#!/usr/bin/env bash
# =============================================================================
# scale-down-c-prd.sh
# Guarda las réplicas actuales de los microservicios en los namespaces cuyo
# nombre contenga PATTERN (por defecto "c-prd") y luego los escala a 0.
#
# Uso:
#   ./scale-down-c-prd.sh              # pide confirmación
#   ./scale-down-c-prd.sh --dry-run    # solo genera el respaldo, no escala
#   ./scale-down-c-prd.sh --yes        # sin confirmación
#
# Variables opcionales:
#   PATTERN="c-prd"                          texto a buscar en el namespace
#   EXCLUDE="mashery|redis"                  namespaces excluidos (bajado manual)
#   RESOURCES="deployment deploymentconfig"  tipos a escalar (agrega statefulset si aplica)
#   BACKUP_DIR="./replicas-backup"           carpeta del respaldo
# =============================================================================
set -euo pipefail

PATTERN="${PATTERN:-c-prd}"
EXCLUDE="${EXCLUDE:-mashery|redis}"   # regex de namespaces a excluir
RESOURCES="${RESOURCES:-deployment deploymentconfig}"
BACKUP_DIR="${BACKUP_DIR:-./replicas-backup}"
DRY_RUN=false
ASSUME_YES=false

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --yes|-y)  ASSUME_YES=true ;;
    *) echo "Parámetro no reconocido: $arg"; exit 1 ;;
  esac
done

command -v oc >/dev/null || { echo "ERROR: 'oc' no está instalado"; exit 1; }
oc whoami >/dev/null 2>&1 || { echo "ERROR: no hay sesión activa en oc"; exit 1; }

CLUSTER="$(oc whoami --show-server)"
TS="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"
OUT="$BACKUP_DIR/replicas-${TS}.csv"

echo "Cluster : $CLUSTER"
echo "Patrón  : *${PATTERN}*"
echo "Tipos   : $RESOURCES"

mapfile -t NAMESPACES < <(
  oc get ns -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' \
    | grep -- "$PATTERN" | grep -viE -- "$EXCLUDE" || true
)
echo "Excluidos: namespaces que contienen '$EXCLUDE' (se bajan manualmente)"

if [[ ${#NAMESPACES[@]} -eq 0 ]]; then
  echo "No se encontraron namespaces que contengan '$PATTERN'."
  exit 0
fi
echo "Namespaces encontrados: ${#NAMESPACES[@]}"

# Solo usar los tipos que existan en el cluster (ej. DeploymentConfig)
VALID_RESOURCES=()
for res in $RESOURCES; do
  if oc explain "$res" >/dev/null 2>&1; then
    VALID_RESOURCES+=("$res")
  else
    echo "AVISO: el recurso '$res' no existe en este cluster, se omite."
  fi
done

# ---- 1. Respaldo (antes de tocar nada) --------------------------------------
{
  echo "# cluster=$CLUSTER"
  echo "# fecha=$TS"
  echo "# namespace,kind,name,replicas"
} > "$OUT"

COUNT=0
for ns in "${NAMESPACES[@]}"; do
  for res in "${VALID_RESOURCES[@]}"; do
    while IFS=',' read -r name replicas; do
      [[ -z "$name" ]] && continue
      replicas="${replicas:-0}"
      # Solo se guardan los que tienen réplicas > 0. Así, si se corre dos veces,
      # el segundo respaldo no "pisa" los valores reales con ceros.
      if [[ "$replicas" -gt 0 ]]; then
        echo "${ns},${res},${name},${replicas}" >> "$OUT"
        COUNT=$((COUNT + 1))
      fi
    done < <(oc get "$res" -n "$ns" \
              -o jsonpath='{range .items[*]}{.metadata.name}{","}{.spec.replicas}{"\n"}{end}' 2>/dev/null)
  done
done

if [[ "$COUNT" -eq 0 ]]; then
  echo "No hay microservicios con réplicas > 0. Nada que escalar."
  rm -f "$OUT"
  exit 0
fi

ln -sfn "$(basename "$OUT")" "$BACKUP_DIR/latest.csv"
echo "Respaldo guardado: $OUT ($COUNT recursos)"

if $DRY_RUN; then
  echo "--dry-run: no se escaló nada. Revisa el respaldo:"
  column -t -s',' < <(grep -v '^#' "$OUT")
  exit 0
fi

# ---- 2. Confirmación --------------------------------------------------------
if ! $ASSUME_YES; then
  read -r -p "Se escalarán $COUNT recursos a 0 en $CLUSTER. ¿Continuar? (si/no): " ans
  [[ "$ans" == "si" ]] || { echo "Cancelado. El respaldo queda en $OUT"; exit 0; }
fi

# ---- 3. Escalar a 0 ---------------------------------------------------------
FAIL=0
while IFS=',' read -r ns kind name replicas; do
  [[ "$ns" =~ ^# || -z "$ns" ]] && continue
  if oc scale "$kind/$name" -n "$ns" --replicas=0 >/dev/null 2>&1; then
    echo "OK    $ns/$kind/$name  $replicas -> 0"
  else
    echo "ERROR $ns/$kind/$name"
    FAIL=$((FAIL + 1))
  fi
done < "$OUT"

echo "Terminado. Errores: $FAIL. Para restaurar: ./scale-up-c-prd.sh $OUT"
