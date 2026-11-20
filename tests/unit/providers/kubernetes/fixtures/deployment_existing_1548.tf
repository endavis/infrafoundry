resource "kubernetes_deployment" "web_app" {
  metadata {
    name      = "web-app"
    namespace = "apps"

    labels = {
      "tier" = "frontend"
      "team" = "platform"
    }
  }

  spec {
    replicas = 3

    selector {
      match_labels = {
        app = "web-app"
      }
    }

    template {
      metadata {
        labels = {
          app = "web-app"
          "tier" = "frontend"
          "team" = "platform"
        }
      }

      spec {
        container {
          name  = "web"
          image = "nginx:1.27"

          port {
            container_port = 80
            name = "http"
            protocol = "TCP"
          }
          port {
            container_port = 8443
          }

          env {
            name  = "MODE"
            value = "prod"
          }
          env {
            name  = "LEVEL"
            value = "info"
          }

          resources {
            limits = {
              "cpu" = "500m"
              "memory" = "256Mi"
            }
            requests = {
              "cpu" = "100m"
              "memory" = "128Mi"
            }
          }
        }
        container {
          name  = "sidecar"
          image = "busybox:1.36"



        }
      }
    }
  }

  depends_on = [
    kubernetes_namespace.apps,
    kubernetes_config_map.settings,
    kubernetes_secret.extra,
  ]
}

resource "kubernetes_deployment" "bare_app" {
  metadata {
    name      = "bare-app"
    namespace = "default"

  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "bare-app"
      }
    }

    template {
      metadata {
        labels = {
          app = "bare-app"
        }
      }

      spec {
        container {
          name  = "app"
          image = "alpine:3"



        }
      }
    }
  }

  depends_on = [
    kubernetes_namespace.apps,
    kubernetes_config_map.settings,
  ]
}
