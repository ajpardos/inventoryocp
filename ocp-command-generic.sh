NS=xxx-redis
oc version
oc get sub,installplan -n $NS
oc get packagemanifest redis-enterprise-operator-cert -o jsonpath='{range .status.channels[*]}{.name}{" → "}{.currentCSV}{"\n"}{end}'
oc get rec -n $NS        # LICENSE STATE
oc get rec rec -n $NS -o yaml | grep -E -A6 'redisEnterpriseImageSpec|upgradeSpec|redisUpgradePolicy|userDefinedModules'
oc get redb xxxxxx -n $NS -o jsonpath='{.spec.redisVersion}{"  "}{.spec.moduleList}{"\n"}'
oc get scc | grep redis
