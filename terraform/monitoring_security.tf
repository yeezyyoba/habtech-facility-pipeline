# --- KEYCLOAK ---
resource "docker_image" "keycloak" {
  name         = "quay.io/keycloak/keycloak:23.0.4"
  keep_locally = true
}

resource "docker_container" "keycloak" {
  name    = "habtech-keycloak"
  image   = docker_image.keycloak.image_id
  command = ["start-dev"]

  env = [
    "KEYCLOAK_ADMIN=admin",
    "KEYCLOAK_ADMIN_PASSWORD=adminpassword"
  ]

  networks_advanced {
    name         = docker_network.habtech_net.name
    ipv4_address = "172.28.0.9"
  }

  ports {
    internal = 8080
    external = 8080
  }

  memory = 600
}

# --- PROMETHEUS ---
resource "docker_image" "prometheus" {
  name         = "prom/prometheus:v2.49.1"
  keep_locally = true
}

resource "docker_container" "prometheus" {
  name  = "habtech-prometheus"
  image = docker_image.prometheus.image_id

  networks_advanced {
    name         = docker_network.habtech_net.name
    ipv4_address = "172.28.0.10"
  }

  ports {
    internal = 9090
    external = 9090
  }

  memory = 256
}

# --- GRAFANA ---
resource "docker_image" "grafana" {
  name         = "grafana/grafana:10.2.3"
  keep_locally = true
}

resource "docker_container" "grafana" {
  name  = "habtech-grafana"
  image = docker_image.grafana.image_id

  networks_advanced {
    name         = docker_network.habtech_net.name
    ipv4_address = "172.28.0.11"
  }

  ports {
    internal = 3000
    external = 3000
  }

  memory = 256
}

# --- CADVISOR ---
resource "docker_image" "cadvisor" {
  name         = "gcr.io/cadvisor/cadvisor:v0.47.2"
  keep_locally = true
}

resource "docker_container" "cadvisor" {
  name  = "habtech-cadvisor"
  image = docker_image.cadvisor.image_id

  volumes {
    host_path      = "/"
    container_path = "/rootfs"
    read_only      = true
  }
  volumes {
    host_path      = "/var/run"
    container_path = "/var/run"
    read_only      = true
  }
  volumes {
    host_path      = "/sys"
    container_path = "/sys"
    read_only      = true
  }
  volumes {
    host_path      = "/var/lib/docker"
    container_path = "/var/lib/docker"
    read_only      = true
  }

  networks_advanced {
    name         = docker_network.habtech_net.name
    ipv4_address = "172.28.0.12"
  }

  ports {
    internal = 8080
    external = 8082
  }

  memory = 256
}
