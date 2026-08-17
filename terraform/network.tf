resource "docker_network" "habtech_net" {
  name   = "eyobnebyou_habtech_net"
  driver = "bridge"
  ipam_config {
    subnet  = "172.28.0.0/16"
    gateway = "172.28.0.1"
  }
}
