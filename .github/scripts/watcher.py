#!/usr/bin/env python3
"""A-watcher: يراقب رسائل الوكيل B على اللوحة ويفتح/يحدّث Issue استدعاء للمالك.
جسر حتمي — لا ينشر ولا يعدّل AGENT-TASKS.md (حماية من تعارض الوكيلين).
القاعدة: رسالة B تُعتبر "تنتظر الرد" فقط إذا لم يوجد بعدها (أحدث منها) أي commit من A."""
import json, os, re, subprocess, sys
import urllib.request

REPO = os.environ.get("REPO", "zouhourab1996-stack/social-autopilot")
TOKEN = os.environ.get("GH_TOKEN", "")
API = f"https://api.github.com/repos/{REPO}"
H = {"Authorization": f"Bearer {TOKEN}", "User-Agent": "a-watcher", "Accept": "application/vnd.github+json"}

log = subprocess.run(["git", "log", "-30", "--pretty=%H%x09%an%x09%s"], capture_output=True, text=True).stdout
commits = [line.split("\t", 2) for line in log.strip().splitlines() if "\t" in line]

def who(author, subject):
    if "agent B" in author or re.match(r"^B:?", subject.strip()):
        return "B"
    if "autopilot" in author or "a-watcher" in author or "Hark" in author and "agent B" in author:
        return "A" if "agent B" not in author else "B"
    return "?"

# الحالة: آخر commit تمت معالجته
try:
    acked = json.load(open(".watcher-state.json"))["acked"]
except Exception:
    acked = commits[0][0] if commits else ""   # أول تشغيل: لا استدعاء على القديم

new_b = []
for sha, author, subject in commits:          # الأحدث أولًا
    if sha == acked:
        break
    side = who(author, subject)
    if side == "B":
        new_b.append((sha[:7], subject.splitlines()[0][:100]))
    elif side == "A":
        break                                  # A ردّ بعدها → كل ما دونها معالَج

if not new_b:
    print(f"no unacked B messages (acked={acked[:7]})")
    sys.exit(0)

def api(path, data=None):
    req = urllib.request.Request(API + path, headers=H,
        data=json.dumps(data).encode() if data else None,
        method="POST" if data else "GET")
    return json.load(urllib.request.urlopen(req))

inbox = next((i for i in api("/issues?state=open&per_page=50")
              if "inbox" in [l["name"] for l in i.get("labels", [])]), None)

body = "\n".join(f"- [`{sha}`] {s}" for sha, s in new_b)
msg = (f"🔔 **رسائل جديدة من الوكيل B تنتظر Arena** ({len(new_b)}):\n\n{body}\n\n"
       "> **المالك:** افتح محادثة Arena واكتب أي حرف (مثل «؟») — سيتفقد اللوحة ويتصرف فورًا.\n"
       "> يُحدَّث تلقائيًا ولا يحتاج ردًا.")

if inbox:
    api(f"/issues/{inbox['number']}/comments", {"body": msg})
    print(f"commented on issue #{inbox['number']}")
else:
    issue = api("/issues", {"title": "🔔 صندوق الوارد: رسائل Hark تنتظر Arena",
                            "body": msg, "labels": ["inbox"]})
    print(f"opened issue #{issue['number']}")

json.dump({"acked": commits[0][0]}, open(".watcher-state.json", "w"))
subprocess.run(["git", "config", "user.name", "a-watcher"], check=True)
subprocess.run(["git", "config", "user.email", "actions@github.com"], check=True)
subprocess.run(["git", "add", ".watcher-state.json"], check=True)
subprocess.run(["git", "commit", "-m", f"watcher: ack {commits[0][0][:7]} [skip ci]"], check=True)
subprocess.run(["git", "push"], check=True)
print("state committed")
