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
        try:
            pvc_info.append({
                'name': pvc['metadata']['name'],
                'volume_name': pvc['spec'].get('volumeName', 'N/A'),
                'access_modes': pvc['status'].get('accessModes', 'N/A'),
                'capacity': pvc['status'].get('capacity', {}).get('storage', 'N/A'),
            })
        except KeyError as e:
            print(f"Error accediendo a un campo en el PVC {pvc['metadata']['name']}: {e}")
            pvc_info.append({
                'name': pvc['metadata']['name'],
                'volume_name': 'N/A',
                'access_modes': 'N/A',
                'capacity': 'N/A',
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
    """Obtiene los configmaps del namespace, omitiendo los que comienzan con openshift o kube-."""
    configmaps = run_command(f"kubectl get configmap -n {namespace} -o json")
    if configmaps is None:
        return []
    configmaps_json = json.loads(configmaps)
    configmap_info = []
    for configmap in configmaps_json['items']:
        configmap_name = configmap['metadata']['name']
        if not (configmap_name.startswith('openshift') or configmap_name.startswith('kube-')):
            configmap_info.append({
                'name': configmap_name,
            })
    return configmap_info

def get_pod_metrics(namespace):
    """Obtiene métricas de los pods en un namespace."""
    try:
        metrics_output = run_command(f"kubectl top pod -n {namespace} --no-headers")
        if metrics_output is None:
            print(f"Métricas no disponibles para los pods en el namespace {namespace}.")
            return {}
        
        pod_metrics = {}
        for line in metrics_output.splitlines():
            parts = line.split()
            pod_name = parts[0]
            cpu = parts[1]
            memory = parts[2]
            pod_metrics[pod_name] = {'cpu': cpu, 'memory': memory}

        return pod_metrics
    except Exception as e:
        print(f"Error obteniendo métricas para el namespace {namespace}: {e}")
        return {}

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

def get_deploymentconfigs_info(namespace):
    """Obtiene información de los DeploymentConfigs en un namespace."""
    dcs = run_command(f"oc get deploymentconfig -n {namespace} -o json")
    if dcs is None:
        return []
    dc_info = []

    dcs_json = json.loads(dcs)
    for dc in dcs_json['items']:
        dc_name = dc['metadata']['name']
        replicas = dc['spec']['replicas']
        labels = dc['metadata'].get('labels', {})
        dc_info.append({
            'deployment_name': dc_name,
            'replicas': replicas,
            'labels': labels,
            'type': 'DeploymentConfig'
        })
    return dc_info

def get_statefulsets_info(namespace):
    """Obtiene información de los StatefulSets en un namespace."""
    statefulsets = run_command(f"kubectl get statefulsets -n {namespace} -o json")
    if statefulsets is None:
        return []
    statefulset_info = []

    statefulsets_json = json.loads(statefulsets)
    for statefulset in statefulsets_json['items']:
        ss_name = statefulset['metadata']['name']
        replicas = statefulset['spec']['replicas']
        labels = statefulset['metadata'].get('labels', {})
        statefulset_info.append({
            'deployment_name': ss_name,
            'replicas': replicas,
            'labels': labels,
            'type': 'StatefulSet'
        })
    return statefulset_info

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
            'ports': ','.join([str(port['port']) for port in ports])
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
        deployments_info = get_deployments_info(namespace)
        dcs_info = get_deploymentconfigs_info(namespace)
        statefulsets_info = get_statefulsets_info(namespace)
        pod_info = get_pod_info(namespace)
        pod_metrics = get_pod_metrics(namespace)
        services_info = get_services_info(namespace)
        routes_info = get_routes_info(namespace)
        hpa_info = get_hpa_info(namespace)
        pvc_info = get_persistent_volume_claims(namespace)
        secret_info = get_secrets(namespace)
        configmap_info = get_configmaps(namespace)
        
        all_deployments_info = deployments_info + dcs_info + statefulsets_info
        
        for deployment in all_deployments_info:
            deployment_name = deployment['deployment_name']
            deployment_type = deployment.get('type', 'Deployment')
            relevant_pods = [pod for pod in pod_info if deployment_name in pod['pod_name']]
            
            # Consolidar la información relacionada con el deployment, DeploymentConfig o StatefulSet
            node_names = ','.join(set([pod['node_name'] for pod in relevant_pods]))
            pod_images = ','.join(set([pod['image'] for pod in relevant_pods]))
            pod_resources = ','.join([str(pod['resources']) for pod in relevant_pods])
            pod_cpu_usages = ','.join([pod_metrics.get(pod['pod_name'], {}).get('cpu', 'N/A') for pod in relevant_pods])
            pod_memory_usages = ','.join([pod_metrics.get(pod['pod_name'], {}).get('memory', 'N/A') for pod in relevant_pods])

            services = ','.join([service['name'] for service in services_info])
            service_ports = ','.join([service['ports'] for service in services_info])
            routes = ','.join([route['name'] for route in routes_info])
            route_hosts = ','.join([route['host'] for route in routes_info])
            hpas = ','.join([hpa['name'] for hpa in hpa_info])

            inventory.append({
                'namespace': namespace,
                'deployment_name': deployment_name,
                'deployment_type': deployment_type,
                'deployment_replicas': deployment['replicas'],
                'deployment_labels': deployment['labels'],
                'node_names': node_names,
                'pod_images': pod_images,
                'pod_resources': pod_resources,
                'pod_cpu_usages': pod_cpu_usages,
                'pod_memory_usages': pod_memory_usages,
                'services': services,
                'service_ports': service_ports,
                'routes': routes,
                'route_hosts': route_hosts,
                'hpas': hpas,
            })

        # Opcional: añadir otros recursos al inventario, pero agrupados por deployment
        for quota in get_resource_quotas(namespace):
            inventory[-1].update({
                'quota_name': quota['name'],
                'quota_limits': quota['limits']
            })

        for pv in pv_info:
            if pv['namespace'] == namespace:
                inventory[-1].update({
                    'pv_name': pv['name'],
                    'pv_capacity': pv['capacity'],
                    'pv_access_modes': pv['access_modes'],
                    'pv_reclaim_policy': pv['reclaim_policy']
                })

        for pvc in pvc_info:
            inventory[-1].update({
                'pvc_name': pvc['name'],
                'pvc_volume_name': pvc['volume_name'],
                'pvc_access_modes': pvc['access_modes'],
                'pvc_capacity': pvc['capacity']
            })

        for secret in secret_info:
            inventory[-1].update({
                'secret_name': secret['name'],
                'secret_type': secret['type']
            })

        for configmap in configmap_info:
            inventory[-1].update({
                'configmap_name': configmap['name']
            })

        node_selector = get_node_selector(namespace)
        if node_selector != 'N/A':
            inventory[-1].update({'node_selector': node_selector})

    # Obtener la fecha actual para usarla en el nombre de los archivos
    date_str = datetime.datetime.now().strftime("%Y%m%d")

    # Guardar el inventario en un archivo CSV
    with open(f'inventario_{date_str}.csv', 'w', newline='') as csvfile:
        fieldnames = [
            'namespace', 'deployment_name', 'deployment_type', 'deployment_replicas', 'deployment_labels',
            'node_names', 'pod_images', 'pod_resources', 'pod_cpu_usages', 'pod_memory_usages',
            'services', 'service_ports', 'routes', 'route_hosts', 'hpas',
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