import os
import sys
import requests

SUPERSET_URL = os.environ.get("SUPERSET_URL", "http://superset:8088")
SUPERSET_USER = os.environ.get("SUPERSET_USER", "admin")
SUPERSET_PASSWORD = os.environ.get("SUPERSET_PASSWORD", "admin")

TARGET_TABLES = {
    "fact_facility_capacity",
    "dim_region",
    "dim_zone_woreda",
    "dim_ownership_type",
}


def refresh_superset_datasets():
    session = requests.Session()
    login_resp = session.post(
        f"{SUPERSET_URL}/api/v1/security/login",
        json={
            "username": SUPERSET_USER,
            "password": SUPERSET_PASSWORD,
            "provider": "db",
            "refresh": True,
        },
        timeout=30,
    )
    login_resp.raise_for_status()
    access_token = login_resp.json().get("access_token")
    headers = {"Authorization": f"Bearer {access_token}"}

    datasets_resp = session.get(
        f"{SUPERSET_URL}/api/v1/dataset/",
        headers=headers,
        params={"q": "(filters:!((col:table_name,opr:ct,value:'')))"},
        timeout=30,
    )
    datasets_resp.raise_for_status()
    datasets = datasets_resp.json().get("result", [])

    refreshed = []
    failed = []
    for ds in datasets:
        if ds.get("table_name") in TARGET_TABLES:
            ds_id = ds["id"]
            refresh_resp = session.put(
                f"{SUPERSET_URL}/api/v1/dataset/{ds_id}/refresh",
                headers=headers,
                timeout=30,
            )
            if refresh_resp.status_code in (200, 201):
                refreshed.append(ds["table_name"])
            else:
                failed.append((ds["table_name"], refresh_resp.status_code, refresh_resp.text))

    print(f"Refreshed Superset datasets: {refreshed}")
    if failed:
        print(f"Failed to refresh: {failed}")
        sys.exit(1)

    missing = TARGET_TABLES - set(refreshed)
    if missing:
        print(f"WARNING: datasets not found in Superset (need to be created manually first): {missing}")


if __name__ == "__main__":
    refresh_superset_datasets()
