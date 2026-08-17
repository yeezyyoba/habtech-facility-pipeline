variable "airflow_proj_dir" {
  type        = string
  default     = "/Users/eyobnebyou/habtech data/airflow"
  description = "Base path to airflow directory containing dags, logs, config, plugins"
}

# --- AIRFLOW POSTGRES METADB ---
resource "docker_image" "postgres_13" {
  name         = "postgres:13"
  keep_locally = true
}

resource "docker_volume" "airflow_postgres_data" {
  name = "airflow_postgres_data"
}

resource "docker_container" "airflow_metadb" {
  name  = "airflow-metadb"
  image = docker_image.postgres_13.image_id

  env = [
    "POSTGRES_USER=airflow",
    "POSTGRES_PASSWORD=airflow",
    "POSTGRES_DB=airflow"
  ]

  volumes {
    volume_name    = docker_volume.airflow_postgres_data.name
    container_path = "/var/lib/postgresql/data"
  }

  networks_advanced {
    name         = docker_network.habtech_net.name
    ipv4_address = "172.28.10.2"
  }

  healthcheck {
    test         = ["CMD", "pg_isready", "-U", "airflow"]
    interval     = "10s"
    retries      = 5
    start_period = "5s"
  }

  memory = 384
}

# --- AIRFLOW WEBSERVER ---
resource "docker_container" "airflow_webserver" {
  name    = "airflow-webserver"
  image   = "airflow-airflow-webserver:latest"
  command = ["webserver"]
  user    = "50000:0"

  env = [
    "AIRFLOW__CORE__EXECUTOR=LocalExecutor",
    "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow:airflow@172.28.10.2/airflow",
    "AIRFLOW__CORE__FERNET_KEY=",
    "AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION=true",
    "AIRFLOW__CORE__LOAD_EXAMPLES=false",
    "AIRFLOW__API__AUTH_BACKENDS=airflow.api.auth.backend.basic_auth,airflow.api.auth.backend.session",
    "AIRFLOW__SCHEDULER__ENABLE_HEALTH_CHECK=true"
  ]

  volumes {
    host_path      = "${var.airflow_proj_dir}/dags"
    container_path = "/opt/airflow/dags"
  }
  volumes {
    host_path      = "${var.airflow_proj_dir}/logs"
    container_path = "/opt/airflow/logs"
  }
  volumes {
    host_path      = "${var.airflow_proj_dir}/config"
    container_path = "/opt/airflow/config"
  }
  volumes {
    host_path      = "${var.airflow_proj_dir}/plugins"
    container_path = "/opt/airflow/plugins"
  }

  networks_advanced {
    name         = docker_network.habtech_net.name
    ipv4_address = "172.28.10.3"
  }

  ports {
    internal = 8080
    external = 8081
  }

  memory     = 512
  depends_on = [docker_container.airflow_metadb]
}

# --- AIRFLOW SCHEDULER ---
resource "docker_container" "airflow_scheduler" {
  name    = "airflow-scheduler"
  image   = "airflow-airflow-scheduler:latest"
  command = ["scheduler"]
  user    = "50000:0"

  env = [
    "AIRFLOW__CORE__EXECUTOR=LocalExecutor",
    "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow:airflow@172.28.10.2/airflow",
    "AIRFLOW__CORE__FERNET_KEY=",
    "AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION=true",
    "AIRFLOW__CORE__LOAD_EXAMPLES=false",
    "AIRFLOW__API__AUTH_BACKENDS=airflow.api.auth.backend.basic_auth,airflow.api.auth.backend.session",
    "AIRFLOW__SCHEDULER__ENABLE_HEALTH_CHECK=true"
  ]

  volumes {
    host_path      = "${var.airflow_proj_dir}/dags"
    container_path = "/opt/airflow/dags"
  }
  volumes {
    host_path      = "${var.airflow_proj_dir}/logs"
    container_path = "/opt/airflow/logs"
  }
  volumes {
    host_path      = "${var.airflow_proj_dir}/config"
    container_path = "/opt/airflow/config"
  }
  volumes {
    host_path      = "${var.airflow_proj_dir}/plugins"
    container_path = "/opt/airflow/plugins"
  }

  networks_advanced {
    name         = docker_network.habtech_net.name
    ipv4_address = "172.28.10.4"
  }

  memory     = 512
  depends_on = [docker_container.airflow_metadb]
}
