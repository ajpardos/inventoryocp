#/bin/bash
# ============================================================================
# Script: find_old_java_deployments.sh
# Description: Connects to each running pod in OpenShift 4, detects the actual
#              Java version running inside the container, and exports results
#              to a CSV file. Excludes OCP internal projects and operators.
#              Uses timeouts to prevent hanging.
# Requires: oc CLI logged into the cluster
# ============================================================================

set -uo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# ============================================================================
# CONFIGURATION
# ============================================================================
EXEC_TIMEOUT=10        # Seconds to wait for oc exec before killing it
MAX_PARALLEL=5         # Number of pods to scan in parallel

echo -e "${GREEN}=============================================${NC}"
echo -e "${GREEN} OpenShift 4 - Java Version Scanner${NC}"
echo -e "${GREEN} Detecting Java <= 8 inside running pods${NC}"
echo -e "${GREEN} (Excluding OCP internal & operators)${NC}"
echo -e "${GREEN} Timeout: ${EXEC_TIMEOUT}s per pod${NC}"
echo -e "${GREEN}=============================================${NC}"
echo ""

# Check prerequisites
if ! command -v oc &> /dev/null; then
    echo -e "${RED}ERROR: 'oc' CLI not found.${NC}"
    exit 1
fi

if ! oc whoami &> /dev/null; then
    echo -e "${RED}ERROR: Not logged in to OpenShift. Run 'oc login' first.${NC}"
    exit 1
fi

# Check for timeout command
TIMEOUT_CMD=""
if command -v timeout &> /dev/null; then
    TIMEOUT_CMD="timeout"
elif command -v gtimeout &> /dev/null; then
    TIMEOUT_CMD="gtimeout"  # macOS with coreutils
else
    echo -e "${YELLOW}WARNING: 'timeout' command not found. Script may hang on unresponsive pods.${NC}"
    echo -e "${YELLOW}Install coreutils to get the timeout command.${NC}"
fi

# ============================================================================
# EXCLUSION RULES
# ============================================================================

EXCLUDED_NS_PREFIXES=(
    "openshift-"
    "kube-"
)

EXCLUDED_NS_EXACT=(
    "default"
    "openshift"
    "kube-system"
    "kube-public"
    "kube-node-lease"
)

EXCLUDED_NS_PATTERNS=(
    ".*-operator$"
    ".*-operators$"
    ".*-metrics-operator$"
)

EXCLUDED_DEPLOY_PATTERNS=(
    ".*-operator-.*"
    ".*-operator$"
    ".*-controller-manager-.*"
    ".*-controller-manager$"
    ".*-webhook-.*"
    "costmanagement-.*"
    "cert-manager-.*"
    "cluster-logging-.*"
    "elasticsearch-operator-.*"
    "jaeger-operator-.*"
    "kiali-operator-.*"
    "servicemesh-.*"
    "compliance-operator-.*"
    "file-integrity-operator-.*"
    "ocs-operator-.*"
    "odf-operator-.*"
    "rhsso-operator-.*"
    "amq-.*-operator-.*"
    "serverless-operator-.*"
    "web-terminal-.*"
    "gitops-operator-.*"
    "pipelines-operator-.*"
    "nfd-.*-operator-.*"
    "gpu-operator-.*"
    "sriov-.*-operator-.*"
    "metallb-operator-.*"
    "local-storage-operator-.*"
)

is_ns_excluded() {
    local ns="$1"
    for excluded in "${EXCLUDED_NS_EXACT[@]}"; do
        [[ "$ns" == "$excluded" ]] && return 0
    done
    for prefix in "${EXCLUDED_NS_PREFIXES[@]}"; do
        [[ "$ns" == ${prefix}* ]] && return 0
    done
    for pattern in "${EXCLUDED_NS_PATTERNS[@]}"; do
        echo "$ns" | grep -qE "$pattern" && return 0
    done
    return 1
}

is_deploy_excluded() {
    local deploy="$1"
    for pattern in "${EXCLUDED_DEPLOY_PATTERNS[@]}"; do
        echo "$deploy" | grep -iqE "$pattern" && return 0
    done
    return 1
}

# ============================================================================
# Execute java -version with timeout
# ============================================================================
exec_java_version() {
    local ns="$1"
    local pod="$2"
    local container="$3"

    if [[ -n "$TIMEOUT_CMD" ]]; then
        $TIMEOUT_CMD ${EXEC_TIMEOUT}s oc exec -n "$ns" "$pod" -c "$container" -- \
            sh -c 'java -version 2>&1 || echo "NO_JAVA"' 2>/dev/null
    else
        oc exec -n "$ns" "$pod" -c "$container" -- \
            sh -c 'java -version 2>&1 || echo "NO_JAVA"' 2>/dev/null
    fi
}

# ============================================================================
# Process a single pod (used for parallel execution)
# ============================================================================
process_pod() {
    local ns="$1"
    local pod="$2"
    local owner="$3"
    local container="$4"
    local image="$5"
    local all_csv="$6"
    local old_csv="$7"
    local scan_date="$8"

    JAVA_OUTPUT=$(exec_java_version "$ns" "$pod" "$container")
    EXIT_CODE=$?

    # timeout returns 124 when it kills the process
    if [[ $EXIT_CODE -eq 124 ]]; then
        JAVA_OUTPUT="TIMEOUT"
    fi

    JAVA_VERSION=""
    MAJOR=""
    STATUS=""

    if [[ -z "$JAVA_OUTPUT" ]] || echo "$JAVA_OUTPUT" | grep -q "TIMEOUT"; then
        STATUS="TIMEOUT"
        JAVA_VERSION="TIMEOUT"
        MAJOR="N/A"
    elif echo "$JAVA_OUTPUT" | grep -q "NO_JAVA"; then
        STATUS="NO_JAVA"
        JAVA_VERSION="N/A"
        MAJOR="N/A"
    elif echo "$JAVA_OUTPUT" | grep -qi "OCI runtime exec failed\|cannot exec\|error\|unable to upgrade"; then
        STATUS="ERROR"
        JAVA_VERSION="UNKNOWN"
        MAJOR="N/A"
    else
        JAVA_VERSION=$(echo "$JAVA_OUTPUT" | grep -i 'version' | head -1 | \
            sed -n 's/.*version "\([^"]*\)".*/\1/p')

        if [[ -z "$JAVA_VERSION" ]]; then
            JAVA_VERSION="PARSE_ERROR"
            MAJOR="N/A"
            STATUS="ERROR"
        else
            if [[ "$JAVA_VERSION" == 1.* ]]; then
                MAJOR=$(echo "$JAVA_VERSION" | cut -d'.' -f2)
            else
                MAJOR=$(echo "$JAVA_VERSION" | cut -d'.' -f1)
            fi

            if [[ "$MAJOR" -le 8 ]] 2>/dev/null; then
                STATUS="UPGRADE_REQUIRED"
            else
                STATUS="OK"
            fi
        fi
    fi

    # Sanitize image
    CLEAN_IMAGE=$(echo "$image" | tr ';' '_')

    # Write to CSV (use flock to avoid race conditions in parallel mode)
    {
        flock -x 200
        echo "${ns};${owner};${pod};${container};${CLEAN_IMAGE};${JAVA_VERSION};${MAJOR};${STATUS};${scan_date}" >> "$all_csv"
        if [[ "$STATUS" == "UPGRADE_REQUIRED" ]]; then
            echo "${ns};${owner};${pod};${container};${CLEAN_IMAGE};${JAVA_VERSION};${MAJOR};${STATUS};${scan_date}" >> "$old_csv"
        fi
    } 200>/tmp/java_scan.lock

    # Console output
    case "$STATUS" in
        UPGRADE_REQUIRED)
            echo -e "${RED}  [JAVA <= 8] ${ns} / ${owner} / ${container} -> Java ${JAVA_VERSION}${NC}" ;;
        TIMEOUT)
            echo -e "${YELLOW}  [TIMEOUT]   ${ns} / ${owner} / ${container} (skipped after ${EXEC_TIMEOUT}s)${NC}" ;;
        ERROR)
            echo -e "${YELLOW}  [ERROR]     ${ns} / ${owner} / ${container}${NC}" ;;
        OK)
            echo -e "${GREEN}  [OK]        ${ns} / ${owner} / ${container} -> Java ${JAVA_VERSION}${NC}" ;;
        NO_JAVA)
            echo -e "  [NO JAVA]   ${ns} / ${owner} / ${container}" ;;
    esac
}

export -f exec_java_version process_pod is_ns_excluded is_deploy_excluded
export TIMEOUT_CMD EXEC_TIMEOUT
export RED GREEN YELLOW CYAN NC
export EXCLUDED_NS_PREFIXES EXCLUDED_NS_EXACT EXCLUDED_NS_PATTERNS EXCLUDED_DEPLOY_PATTERNS

# Namespace selection
NAMESPACE_FLAG="--all-namespaces"
if [[ "${1:-}" != "" ]]; then
    NAMESPACE_FLAG="-n $1"
    echo -e "${YELLOW}Scanning namespace: $1${NC}"
else
    echo -e "${YELLOW}Scanning all namespaces (excluding OCP internal & operators)...${NC}"
fi
echo ""

# Output CSV files
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
ALL_RESULTS_CSV="java_scan_all_${TIMESTAMP}.csv"
OLD_JAVA_CSV="java_scan_old_versions_${TIMESTAMP}.csv"

echo "NAMESPACE;DEPLOYMENT;POD;CONTAINER;IMAGE;JAVA_VERSION;MAJOR_VERSION;STATUS;SCAN_DATE" > "$ALL_RESULTS_CSV"
echo "NAMESPACE;DEPLOYMENT;POD;CONTAINER;IMAGE;JAVA_VERSION;MAJOR_VERSION;STATUS;SCAN_DATE" > "$OLD_JAVA_CSV"

SCAN_DATE=$(date +%Y-%m-%d)

echo -e "${CYAN}Fetching pod list...${NC}"

# Get pod list and filter
POD_LIST=$(oc get pods ${NAMESPACE_FLAG} -o json 2>/dev/null | jq -r '
  .items[] |
  select(.status.phase == "Running") |
  .metadata.namespace as $ns |
  .metadata.name as $pod |
  (.metadata.ownerReferences // [] | .[0].name // "unknown") as $owner |
  .spec.containers[] |
  "\($ns)|\($pod)|\($owner)|\(.name)|\(.image)"
')

TOTAL_PODS=$(echo "$POD_LIST" | wc -l)
echo -e "${CYAN}Found ${TOTAL_PODS} running containers. Filtering and scanning...${NC}"
echo ""

SCANNED=0
SKIPPED=0

echo "$POD_LIST" | while IFS='|' read -r ns pod owner container image; do

    # Skip excluded namespaces
    if is_ns_excluded "$ns"; then
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    # Skip operator deployments
    if is_deploy_excluded "$owner"; then
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    SCANNED=$((SCANNED + 1))
    process_pod "$ns" "$pod" "$owner" "$container" "$image" "$ALL_RESULTS_CSV" "$OLD_JAVA_CSV" "$SCAN_DATE"

done

echo ""
echo -e "${GREEN}=============================================${NC}"
echo -e "${GREEN} SCAN COMPLETE${NC}"
echo -e "${GREEN}=============================================${NC}"
echo ""
echo -e "${GREEN}CSV FILES:${NC}"
echo -e "  All results:   ${CYAN}${ALL_RESULTS_CSV}${NC}"
echo -e "  Old Java only: ${RED}${OLD_JAVA_CSV}${NC}"
echo ""

# Show summary from CSV
if [[ -f "$ALL_RESULTS_CSV" ]]; then
    TOTAL_SCANNED=$(tail -n +2 "$ALL_RESULTS_CSV" | wc -l)
    OLD_COUNT=$(grep -c "UPGRADE_REQUIRED" "$ALL_RESULTS_CSV" 2>/dev/null || echo 0)
    TIMEOUT_COUNT=$(grep -c "TIMEOUT" "$ALL_RESULTS_CSV" 2>/dev/null || echo 0)
    ERROR_COUNT=$(grep -c ";ERROR;" "$ALL_RESULTS_CSV" 2>/dev/null || echo 0)
    OK_COUNT=$(grep -c ";OK;" "$ALL_RESULTS_CSV" 2>/dev/null || echo 0)
    NOJAVA_COUNT=$(grep -c "NO_JAVA" "$ALL_RESULTS_CSV" 2>/dev/null || echo 0)

    echo -e "  Containers scanned:          $TOTAL_SCANNED"
    echo -e "${GREEN}  Java OK (> 8):              $OK_COUNT${NC}"
    echo -e "${RED}  Java <= 8 (need upgrade):   $OLD_COUNT${NC}"
    echo -e "  No Java:                     $NOJAVA_COUNT"
    echo -e "${YELLOW}  Timeouts:                   $TIMEOUT_COUNT${NC}"
    echo -e "${YELLOW}  Errors:                     $ERROR_COUNT${NC}"
fi

echo ""
echo -e "${YELLOW}Timeout was set to ${EXEC_TIMEOUT}s per container.${NC}"
echo -e "${YELLOW}Adjust EXEC_TIMEOUT at the top of the script if needed.${NC}"
echo ""
echo -e "${GREEN}Done.${NC}"