import subprocess
import json
import csv
import getpass
import datetime

def run_command(command):
    """Ejecuta un comando en la terminal y devuelve la salida."""
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
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
        pod_name = pod['metadata']['name']
        node_name = pod['spec'].get('nodeName', 'N/A')
        labels = pod['metadata'].get('labels', {})
        resources = pod['spec']['containers'][0].get('resources', {})
        readiness_probe = pod['spec']['containers'][0].get('readinessProbe', {})
        liveness_probe = pod['spec']['containers'][0].get('livenessProbe', {})
        image = pod['spec']['containers'][0]['image']
        pod_info.append({
            'name': pod_name,
            'node_name': node_name,
            'labels': labels,
            'resources': resources,
            'readiness_probe': readiness_probe,
            'liveness_probe': liveness_probe,
            'image': image
        })
    return pod_info

def get_persistent_volumes(namespace):
    """Obtiene los volúmenes persistentes del namespace."""
    pvs = run_command("kubectl get pv -o json")
    if pvs is None:
        return []
    pvs_json = json.loads(pvs)
    pv_info = []
    for pv in pvs_json['items']:
        claim_ref = pv['spec'].get('claimRef')
        if claim_ref and claim_ref.get('namespace') == namespace:
            pv_info.append({
                'name': pv['metadata']['name'],
                'capacity': pv['spec']['capacity']['storage'],
                'access_modes': pv['spec']['accessModes'],
                'reclaim_policy': pv['spec']['persistentVolumeReclaimPolicy'],
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
    """Obtiene los secretos del namespace."""
    secrets = run_command(f"kubectl get secret -n {namespace} -o json")
    if secrets is None:
        return []
    secrets_json = json.loads(secrets)
    secret_info = []
    for secret in secrets_json['items']:
        secret_info.append({
            'name': secret['metadata']['name'],
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
        data_keys = list(configmap.get('data', {}).keys())
        configmap_info.append({
            'name': configmap['metadata']['name'],
            'data_keys': data_keys,
        })
    return configmap_info

# Similar functions for other resources would go here...

def generate_inventory():
    """Genera un inventario de los microservicios y lo guarda en archivos CSV y JSON."""
    inventory = []

    namespaces = get_non_openshift_namespaces()
    for namespace in namespaces:
        print(f"Processing namespace: {namespace}")
        pod_info = get_pod_info(namespace)
        pv_info = get_persistent_volumes(namespace)
        pvc_info = get_persistent_volume_claims(namespace)
        secret_info = get_secrets(namespace)
        configmap_info = get_configmaps(namespace)
        # Add other resources to inventory as needed...

        # Append all collected data to the inventory list
        inventory.extend(pod_info + pv_info + pvc_info + secret_info + configmap_info)
        # More appends as necessary...

    # Save to CSV and JSON, including timestamp in filenames
    date_str = datetime.datetime.now().strftime("%Y%m%d")
    with open(f'inventario_{date_str}.csv', 'w', newline='') as csvfile:
        fieldnames = list(inventory[0].keys()) if inventory else []
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for item in inventory:
            writer.writerow(item)

    with open(f'inventario_{date_str}.json', 'w') as jsonfile:
        json.dump(inventory, jsonfile, indent=2)

if __name__ == "__main__":
    api_url = input("Ingrese la URL del clúster de OpenShift: ")
    username = input("Ingrese el nombre de usuario: ")
    password = getpass.getpass("Ingrese la contraseña: ")
    login_to_openshift(api_url, username, password)
    generate_inventory()