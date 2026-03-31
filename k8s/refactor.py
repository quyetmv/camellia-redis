import os
import yaml
from pathlib import Path

BASE_DIR = "/mnt/c/Users/quyetmv/workspace-pc/learning/labs/camellia-redis/k8s/deployment"

def process_file(file_path, mode):
    with open(file_path, 'r') as f:
        content = f.read()

    # Generic string replacement for app labels, selectors, and names
    content = content.replace("camellia-proxy-cluster-", "camellia-proxy-")
    content = content.replace("camellia-proxy-standalone-", "camellia-proxy-")
    
    for t in ["order", "payment", "search", "key-routing", "shared-auth"]:
        content = content.replace(f"camellia-proxy-{t}", f"camellia-proxy-{mode}-{t}")

    # Replace ConfigMap mount paths
    content = content.replace("application-cluster-", "application-")
    content = content.replace("application-standalone-", "application-")
    for t in ["key-routing", "service-order", "service-payment", "service-search"]:
        content = content.replace(f"application-{t}.yml", f"application-{mode}-{t}.yml")
    
    content = content.replace("camellia-redis-proxy.properties", "application.yml")
    content = content.replace("camellia-redis-proxy-shared-auth.properties", f"application-{mode}-shared-auth.yml")
    content = content.replace("application-shared-auth.yml", f"application-{mode}-shared-auth.yml")

    # Load YAML dynamically to modify ports array
    docs = []
    for doc in yaml.safe_load_all(content):
        if not doc: continue
        
        kind = doc.get("kind")
        if kind == "Deployment":
            # Modify container ports
            for container in doc['spec']['template']['spec']['containers']:
                new_ports = [{"containerPort": 6380, "name": "redis", "protocol": "TCP"}]
                if mode == "cluster":
                    new_ports.append({"containerPort": 16378, "name": "console", "protocol": "TCP"})
                    new_ports.append({"containerPort": 16380, "name": "cport", "protocol": "TCP"})
                else:
                    new_ports.append({"containerPort": 16379, "name": "console", "protocol": "TCP"})
                container['ports'] = new_ports
                
        elif kind == "Service":
            # Modify service ports, preserving nodePort for redis if any
            existing_redis_node_port = None
            existing_console_node_port = None
            
            for p in doc['spec']['ports']:
                if p.get('name') == 'redis' and 'nodePort' in p:
                    existing_redis_node_port = p['nodePort']
                if p.get('name') == 'console' and 'nodePort' in p:
                    existing_console_node_port = p['nodePort']
            
            new_ports = [{"name": "redis", "port": 6380, "targetPort": 6380}]
            if existing_redis_node_port:
                new_ports[0]['nodePort'] = existing_redis_node_port
                
            if mode == "cluster":
                c = {"name": "console", "port": 16378, "targetPort": 16378}
                if existing_console_node_port: c['nodePort'] = existing_console_node_port
                new_ports.append(c)
                new_ports.append({"name": "cport", "port": 16380, "targetPort": 16380})
            else:
                c = {"name": "console", "port": 16379, "targetPort": 16379}
                if existing_console_node_port: c['nodePort'] = existing_console_node_port
                new_ports.append(c)
            
            doc['spec']['ports'] = new_ports
            
        docs.append(doc)

    if docs:
        return yaml.dump_all(docs, sort_keys=False)
    return content

def run(mode):
    target_dir = Path(BASE_DIR) / mode
    if not target_dir.exists():
        return
        
    for root, dirs, files in os.walk(target_dir):
        for fname in files:
            path = Path(root) / fname
            if fname == "kustomization.yaml":
                with open(path, 'r') as f:
                    content = f.read()
                content = content.replace("camellia-proxy-cluster-", "camellia-proxy-")
                content = content.replace("camellia-proxy-standalone-", "camellia-proxy-")
                for t in ["key-routing-deployment", "key-routing-service", "services-deployments", "services-services", "shared-auth-deployment", "shared-auth-service"]:
                    content = content.replace(f"camellia-proxy-{t}.yaml", f"camellia-proxy-{mode}-{t}.yaml")
                with open(path, 'w') as f:
                    f.write(content)
                continue
                
            if not fname.endswith(".yaml"):
                continue
                
            if not fname.startswith("camellia-proxy-"):
                continue

            print(f"Refactoring {path}")
            new_content = process_file(path, mode)
            
            new_fname = fname.replace("camellia-proxy-cluster-", "camellia-proxy-").replace("camellia-proxy-standalone-", "camellia-proxy-")
            for t in ["key-routing-deployment", "key-routing-service", "services-deployments", "services-services", "shared-auth-deployment", "shared-auth-service"]:
                new_fname = new_fname.replace(f"camellia-proxy-{t}.yaml", f"camellia-proxy-{mode}-{t}.yaml")
                
            new_path = Path(root) / new_fname
            with open(new_path, 'w') as f:
                f.write(new_content)
                
            if str(new_path) != str(path):
                os.remove(path)

if __name__ == "__main__":
    run("cluster")
    run("standalone")
    print("DONE Refactoring!")
