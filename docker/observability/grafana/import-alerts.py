#!/usr/bin/env python3
"""Load a Grafana alert provisioning file into a running Grafana over its API.

For Grafana instances whose provisioning directory we cannot write to, such as
Opsview. The file stays the single definition; this pushes it.

    set GRAFANA_URL=https://<grafana host>
    set GRAFANA_TOKEN=<service account token with the Editor role>
    python import-alerts.py provisioning/alerting/vault.yml --datasource-url prometheus.m8flow.ai
    python import-alerts.py provisioning/alerting/vault.yml --datasource-url prometheus.m8flow.ai --apply

Dry run unless --apply is given. The token is read from the environment and
never printed.

The file's datasourceUid is the local one ("prometheus"). The target Grafana's
UID differs, so it is looked up by URL and substituted. Rules are sent with
X-Disable-Provenance so they stay editable in the UI afterwards.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

import yaml


def api(base, token, method, path, body=None, headers=None):
    req = urllib.request.Request(base.rstrip("/") + path, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def seconds(duration):
    unit = {"s": 1, "m": 60, "h": 3600}[duration[-1]]
    return int(duration[:-1]) * unit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--datasource-url", help="substring of the target Prometheus datasource URL")
    ap.add_argument("--datasource-uid", help="use this UID instead of looking one up")
    ap.add_argument("--folder", default=None, help="override the folder title in the file")
    ap.add_argument("--apply", action="store_true", help="send it; without this, only print")
    a = ap.parse_args()

    doc = yaml.safe_load(open(a.file, encoding="utf-8"))
    base = os.environ.get("GRAFANA_URL", "")
    token = os.environ.get("GRAFANA_TOKEN", "")
    if a.apply and not (base and token):
        sys.exit("GRAFANA_URL and GRAFANA_TOKEN must be set to apply")

    # 1. Datasource UID on the target
    ds_uid = a.datasource_uid
    if not ds_uid:
        if not (base and token):
            sys.exit("set GRAFANA_URL and GRAFANA_TOKEN, or pass --datasource-uid")
        status, sources = api(base, token, "GET", "/api/datasources")
        if status != 200:
            sys.exit(f"listing datasources failed: {status} {sources}")
        prom = [s for s in sources if s.get("type") == "prometheus"]
        match = [s for s in prom if a.datasource_url and a.datasource_url in (s.get("url") or "")]
        if len(match) != 1:
            print("Prometheus datasources on the target:")
            for s in prom:
                print(f"  uid={s['uid']:<24} name={s['name']:<30} url={s.get('url')}")
            sys.exit(f"need exactly one match for --datasource-url={a.datasource_url!r}, found {len(match)}")
        ds_uid = match[0]["uid"]
    print(f"datasource uid: {ds_uid}")

    for group in doc["groups"]:
        folder_title = a.folder or group["folder"]

        # 2. Folder, created if missing
        folder_uid = "<new>"
        if base and token:
            status, folders = api(base, token, "GET", "/api/folders?limit=1000")
            if status != 200:
                sys.exit(f"listing folders failed: {status} {folders}")
            found = [f for f in folders if f["title"] == folder_title]
            if found:
                folder_uid = found[0]["uid"]
            elif a.apply:
                status, created = api(base, token, "POST", "/api/folders", {"title": folder_title})
                if status not in (200, 201):
                    sys.exit(f"creating folder failed: {status} {created}")
                folder_uid = created["uid"]
        print(f"folder: {folder_title} ({folder_uid})")

        # 3. Rules, datasource substituted
        rules = []
        for r in group["rules"]:
            data = []
            for q in r["data"]:
                q = dict(q)
                if q["datasourceUid"] != "__expr__":
                    q["datasourceUid"] = ds_uid
                    q["model"] = dict(q["model"], datasource={"type": "prometheus", "uid": ds_uid})
                q.setdefault("relativeTimeRange", {"from": 0, "to": 0})
                data.append(q)
            rules.append({
                "uid": r["uid"], "title": r["title"], "condition": r["condition"], "data": data,
                "for": r.get("for", "0m"), "noDataState": r["noDataState"], "execErrState": r["execErrState"],
                "labels": r.get("labels", {}), "annotations": r.get("annotations", {}),
                "folderUID": folder_uid, "ruleGroup": group["name"], "orgID": group.get("orgId", 1),
                "isPaused": False,
            })
        body = {"title": group["name"], "folderUid": folder_uid,
                "interval": seconds(group["interval"]), "rules": rules}

        print(f"group: {group['name']}, every {group['interval']}, {len(rules)} rules")
        for r in rules:
            print(f"  {r['uid']:<24} {r['labels'].get('severity', ''):<9} {r['title']}")

        if not a.apply:
            print("dry run: nothing sent. Re-run with --apply.")
            continue

        # 4. PUT the whole group: creates or updates every rule in it, idempotently
        path = f"/api/v1/provisioning/folder/{folder_uid}/rule-groups/{urllib.parse.quote(group['name'])}"
        status, resp = api(base, token, "PUT", path, body, {"X-Disable-Provenance": "true"})
        if status not in (200, 201, 202):
            sys.exit(f"loading group failed: {status} {resp}")
        print(f"loaded: {len(rules)} rules into {folder_title}/{group['name']}")


if __name__ == "__main__":
    main()
