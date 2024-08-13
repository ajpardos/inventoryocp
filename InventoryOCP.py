import subprocess
import json
import csv
import getpass
import datetime

def run_command(command):
    """Ejecuta un comando en la terminal y devuelve la salida."""
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error executing command: {command}")
        print(f"Error message: {result.stderr}")
        return None
    return result.stdout.strip()

def login_to_openshift(api_url, username, password):
    """Inicia sesión en OpenShift usando oc login."""
    command = f"oc login {api_url} -u {username} -p {password} --insecure-skip-tls-verify"
    output = run_command(command)
    if output is not None:
        print("Successfully logged into OpenShift.")
    else:
        print("Failed to log into OpenShift.")
        exit(1)

def get_non_openshift_namespaces():
    """Obtiene todos los namespaces excluyendo los propios de OpenShift, default, kube, y hostpath-provisioner."""
    all_namespaces = run_command("kubectl get namespaces -o json")
    if all_namespaces is None:
        return []
    
    namespaces = json.loads(all_namespaces)
    excluded_prefixes = ('openshift-', 'kube-', 'default', 'hostpath-provisioner')
    non_excluded_namespaces = [
        ns['metadata']['name'] for ns in namespaces['items']
        if not ns['metadata']['name'].startswith(excluded_prefixes)
    ]
    return non_excluded_namespaces

def get_pod_info(namespace):
    """Obtiene información de los pods en un namespace."""
    pods = run_command(f"kubectl get pods -n {namespace} -o json")
    if pods is None:
        return []
    pod_info = []

    pods_json = json.loads(pods)
    for pod in pods_json['items']:
        node_name = pod['spec'].get('nodeName', 'N/A')
        resources = pod['spec']['containers'][0].get('resources', {})
        readiness_probe = pod['spec']['containers'][0].get('readinessProbe', {})
        liveness_probe = pod['spec']['containers'][0].get('livenessProbe', {})
        image = pod['spec']['containers'][0]['image']
        pod_info.append({
            'node_name': node_name,
            'resources': resources,
            'readiness_probe': readiness_probe,
            'liveness_probe': liveness_probe,
            'image': image,
            'pod_name': pod['metadata']['name']
        })
    return pod_info

def get_node_selector(namespace):
    """Obtiene el node selector del namespace."""
    namespace_info = run_command(f"kubectl get namespace {namespace} -o json")
    if namespace_info is None:
        return 'N/A'
    namespace_json = json.loads(namespace_info)
    return namespace_json['metadata'].get('annotations', {}).get('openshift.io/node-selector', 'N/A')

def get_resource_quotas(namespace):
    """Obtiene las cuotas de recursos del namespace."""
    quotas = run_command(f"kubectl get resourcequota -n {namespace} -o json")
    if quotas is None:
        return []
    quotas_json = json.loads(quotas)
    quota_info = []
    for quota in quotas_json['items']:
        quota_name = quota['metadata']['name']
        hard_limits = quota['spec']['hard']
        quota_info.append({
            'name': quota_name,
            'limits': hard_limits
        })
    return quota_info

def get_persistent_volumes():
    """Obtiene información de los volúmenes persistentes."""
    pvs = run_command("kubectl get pv -o json")
    if pvs is None:
        return []
    pvs_json = json.loads(pvs)
    pv_info = []
    for pv in pvs_json['items']:
        claim_ref = pv['spec'].get('claimRef')
        namespace = claim_ref.get('namespace') if claim_ref else None
        pv_info.append({
            'name': pv['metadata']['name'],
            'namespace': namespace,
            'capacity': pv['spec']['capacity']['storage'],
            'access_modes': pv['spec']['accessModes'],
            'reclaim_policy': pv['spec']['persistentVolumeReclaimPolicy']
        })
    return pv_info

def get_persistent_volume_claims(namespace):
    """Obtiene las reclamaciones de volúmenes persistentes del namespace."""
    pvcs = run_command(f"kubectl get pvc -n {namespace} -o json")
    if pvcs is None:
        return []
    pvcs_json = json.loads(pvcs)
    pvc_info = []
    for pvc in pvcs_json['items']:
        pvc_info.append({
            'name': pvc['metadata']['name'],
            'volume_name': pvc['spec']['volumeName'],
            'access_modes': pvc['status']['accessModes'],
            'capacity': pvc['status']['capacity']['storage'],
        })
    return pvc_info

def get_secrets(namespace):
    """Obtiene los secretos del namespace, omitiendo los que comienzan con builder, default o deployer."""
    secrets = run_command(f"kubectl get secret -n {namespace} -o json")
    if secrets is None:
        return []
    secrets_json = json.loads(secrets)
    secret_info = []
    for secret in secrets_json['items']:
        secret_name = secret['metadata']['name']
        if not (secret_name.startswith('builder') or secret_name.startswith('default') or secret_name.startswith('deployer')):
            secret_info.append({
                'name': secret_name,
                'type': secret['type'],
            })
    return secret_info

def get_configmaps(namespace):
    """Obtiene los configmaps del namespace."""
    configmaps = run_command(f"kubectl get configmap -n {namespace} -o json")
    if configmaps is None:
        return []
    configmaps_json = json.loads(configmaps)
    configmap_info = []
    for configmap in configmaps_json['items']:
        configmap_info.append({
            'name': configmap['metadata']['name'],
        })
    return configmap_info

def get_pod_metrics(namespace):
    """Obtiene métricas de los pods en un namespace."""
    metrics_output = run_command(f"kubectl top pod -n {namespace} --no-headers")
    if not metrics_output:
        return {}
    
    pod_metrics = {}
    for line in metrics_output.splitlines():
        parts = line.split()
        pod_name = parts[0]
        cpu = parts[1]
        memory = parts[2]
        pod_metrics[pod_name] = {'cpu': cpu, 'memory': memory}

    return pod_metrics

def get_deployments_info(namespace):
    """Obtiene información de los despliegues en un namespace."""
    deployments = run_command(f"kubectl get deployments -n {namespace} -o json")
    if deployments is None:
        return []
    deployment_info = []

    deployments_json = json.loads(deployments)
    for deployment in deployments_json['items']:
        deployment_name = deployment['metadata']['name']
        replicas = deployment['spec']['replicas']
        labels = deployment['metadata'].get('labels', {})
        deployment_info.append({
            'deployment_name': deployment_name,
            'replicas': replicas,
            'labels': labels
        })
    return deployment_info

def get_services_info(namespace):
    """Obtiene información de los servicios en un namespace."""
    services = run_command(f"kubectl get services -n {namespace} -o json")
    if services is None:
        return []
    service_info = []

    services_json = json.loads(services)
    for service in services_json['items']:
        service_name = service['metadata']['name']
        service_type = service['spec']['type']
        ports = service['spec'].get('ports', [])
        service_info.append({
            'name': service_name,
            'type': service_type,
            'ports': ports
        })
    return service_info

def get_routes_info(namespace):
    """Obtiene información de las rutas en un namespace."""
    routes = run_command(f"kubectl get routes -n {namespace} -o json")
    if routes is None:
        return []
    route_info = []

    routes_json = json.loads(routes)
    for route in routes_json['items']:
        route_name = route['metadata']['name']
        host = route['spec']['host']
        route_info.append({
            'name': route_name,
            'host': host
        })
    return route_info

def get_hpa_info(namespace):
    """Obtiene información de los HPA en un namespace."""
    hpas = run_command(f"kubectl get hpa -n {namespace} -o json")
    if hpas is None:
        return []
    hpa_info = []

    hpas_json = json.loads(hpas)
    for hpa in hpas_json['items']:
        hpa_name = hpa['metadata']['name']
        min_replicas = hpa['spec'].get('minReplicas', 1)
        max_replicas = hpa['spec']['maxReplicas']
        current_cpu_utilization = hpa['status'].get('currentCPUUtilizationPercentage', 'N/A')
        hpa_info.append({
            'name': hpa_name,
            'min_replicas': min_replicas,
            'max_replicas': max_replicas,
            'current_cpu_utilization': current_cpu_utilization
        })
    return hpa_info

def generate_inventory():
    """Genera un inventario de los microservicios y lo guarda en archivos CSV y JSON."""
    inventory = []
    
    pv_info = get_persistent_volumes()

    namespaces = get_non_openshift_namespaces()
    for namespace in namespaces:
        print(f"Processing namespace: {namespace}")
        pod_info = get_pod_info(namespace)
        pod_metrics = get_pod_metrics(namespace)
        deployments_info = get_deployments_info(namespace)
        services_info = get_services_info(namespace)
        routes_info = get_routes_info(namespace)
        hpa_info = get_hpa_info(namespace)
        node_selector = get_node_selector(namespace)
        quotas_info = get_resource_quotas(namespace)
        pvc_info = get_persistent_volume_claims(namespace)
        secret_info = get_secrets(namespace)
        configmap_info = get_configmaps(namespace)
        
        for deployment in deployments_info:
            deployment_name = deployment['deployment_name']
            relevant_pods = [pod for pod in pod_info if deployment_name in pod['pod_name']]
            
            for pod in relevant_pods:
                node_name = pod['node_name']
                metrics = pod_metrics.get(pod['pod_name'], {})
                inventory.append({
                    'namespace': namespace,
                    'deployment_name': deployment_name,
                    'node_name': node_name,
                    'pod_resources': pod['resources'],
                    'pod_readiness_probe': pod['readiness_probe'],
                    'pod_liveness_probe': pod['liveness_probe'],
                    'pod_image': pod['image'],
                    'pod_cpu_usage': metrics.get('cpu', 'N/A'),
                    'pod_memory_usage': metrics.get('memory', 'N/A')
                })

            inventory.append({
                'namespace': namespace,
                'deployment_name': deployment_name,
                'deployment_replicas': deployment['replicas'],
                'deployment_labels': deployment['labels']
            })

        for service in services_info:
            inventory.append({
                'namespace': namespace,
                'service_name': service['name'],
                'service_type': service['type'],
                'service_ports': service['ports']
            })

        for route in routes_info:
            inventory.append({
                'namespace': namespace,
                'route_name': route['name'],
                'route_host': route['host']
            })

        for hpa in hpa_info:
            inventory.append({
                'namespace': namespace,
                'hpa_name': hpa['name'],
                'hpa_min_replicas': hpa['min_replicas'],
                'hpa_max_replicas': hpa['max_replicas'],
                'hpa_current_cpu_utilization': hpa['current_cpu_utilization']
            })

        for quota in quotas_info:
            inventory.append({
                'namespace': namespace,
                'quota_name': quota['name'],
                'quota_limits': quota['limits']
            })

        for pv in pv_info:
            if pv['namespace'] == namespace:
                inventory.append({
                    'namespace': namespace,
                    'pv_name': pv['name'],
                    'pv_capacity': pv['capacity'],
                    'pv_access_modes': pv['access_modes'],
                    'pv_reclaim_policy': pv['reclaim_policy']
                })

        for pvc in pvc_info:
            inventory.append({
                'namespace': namespace,
                'pvc_name': pvc['name'],
                'pvc_volume_name': pvc['volume_name'],
                'pvc_access_modes': pvc['access_modes'],
                'pvc_capacity': pvc['capacity']
            })

        for secret in secret_info:
            inventory.append({
                'namespace': namespace,
                'secret_name': secret['name'],
                'secret_type': secret['type']
            })

        for configmap in configmap_info:
            inventory.append({
                'namespace': namespace,
                'configmap_name': configmap['name']
            })

        # Añadir el node selector al nivel del namespace
        if node_selector != 'N/A':
            inventory.append({
                'namespace': namespace,
                'node_selector': node_selector
            })

    # Obtener la fecha actual para usarla en el nombre de los archivos
    date_str = datetime.datetime.now().strftime("%Y%m%d")

    # Guardar el inventario en un archivo CSV
    with open(f'inventario_{date_str}.csv', 'w', newline='') as csvfile:
        fieldnames = [
            'namespace', 'node_name', 'pod_resources', 'pod_readiness_probe', 'pod_liveness_probe',
            'pod_image', 'pod_cpu_usage', 'pod_memory_usage', 'deployment_name', 'deployment_replicas', 'deployment_labels',
            'service_name', 'service_type', 'service_ports', 'route_name', 'route_host',
            'hpa_name', 'hpa_min_replicas', 'hpa_max_replicas', 'hpa_current_cpu_utilization',
            'quota_name', 'quota_limits', 'pv_name', 'pv_capacity', 'pv_access_modes', 'pv_reclaim_policy',
            'pvc_name', 'pvc_volume_name', 'pvc_access_modes', 'pvc_capacity',
            'secret_name', 'secret_type', 'configmap_name', 'node_selector'
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for entry in inventory:
            writer.writerow(entry)
    print(f"Inventario generado en 'inventario_{date_str}.csv'")

    # Guardar el inventario en un archivo JSON
    with open(f'inventario_{date_str}.json', 'w') as jsonfile:
        json.dump(inventory, jsonfile, indent=2)
    print(f"Inventario generado en 'inventario_{date_str}.json'")

if __name__ == "__main__":
    api_url = input("Ingrese la URL del clúster de OpenShift: ")
    username = input("Ingrese el nombre de usuario: ")
    password = getpass.getpass("Ingrese la contraseña: ")

    login_to_openshift(api_url, username, password)
    generate_inventory()