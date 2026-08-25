from datetime import datetime, timedelta
import time

import clickhouse_connect
import requests
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from kubernetes.client import models as k8s

SUPERSET_URL = 'http://habtech-superset:8088'
SUPERSET_USER = 'admin'
SUPERSET_PASSWORD = 'admin'

CH_HOST = 'habtech-clickhouse'
CH_PORT = 8123
CH_USER = 'habtech_airflow'
CH_PASSWORD = 'habtechpass123'

EXPECTED_STAGING_TABLES = {'mfr_facilities', 'dhis2_facilities', 'org_units'}

MONITORING_ENDPOINTS = {
    'prometheus': 'http://habtech-prometheus:9090/-/healthy',
    'grafana': 'http://habtech-grafana:3000/api/health',
    'cadvisor': 'http://habtech-cadvisor:8080/healthz',
    'keycloak': 'http://habtech-keycloak:8080/health/ready',
}


def wait_for_staging_tables():
    client = clickhouse_connect.get_client(
        host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD,
    )
    deadline = time.time() + 60
    while time.time() < deadline:
        result = client.query("SHOW TABLES FROM staging")
        existing = {row[0] for row in result.result_rows}
        missing = EXPECTED_STAGING_TABLES - existing
        if not missing:
            print(f"All staging tables present: {existing}")
            return
        print(f"Waiting on staging tables: {missing}")
        time.sleep(3)
    raise Exception(f"Timed out waiting for staging tables: {EXPECTED_STAGING_TABLES - existing}")


def refresh_superset_datasets():
    session = requests.Session()
    try:
        login_resp = session.post(
            f"{SUPERSET_URL}/api/v1/security/login",
            json={
                "username": SUPERSET_USER,
                "password": SUPERSET_PASSWORD,
                "provider": "db",
                "refresh": True,
            },
            timeout=10,
        )
        login_resp.raise_for_status()
        access_token = login_resp.json().get("access_token")
        headers = {"Authorization": f"Bearer {access_token}"}

        datasets_resp = session.get(
            f"{SUPERSET_URL}/api/v1/dataset/",
            headers=headers,
            params={"q": "(filters:!((col:table_name,opr:ct,value:'')))"},
            timeout=10,
        )
        datasets_resp.raise_for_status()
        datasets = datasets_resp.json().get("result", [])

        target_tables = {"fact_facility_capacity", "dim_region"}
        refreshed = []
        for ds in datasets:
            if ds.get("table_name") in target_tables:
                ds_id = ds["id"]
                refresh_resp = session.put(
                    f"{SUPERSET_URL}/api/v1/dataset/{ds_id}/refresh",
                    headers=headers,
                    timeout=10,
                )
                if refresh_resp.status_code in (200, 201):
                    refreshed.append(ds["table_name"])

        print(f"Refreshed Superset datasets: {refreshed}")

    except Exception as e:
        print(f"Superset refresh skipped/failed (non-blocking): {e}")


def check_monitoring_stack_health():
    results = {}
    for name, url in MONITORING_ENDPOINTS.items():
        try:
            resp = requests.get(url, timeout=5)
            results[name] = f"UP ({resp.status_code})" if resp.status_code < 400 else f"DEGRADED ({resp.status_code})"
        except Exception as e:
            results[name] = f"DOWN ({e})"

    print("Monitoring/security stack health check:")
    for name, status in results.items():
        print(f"  {name}: {status}")


default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2026, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=2),
}

csv_volume = k8s.V1Volume(
    name='csv-data',
    host_path=k8s.V1HostPathVolumeSource(path='/mnt/csvdata'),
)
csv_volume_mount = k8s.V1VolumeMount(name='csv-data', mount_path='/data')

with DAG(
    dag_id='habtech_k8s_ingestion_transformation',
    default_args=default_args,
    description='Airflow-triggered Meltano ingestion + dbt transformation as Kubernetes pods',
    schedule_interval='@daily',
    catchup=False,
    tags=['meltano', 'dbt', 'kubernetes', 'habtech'],
) as dag:

    task_meltano_ingest = KubernetesPodOperator(
        task_id='meltano_ingest',
        name='meltano-ingest-af',
        namespace='default',
        image='habtech-meltano:latest',
        image_pull_policy='Never',
        cmds=['meltano', 'run', 'tap-csv', 'target-clickhouse'],
        volumes=[csv_volume],
        volume_mounts=[csv_volume_mount],
        config_file='/opt/airflow/.kube/config',
        cluster_context='minikube',
        is_delete_operator_pod=True,
        get_logs=True,
        startup_timeout_seconds=300,
    )

    task_wait_for_staging = PythonOperator(
        task_id='wait_for_staging_tables',
        python_callable=wait_for_staging_tables,
    )

    task_dbt_transform = KubernetesPodOperator(
        task_id='dbt_transform',
        name='dbt-transform-af',
        namespace='default',
        image='habtech-dbt:latest',
        image_pull_policy='Never',
        cmds=['dbt', 'run'],
        config_file='/opt/airflow/.kube/config',
        cluster_context='minikube',
        is_delete_operator_pod=True,
        get_logs=True,
        startup_timeout_seconds=300,
    )

    task_refresh_superset = PythonOperator(
        task_id='refresh_superset_datasets',
        python_callable=refresh_superset_datasets,
        trigger_rule='all_done',
    )

    task_check_monitoring = PythonOperator(
        task_id='check_monitoring_stack_health',
        python_callable=check_monitoring_stack_health,
        trigger_rule='all_done',
    )

    task_meltano_ingest >> task_wait_for_staging >> task_dbt_transform >> [task_refresh_superset, task_check_monitoring]
