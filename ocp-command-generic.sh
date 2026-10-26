NS=xxx-redis
oc version
oc get sub,installplan -n $NS
oc get packagemanifest redis-enterprise-operator-cert -o jsonpath='{range .status.channels[*]}{.name}{" → "}{.currentCSV}{"\n"}{end}'
oc get rec -n $NS        # LICENSE STATE
oc get rec rec -n $NS -o yaml | grep -E -A6 'redisEnterpriseImageSpec|upgradeSpec|redisUpgradePolicy|userDefinedModules'
oc get redb xxxxxx -n $NS -o jsonpath='{.spec.redisVersion}{"  "}{.spec.moduleList}{"\n"}'
oc get scc | grep redis
# Versión real de la DB
rladmin status databases extra all

# ¿El bundle 8.2.0-19.1 acepta saltar desde 7.8.6? (lo que falló en dev)
oc get packagemanifest redis-enterprise-operator-cert -o jsonpath='{.status.channels[?(@.name=="production")].currentCSVDesc.annotations.olm\.skipRange}{"\n"}'
oc get packagemanifest redis-enterprise-operator-cert -o jsonpath='{range .status.channels[?(@.name=="production")].entries[*]}{.name}{"\n"}{end}'
