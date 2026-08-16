from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
import clickhouse_connect

def test_clickhouse_connection():
    client = clickhouse_connect.get_client(
        host='host.docker.internal',
        port=8123,
        username='airflow_user',
        password='airflowpass123',
    )
    result = client.query('SELECT 1')
    print(f"ClickHouse connection successful. Result: {result.result_rows}")
    return result.result_rows

with DAG(
    dag_id='clickhouse_auth_test',
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=['clickhouse', 'test'],
) as dag:
    test_connection = PythonOperator(
        task_id='test_clickhouse_connection',
        python_callable=test_clickhouse_connection,
    )
