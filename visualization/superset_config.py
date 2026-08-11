import os
from flask_appbuilder.security.manager import AUTH_OAUTH
from superset.security import SupersetSecurityManager

# ----------------------------------------------------
# Superset Core Settings
# ----------------------------------------------------
SECRET_KEY = os.environ.get(
    "SUPERSET_SECRET_KEY",
    "a-long-random-secret-for-my-superset-installation-9f82k3x7"
)

AUTH_TYPE = AUTH_OAUTH
AUTH_USER_REGISTRATION = True
AUTH_USER_REGISTRATION_ROLE = "Alpha"

# ----------------------------------------------------
# Keycloak Claims Mapping
# ----------------------------------------------------
class KeycloakSecurityManager(SupersetSecurityManager):
    def oauth_user_info(self, provider, response=None):
        if provider == "keycloak":
            me = self.appbuilder.sm.oauth_remotes[provider].get("userinfo").json()
            return {
                "name": me.get("name", ""),
                "email": me.get("email", ""),
                "id": me.get("sub", ""),
                "username": me.get("preferred_username", me.get("email")),
                "first_name": me.get("given_name", ""),
                "last_name": me.get("family_name", ""),
            }
        return super().oauth_user_info(provider, response)

CUSTOM_SECURITY_MANAGER = KeycloakSecurityManager

# ----------------------------------------------------
# Keycloak Provider Configuration
# ----------------------------------------------------
KEYCLOAK_INTERNAL_BASE = "http://host.docker.internal:8080/realms/habtech-demo"
KEYCLOAK_EXTERNAL_BASE = "http://localhost:8080/realms/habtech-demo"

OAUTH_PROVIDERS = [
    {
        "name": "keycloak",
        "icon": "fa-key",
        "token_key": "access_token",
        "remote_app": {
            "client_id": "superset",
            "client_secret": "HYlRXGlgKzogiL50ZOHt2dzrK36xa90g",
            "client_kwargs": {
                "scope": "openid profile email",
            },
            "server_metadata_url": f"{KEYCLOAK_INTERNAL_BASE}/.well-known/openid-configuration",
            "api_base_url": f"{KEYCLOAK_INTERNAL_BASE}/protocol/openid-connect/",
            "access_token_url": f"{KEYCLOAK_INTERNAL_BASE}/protocol/openid-connect/token",
            "authorize_url": f"{KEYCLOAK_EXTERNAL_BASE}/protocol/openid-connect/auth",
        },
    }
]