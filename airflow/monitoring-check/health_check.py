import os
import sys
import requests

MONITORING_ENDPOINTS = {
    'prometheus': os.environ.get('PROMETHEUS_URL', 'http://habtech-prometheus:9090/-/healthy'),
    'grafana': os.environ.get('GRAFANA_URL', 'http://habtech-grafana:3000/api/health'),
    'cadvisor': os.environ.get('CADVISOR_URL', 'http://habtech-cadvisor:8080/healthz'),
    'keycloak': os.environ.get('KEYCLOAK_URL', 'http://keycloak:8080/health/ready'),
}


def check_monitoring_stack_health():
    results = {}
    any_down = False
    for name, url in MONITORING_ENDPOINTS.items():
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code < 400:
                results[name] = f"UP ({resp.status_code})"
            else:
                results[name] = f"DEGRADED ({resp.status_code})"
                any_down = True
        except Exception as e:
            results[name] = f"DOWN ({e})"
            any_down = True

    print("Monitoring/security stack health check:")
    for name, status in results.items():
        print(f"  {name}: {status}")

    if any_down:
        print("One or more services are down or degraded.")
        # Non-blocking by default — change to sys.exit(1) if you want the Job to fail the DAG on any DOWN service
    else:
        print("All monitored services healthy.")


if __name__ == "__main__":
    check_monitoring_stack_health()
