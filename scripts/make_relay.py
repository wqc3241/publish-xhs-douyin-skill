#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 window.name 接力页 (跨域搬运大文件进创作者后台的核心工具)。

原理: window.name 在同一标签页的顶层导航之间存活(跨域也存活), 且顶层导航不受 CSP 管。
所以: 浏览器标签 → http://127.0.0.1:8765/f/relay_<tag>.html (本页 fetch 同源 /f/<file> →
FileReader → base64 → window.name = '<PREFIX>:'+b64 → location.replace(<return_url>)) →
回到创作者页面后用 javascript_tool 读 window.name, atob → File → 塞进 input[type=file]。

用法:
  python make_relay.py <served_file_name> <return_url> [tag=vid] [prefix=ZQVID]
生成 ./relay_<tag>.html (放在 publish_bridge.py 的服务目录里跑这条命令),
然后把浏览器导航到 http://127.0.0.1:8765/f/relay_<tag>.html 即可。
"""
import sys, os, urllib.parse

if len(sys.argv) < 3:
    print(__doc__); sys.exit(1)
fname, url = sys.argv[1], sys.argv[2]
tag = sys.argv[3] if len(sys.argv) > 3 else "vid"
prefix = sys.argv[4] if len(sys.argv) > 4 else "ZQVID"
q = urllib.parse.quote(fname)

html = f"""<!doctype html>
<meta charset="utf-8">
<title>relay {tag}</title>
<body style="font-family:monospace;background:#111;color:#0f0">
<pre id="log">loading {fname} from bridge...</pre>
<script>
const log = m => document.getElementById('log').textContent += '\\n' + m;
(async () => {{
  try {{
    const r = await fetch('/f/{q}');
    if (!r.ok) {{ log('fetch failed: ' + r.status); return; }}
    const blob = await r.blob();
    log('blob ' + blob.size + ' bytes, encoding...');
    const fr = new FileReader();
    fr.onload = () => {{
      window.name = '{prefix}:' + fr.result.split(',')[1];
      log('window.name set (' + window.name.length + ' chars), navigating...');
      location.replace({url!r});
    }};
    fr.onerror = () => log('FileReader error');
    fr.readAsDataURL(blob);
  }} catch (e) {{ log('ERR ' + e); }}
}})();
</script>
</body>
"""
out = f"relay_{tag}.html"
open(out, "w").write(html)
print("wrote", os.path.abspath(out))
print("navigate the tab to: http://127.0.0.1:8765/f/" + out)
