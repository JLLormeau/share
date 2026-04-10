#!/usr/bin/env python3
import sys
import os
import time
import requests

# ----------------------------------
# CONFIG & ENV
# ----------------------------------
DT_TENANT_URL = os.getenv("DT_TENANT_URL")
DT_TOKEN_API = os.getenv("DT_TOKEN_API")

if not DT_TENANT_URL or not DT_TOKEN_API:
    print("[ERROR] Missing DT_TENANT_URL or DT_TOKEN_API")
    sys.exit(1)

HEADERS_JSON = {
    "Accept": "application/json; charset=utf-8",
    "Authorization": f"Api-Token {DT_TOKEN_API}"
}

HEADERS_METRIC = {
    "Content-Type": "text/plain; charset=utf-8",
    "Authorization": f"Api-Token {DT_TOKEN_API}"
}

# ----------------------------------
# ARGS
# ----------------------------------
if len(sys.argv) < 3:
    print("Usage: script.py <STATS> \"<PARCOURS> <ALERT_TYPE>\" [PERIOD]")
    print("STATS = OPEN | RESOLVED")
    sys.exit(1)

stats = sys.argv[1].upper()
problem_title = sys.argv[2]
period = sys.argv[3] if len(sys.argv) >= 4 else "now-30m"

if stats not in ["OPEN", "RESOLVED"]:
    print("[ERROR] stats must be OPEN or RESOLVED")
    sys.exit(1)

# Mapping stats -> Dynatrace status
status_api = "ACTIVE" if stats == "OPEN" else "CLOSED"

print(f"[INFO] stats={stats}, status_api={status_api}, period={period}")

# ----------------------------------
# STEP 1 - Parse problem_title
# ----------------------------------
try:
    parcours, alert_burnrate = problem_title.split(" ", 1)
except ValueError:
    print("[ERROR] problem_title must contain a space")
    sys.exit(1)

print(f"[INFO] parcours={parcours}, alert_burnrate={alert_burnrate}")

# ----------------------------------
# STEP 2 - Query problems API
# ----------------------------------
entity_selector = (
    'type(service_method),'
    f'tag("parcours:{parcours}")'
)

params = {
    "from": period,
    "status": status_api,
    "entitySelector": entity_selector
}

url = f"{DT_TENANT_URL}/api/v2/problems"

print(f"[INFO] Calling Problems API: from={period}, status={status_api}")
r = requests.get(url, headers=HEADERS_JSON, params=params)

if r.status_code != 200:
    print(f"[ERROR] Problems API failed: {r.status_code} {r.text}")
    sys.exit(1)

data = r.json()
problems = data.get("problems", [])
total_count = data.get("totalCount", 0)

print(f"[INFO] totalCount={total_count}")

if total_count == 0:
    print("[INFO] No problem found, nothing to send")
    sys.exit(0)

# ----------------------------------
# STEP 3 - Compute metrics
# ----------------------------------
now_ts_ms = int(time.time() * 1000)
oldest_start_ms = min(p["startTime"] for p in problems)

duration_sec = int((now_ts_ms - oldest_start_ms) / 1000)
metrics = []

if stats == "OPEN":
    metrics.append(
        f'kpi.slo.davis_problem,parcours={parcours},alert_burnrate={alert_burnrate} {total_count}'
    )
    metrics.append(
        f'kpi.slo.mttd,parcours={parcours},alert_burnrate={alert_burnrate} {duration_sec}'
    )
else:
    metrics.append(
        f'kpi.slo.mttr,parcours={parcours},alert_burnrate={alert_burnrate} {duration_sec}'
    )

print(f"[INFO] duration_sec={duration_sec}")

# ----------------------------------
# STEP 4 - Push metrics to Dynatrace
# ----------------------------------
metric_url = f"{DT_TENANT_URL}/api/v2/metrics/ingest"

for metric in metrics:
    print(f"[INFO] Sending metric: {metric}")
    resp = requests.post(
        metric_url,
        headers=HEADERS_METRIC,
        data=metric.encode("utf-8")
    )

    if resp.status_code not in (200, 202):
        print(f"[ERROR] Metric ingest failed: {resp.status_code} {resp.text}")
    else:
        print("[OK] Metric ingested")

print("[INFO] Done")