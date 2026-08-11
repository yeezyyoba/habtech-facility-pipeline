FROM apache/superset:latest

USER root
# Install Authlib for Keycloak and clickhouse-connect for ClickHouse
RUN pip install --no-cache-dir Authlib clickhouse-connect

USER superset