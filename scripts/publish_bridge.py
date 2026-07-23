# -*- coding: utf-8 -*-
"""发布用本地文件服务器: 把成片/封面喂给创作者后台页面 (creator.douyin.com / creator.xiaohongshu.com)。
页内 `fetch('http://127.0.0.1:8765/f/<name>')` -> blob -> new File -> input.files=dt.files。
- GET /f/<name>  从启动目录读文件, 带 CORS 头 (https 页面访问 127.0.0.1 有混合内容豁免)
- POST 兼容 cover_bridge 的 name+url/b64 落盘 (备用)
用法: python publish_bridge.py [服务目录]  (默认 cwd; 端口 8765)"""
import http.server, urllib.request, os, sys, base64, mimetypes
from urllib.parse import parse_qs, unquote
ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())
class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"   # no keep-alive: avoids Chrome fetch hang
    def _cors(self):
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        # Chrome Private Network Access preflight (public https page -> 127.0.0.1)
        self.send_header("Access-Control-Allow-Private-Network", "true")
    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.send_header("Content-Length","0"); self.end_headers()
    def do_GET(self):
        if not self.path.startswith("/f/"):
            self.send_response(404); self._cors(); self.send_header("Content-Length","0"); self.end_headers(); return
        name = os.path.basename(unquote(self.path[3:]))
        p = os.path.join(ROOT, name)
        if not os.path.exists(p):
            self.send_response(404); self._cors(); self.send_header("Content-Length","0"); self.end_headers(); return
        data = open(p, "rb").read()
        self.send_response(200); self._cors()
        self.send_header("Content-Type", mimetypes.guess_type(p)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data))); self.end_headers()
        self.wfile.write(data)
    def do_POST(self):
        try:
            l = int(self.headers.get('Content-Length', 0)); body = self.rfile.read(l).decode()
            d = parse_qs(body); name = os.path.basename(d.get('name', ['img.jpg'])[0])
            if 'b64' in d:
                data = base64.b64decode(d['b64'][0].split(',')[-1])
            else:
                req = urllib.request.Request(d['url'][0], headers={'User-Agent': 'Mozilla/5.0'})
                data = urllib.request.urlopen(req, timeout=60).read()
            open(os.path.join(ROOT, name), 'wb').write(data)
            out = b"saved " + name.encode()
            self.send_response(200); self._cors(); self.send_header("Content-Length", str(len(out))); self.end_headers()
            self.wfile.write(out)
        except Exception as e:
            out = ("ERR %r" % e).encode()
            self.send_response(500); self._cors(); self.send_header("Content-Length", str(len(out))); self.end_headers()
            self.wfile.write(out)
    def log_message(self, *a): pass
print("publish bridge on 127.0.0.1:8765 root:", ROOT, flush=True)
http.server.ThreadingHTTPServer(('127.0.0.1', 8765), H).serve_forever()
