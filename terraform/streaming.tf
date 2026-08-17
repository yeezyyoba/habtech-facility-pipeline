# --- ZOOKEEPER ---
resource "docker_image" "zookeeper" {
  name         = "confluentinc/cp-zookeeper:7.5.0"
  keep_locally = true
}

resource "docker_container" "zookeeper" {
  name  = "zookeeper"
  image = docker_image.zookeeper.image_id

  env = [
    "ZOOKEEPER_CLIENT_PORT=2181"
  ]

  networks_advanced {
    name         = docker_network.habtech_net.name
    ipv4_address = "172.28.0.2"
  }

  memory = 384
}

# --- KAFKA ---
resource "docker_image" "kafka" {
  name         = "confluentinc/cp-kafka:7.5.0"
  keep_locally = true
}

resource "docker_container" "kafka" {
  name  = "kafka"
  image = docker_image.kafka.image_id

  env = [
    "KAFKA_BROKER_ID=1",
    "KAFKA_ZOOKEEPER_CONNECT=172.28.0.2:2181",
    "KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://kafka:29092,PLAINTEXT_HOST://localhost:9092",
    "KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT",
    "KAFKA_INTER_BROKER_LISTENER_NAME=PLAINTEXT",
    "KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1",
    "KAFKA_HEAP_OPTS=-Xmx384m -Xms256m"
  ]

  networks_advanced {
    name         = docker_network.habtech_net.name
    ipv4_address = "172.28.0.3"
  }

  ports {
    internal = 9092
    external = 9092
  }

  memory     = 512
  depends_on = [docker_container.zookeeper]
}

# --- DEBEZIUM CONNECT ---
resource "docker_image" "debezium" {
  name         = "debezium/connect:2.4"
  keep_locally = true
}

resource "docker_container" "debezium_connect" {
  name  = "debezium_connect"
  image = docker_image.debezium.image_id

  env = [
    "BOOTSTRAP_SERVERS=172.28.0.3:29092",
    "GROUP_ID=1",
    "CONFIG_STORAGE_TOPIC=connect_configs",
    "OFFSET_STORAGE_TOPIC=connect_offsets",
    "STATUS_STORAGE_TOPIC=connect_statuses"
  ]

  networks_advanced {
    name         = docker_network.habtech_net.name
    ipv4_address = "172.28.0.5"
  }

  ports {
    internal = 8083
    external = 8083
  }

  memory     = 512
  depends_on = [docker_container.kafka, docker_container.postgres]
}
