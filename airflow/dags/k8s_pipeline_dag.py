from datetime import datetime, timedelta
import time

import clickhouse_connect
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from kubernetes.client import models as k8s

CH_HOST = 'host.docker.internal'
CH_PORT = 8123
CH_USER = 'habtech_airflow'
CH_PASSWORD = 'habtechpass123'

EXPECTED_STAGING_TABLES = {'mfr_facilities', 'dhis2_facilities', 'org_units'}


def wait_for_staging_tables():
    client = clickhouse_connect.get_client(
        host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD,
    )
    deadline = time.time() + 300
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
    description='Airflow-triggered Meltano ingestion + dbt transformation + Superset refresh + monitoring check, all as Kubernetes pods',
    schedule_interval='@daily',
    catchup=False,
    tags=['meltano', 'dbt', 'superset', 'monitoring', 'kubernetes', 'habtech'],
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

    task_refresh_superset = KubernetesPodOperator(
        task_id='refresh_superset_datasets',
        name='superset-refresh-af',
        namespace='default',
        image='habtech-superset-refresh:latest',
        image_pull_policy='Never',
        env_vars={
            'SUPERSET_URL': 'http://superset:8088',
            'SUPERSET_USER': 'admin',
            'SUPERSET_PASSWORD': 'admin',
        },
        config_file='/opt/airflow/.kube/config',
        cluster_context='minikube',
        is_delete_operator_pod=True,
        get_logs=True,
        startup_timeout_seconds=300,
        trigger_rule='all_done',
    )

    task_check_monitoring = KubernetesPodOperator(
        task_id='check_monitoring_stack_health',
        name='monitoring-check-af',
        namespace='default',
        image='habtech-monitoring-check:latest',
        image_pull_policy='Never',
        env_vars={
            'PROMETHEUS_URL': 'http://host.docker.internal:9090/-/healthy',
            'GRAFANA_URL': 'http://host.docker.internal:3000/api/health',
            'CADVISOR_URL': 'http://host.docker.internal:8082/healthz',
            'KEYCLOAK_URL': 'http://host.docker.internal:8080/realms/master/.well-known/openid-configuration',
        },
        config_file='/opt/airflow/.kube/config',
        cluster_context='minikube',
        is_delete_operator_pod=True,
        get_logs=True,
        startup_timeout_seconds=300,
        trigger_rule='all_done',
    )

    task_meltano_ingest >> task_wait_for_staging >> task_dbt_transform >> [task_refresh_superset, task_check_monitoring]
