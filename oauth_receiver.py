#!/usr/bin/env python3
"""Pinterest OAuth redirect receiver — captures ?code= and saves it to /tmp/oauth_code.json."""
import json, os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

CODE_FILE = "/tmp/oauth_code.json"

SUCCESS_HTML = """<!doctype html><html dir="rtl"><body style="font-family:system-ui;background:#0b1020;color:#eef1fb;display:grid;place-items:center;height:100vh;margin:0">
<div style="text-align:center;max-width:520px;padding:30px;border:1px solid #243056;border-radius:14px">
<div style="font-size:44px">&#9989;</div>
<h1 style="margin:10px 0">Authentication captured!</h1>
<p style="color:#9aa6cf">&#1578;&#1605; &#1578;&#1604;&#1602;&#1610; &#1575;&#1604;&#1578;&#1601;&#1608;&#1610;&#1590; &#1576;&#1606;&#1580;&#1575;&#1581; &#8212; &#1593;&#1583; &#1573;&#1604;&#1609; &#1575;&#1604;&#1605;&#1581;&#1575;&#1583;&#1579;&#1577; &#1608;&#1575;&#1603;&#1578;&#1576; &#1571;&#1610; &#1585;&#1587;&#1575;&#1604;&#1577;</p></div></body></html>"""

class H(BaseHTTPRequestHandler):
    def _send(self, html, code=200):
        b = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/callback":
            q = parse_qs(u.query)
            if "code" in q:
                json.dump({"code": q["code"][0], "state": q.get("state", [""])[0]}, open(CODE_FILE, "w"))
                self._send(SUCCESS_HTML)
                print("OAUTH CODE CAPTURED", flush=True)
            elif "error" in q:
                self._send("Pinterest returned an error: " + str(q), 400)
            else:
                self._send("Missing code parameter", 400)
        elif u.path == "/status":
            self._send("CODE CAPTURED" if os.path.exists(CODE_FILE) else "waiting for authorization...")
        else:
            self._send("Pinterest OAuth receiver is running. Waiting at /callback")
    def log_message(self, *a): pass

print("receiver listening on 0.0.0.0:8765", flush=True)
HTTPServer(("0.0.0.0", 8765), H).serve_forever()
