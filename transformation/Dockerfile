FROM python:3.11-slim

RUN pip install --no-cache-dir dbt-clickhouse

WORKDIR /project
COPY . .
COPY profiles.yml /root/.dbt/profiles.yml

CMD ["dbt", "run"]
