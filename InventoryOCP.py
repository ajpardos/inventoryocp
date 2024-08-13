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

def get_resources(namespace, resource_type):
    """General function to fetch resources from OpenShift."""
    resources = run_command(f"kubectl get {resource_type} -n {namespace} -o json")
    if resources is None:
        return []
    return json.loads(resources)['items']

def standardize_inventory_data(data_list, standard_fields):
    """Ensure that each dictionary in data_list contains all the fields in standard_fields, filling missing ones with None."""
    return [{field: item.get(field, None) for field in standard_fields} for item in data_list]

def generate_inventory():
    """Genera un inventario de los microservicios y lo guarda en archivos CSV y JSON."""
    inventory = []
    namespaces = get_non_openshift_namespaces()
    resource_types = ['pods', 'services', 'deployments', 'routes', 'configmaps', 'secrets', 'persistentvolumeclaims']

    for namespace in namespaces:
        print(f"Processing namespace: {namespace}")
        for resource_type in resource_types:
            resources_info = get_resources(namespace, resource_type)
            for resource in resources_info:
                resource.update({'type': resource_type, 'namespace': namespace})  # Add type and namespace to each resource
                inventory.append(resource)

    # Determining all possible fields
    fieldnames = set()
    for item in inventory:
        fieldnames.update(item.keys())

    # Save to CSV and JSON, including timestamp in filenames
    date_str = datetime.datetime.now().strftime("%Y%m%d")
    with open(f'inventario_{date_str}.csv', 'w', newline='') as csvfile:
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