# --- POSTGRES (PRIMARY APP DB) ---
resource "docker_image" "postgres_15" {
  name         = "postgres:15"
  keep_locally = true
}

resource "docker_container" "postgres" {
  name  = "postgres"
  image = docker_image.postgres_15.image_id

  env = [
    "POSTGRES_USER=postgres",
    "POSTGRES_PASSWORD=postgrespassword",
    "POSTGRES_DB=app_db"
  ]

  networks_advanced {
    name         = docker_network.habtech_net.name
    ipv4_address = "172.28.0.4"
  }

  ports {
    internal = 5432
    external = 5432
  }

  memory = 512
}

# --- CLICKHOUSE ---
resource "docker_image" "clickhouse" {
  name         = "clickhouse/clickhouse-server:26.6"
  keep_locally = true
}

resource "docker_container" "clickhouse" {
  name  = "habtech-clickhouse"
  image = docker_image.clickhouse.image_id

  networks_advanced {
    name         = docker_network.habtech_net.name
    ipv4_address = "172.28.0.6"
  }

  ports {
    internal = 8123
    external = 8123
  }
  ports {
    internal = 9000
    external = 9000
  }

  memory = 1536
}

# --- MINIO ---
resource "docker_image" "minio" {
  name         = "minio/minio:RELEASE.2024-01-18T22-51-28Z"
  keep_locally = true
}

resource "docker_container" "minio" {
  name    = "habtech-minio"
  image   = docker_image.minio.image_id
  command = ["server", "/data", "--console-address", ":9001"]

  env = [
    "MINIO_ROOT_USER=minioadmin",
    "MINIO_ROOT_PASSWORD=minioadminpassword"
  ]

  networks_advanced {
    name         = docker_network.habtech_net.name
    ipv4_address = "172.28.0.8"
  }

  ports {
    internal = 9000
    external = 9001
  }
  ports {
    internal = 9001
    external = 9002
  }

  memory = 512
}
