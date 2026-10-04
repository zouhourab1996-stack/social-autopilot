#!/usr/bin/env python3
"""
Monthly Pinterest token refresh — swaps the access token before its 30-day
expiry and updates the GitHub secret in place. Runs on a schedule; the
refresh token itself is long-lived (about a year) and rotates on use.

Env (from GitHub Actions secrets):
  PINTEREST_CLIENT_SECRET  app secret (from developers.pinterest.com)
  PINTEREST_REFRESH_TOKEN  current refresh token (pinr…)
  GH_PAT                   classic PAT with repo admin — needed to write secrets
"""
import base64
import json
import os
import urllib.parse
import urllib.request

CLIENT_ID = "1619387"
REPO_API = "https://api.github.com/repos/zouhourab1996-stack/social-autopilot"
SCOPES = "boards:read,boards:write,pins:read,pins:write"

SECRET_ = os.environ.get("PINTEREST_CLIENT_SECRET", "")
REFRESH = os.environ.get("PINTEREST_REFRESH_TOKEN", "")
PAT = os.environ.get("GH_PAT", "")


def exchange():
    basic = base64.b64encode(f"{CLIENT_ID}:{SECRET_}".encode()).decode()
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": REFRESH,
        "scope": SCOPES,
    }).encode()
    req = urllib.request.Request("https://api.pinterest.com/v5/oauth/token", data=data,
                                 headers={"Authorization": "Basic " + basic,
                                          "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def update_secret(name, value):
    from nacl.public import PublicKey, SealedBox
    req = urllib.request.Request(REPO_API + "/actions/secrets/public-key",
                                 headers={"Authorization": "token " + PAT,
                                          "Accept": "application/vnd.github+json"})
    pk = json.loads(urllib.request.urlopen(req, timeout=30).read())
    box = SealedBox(PublicKey(base64.b64decode(pk["key"])))
    enc = base64.b64encode(box.encrypt(value.encode())).decode()
    r = urllib.request.Request(REPO_API + f"/actions/secrets/{name}",
                               data=json.dumps({"encrypted_value": enc,
                                                "key_id": pk["key_id"]}).encode(),
                               headers={"Authorization": "token " + PAT,
                                        "Accept": "application/vnd.github+json"},
                               method="PUT")
    urllib.request.urlopen(r, timeout=30)


if not (SECRET_ and REFRESH and PAT):
    print("Missing env (secret/refresh/PAT) — nothing to do.")
    raise SystemExit(0)

t = exchange()
update_secret("PINTEREST_ACCESS_TOKEN", t["access_token"])
if t.get("refresh_token"):
    update_secret("PINTEREST_REFRESH_TOKEN", t["refresh_token"])
print(f"Tokens refreshed. Access token valid {t.get('expires_in', 0) // 86400} days; "
      f"refresh token valid {t.get('refresh_token_expires_in', 0) // 86400} days.")
