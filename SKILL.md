---
name: publish-xhs-douyin
description: >-
  Auto-publish a finished vertical video (成片 + 封面图 + 发布文案 + 内容章节) to 小红书 and
  抖音 via their web creator backends, driven through Claude-in-Chrome. Handles video upload,
  title/body/tags, platform chapter features, declarations (原创声明/自主声明), custom cover,
  and 定时发布 scheduling. Use when the user says 发布小红书 / 发布抖音 / 自动发布 / 定时发布 /
  "把视频发到小红书和抖音" after a video has been produced (typically by the
  vertical-commentary-video skill).
---

# 自动发布小红书 + 抖音 (web 创作者后台)

Battle-tested 2026-07-23 (郑钦文项目, 82MB 2:41 成片) / 2026-07-27 (函馆短片, 17MB 30s 横版)。
输入 = 交付五件套:
`<成片>.mp4` + **`封面图-竖3x4.jpg` (1242×1656)** + **`封面图-横4x3.jpg` (1440×1080)** +
`小红书发布文案.md` (标题/正文/tags) + 内容章节列表。

## ⚠ 封面必须一次出两版 (3:4 竖 + 4:3 横)

**抖音发布页有两个独立封面槽**: `横封面4:3` 和 `竖封面3:4`，缺一个会一直挂
「横/竖双封面缺失」提示。只给一张 3:4 的结果: 它被塞进 4:3 槽并按 4:3 裁掉上下,
竖槽只能用平台 AI 封面 —— 而**信息流里露出的恰恰是竖封面**, 等于自制封面白做。

生成规则:
| 槽位 | 尺寸 | 平台 | 构图 |
|---|---|---|---|
| 竖 3:4 | 1242×1656 | XHS 封面 + 抖音竖封面 | **满幅铺图, 标题叠上三分之一** (信息流主视觉, 优先做好这张) |
| 横 4:3 | 1440×1080 | 抖音横封面 | **满幅铺图, 标题叠下三分之一** |

**两版都满幅, 不留纯色条** —— 信息流里色条会显得像加了边框, 图也变小。可读性靠**渐变压暗**
(竖版顶部渐变 / 横版底部渐变) + 文字投影, 不靠色块。

**不能互相裁切生成**: 标题落点一上一下, 裁一刀会把标题整块裁掉。两版各自按目标画布排一次版。

**`--bias` 必须按主体位置给**: 3:4 满幅要从 16:9 里裁掉大半宽度 (1280×720 → 只剩 540×720),
主体偏一侧时不指定就会被裁掉。0=靠左 / .5=居中 / 1=靠右。脚本会在放大 >1.8× 时提示 ——
720p 源出竖版满幅约 2.3×, 手机上通常可接受, 但别指望锐利。

`scripts/make_covers.py` 一条命令出两版 —— 见文末 scripts 段。

**前置条件**: ① Claude-in-Chrome 已连接; ② 用户已登录两个平台 (XHS 只有短信/扫码登录, 必须用户
本人操作 — 白屏+API 超时=未登录 OR 见文末风控域黑洞); ③ 发布桥在跑。

## 0. 共享基础设施

```bash
cd <project_dir>   # 成片/封面所在目录
python <skill>/scripts/publish_bridge.py .   # 127.0.0.1:8765, ThreadingHTTPServer(单线程会被死连接卡住)
```

**window.name 跨域接力 (核心手法 — 大文件进创作者页的唯一通路):** window.name 在同标签顶层导航间
存活(跨域也存活), 顶层导航不受 CSP 管。流程:
```bash
python <skill>/scripts/make_relay.py <成片文件名> "<返回的创作者页URL>" vid ZQVID
# 生成 relay_vid.html 于桥目录 → 把标签导航到 http://127.0.0.1:8765/f/relay_vid.html
# 页面自动: fetch /f/<file> → FileReader b64 → window.name='ZQVID:'+b64 → location.replace(返回URL)
```
回到创作者页后注入 (javascript_tool):
```js
const b64=window.name.slice(6); window.name='';
const bin=atob(b64); const u8=new Uint8Array(bin.length);
for(let i=0;i<bin.length;i++)u8[i]=bin.charCodeAt(i);
const f=new File([u8],'<文件名>.mp4',{type:'video/mp4'});
const dt=new DataTransfer(); dt.items.add(f);
const inp=document.querySelector('input[type=file]'); inp.files=dt.files;
inp.dispatchEvent(new Event('change',{bubbles:true}));
```
82MB→1.14亿字符 b64 没问题; SPA 冷加载白屏时 window.name 照样存活, 反复刷新等它起来即可。

**⚠ 但页面来之不易时绝不能刷新**: 风控域黑洞期间 SPA 只在偶尔通的窗口里挂载得起来 (或用户手动
点进去的)。这种页面**一导航就回不来**。此时 window.name 接力不能用在工作标签上 —— 改用下面的
跨标签方案, 工作标签全程不动。

**大文件跨标签: IndexedDB 存 Blob** (17MB 视频实测通)。localStorage 装不下 (24M 字符 b64
≈ 48MB UTF-16, 超配额), 且 b64 字符串比 Blob 多占一倍:
```js
// A. 新标签: 127.0.0.1 接力页 → window.name → 落到目标站同源页 (白屏也行, JS 照跑) → 存 Blob
const bin=atob(window.name.slice(7)); window.name='';
const u8=new Uint8Array(bin.length); for(let i=0;i<bin.length;i++)u8[i]=bin.charCodeAt(i);
const db=await new Promise((res,rej)=>{const q=indexedDB.open('xfer',1);
  q.onupgradeneeded=e=>e.target.result.createObjectStore('files');
  q.onsuccess=e=>res(e.target.result); q.onerror=e=>rej(e.target.error);});
await new Promise((res,rej)=>{const tx=db.transaction('files','readwrite');
  tx.objectStore('files').put(new Blob([u8],{type:'video/mp4'}),'video');
  tx.oncomplete=res; tx.onerror=e=>rej(e.target.error);});
// B. 工作标签 (未导航): 同样 open('xfer',1) → get('video') → new File([blob],name) → 注入
```
接力落地页用**白屏也无妨的同源 URL** —— 只要 document 存在 JS 就能跑, 不需要 SPA 挂载。

**封面小文件走 localStorage 同源跨标签接力** (免得再动表单标签): 另开一个同平台标签跑一次
window.name 接力 → `localStorage.setItem('zq_cover_b64', b64)` → 表单标签同源读出注入。

**坐标换算 (computer 点击):** screenshot_px = clientRect_px × (screenshot宽 / window.innerWidth)。
每次窗口尺寸变了要重新算; 优先用 JS 拿 getBoundingClientRect 再换算, 别肉眼估。

**已验证的死路 — 不要再试:** ① `file_upload` 工具: ≤10MB 且只认会话共享目录(项目目录不行);
② 抖音 CSP 拦 connect-src+img-src 到 127.0.0.1 (页内 fetch 桥必败); ③ XHS 无 CSP 但 Chrome
Local Network Access 会让页内 localhost fetch 无限挂起; ④ python http.server GET 请求行上限
64KB (巨型 URL 走私不通); ⑤ popup / a.click() 下载被拦; ⑥ b64 放进工具**返回值**会被安全过滤
(写方向 OK — 所以 JS 里算完只 return 长度/校验值, 别回传内容); ⑦ 抖音编辑器 execCommand 插入
会被 React 回滚/重复。

---

## 1. 抖音 (creator.douyin.com)

**用户三条固定规范 (2026-07-23 定, 必须执行):**
1. 网球内容标题**开头加 🎾** (如「🎾从奥运冠军到重新出发」)。
2. **自主声明 = 「内容为个人观点或见解」** 必选。
3. **视频章节必须有**: 用抖音智能章节自动生成, 或手动添加, 不能空着。

**流程:**
1. 视频: make_relay 返回 URL 设为 `https://creator.douyin.com/creator-micro/content/upload`
   → 接力 → 注入 input[type=file] → 秒收并自动跳发布表单。
2. **标题/简介 (editor-kit 极难伺候):** 唯一稳的输入法 = 精确坐标点击聚焦 → `cmd+A`+`Backspace`
   真键盘清场 → `computer type` 打字。禁 execCommand (React 回滚 + 幽灵 token: "郑钦暖"、
   "育人物"复活)。回车在简介里**不产生换行** (章节别写简介里 — 用章节功能)。
3. **话题 tags (抖音编辑器专属地雷):** 逐个 `type "#xx"` → 等 3s → `Enter`, **每个都要用
   `[...ed.querySelectorAll('[data-mention]')].map(e=>e.textContent)` 验证**是否成了真 chip。
   - **判定真假**: 真话题 = 有 `data-mention` 属性的元素; 纯文本 `#xx` 看起来一模一样
     (同色同粗), innerText 也一样, **只有 DOM 属性能区分**。别用颜色或 innerText 判断。
   - **交错幽灵**: 若某次 `Enter` 没选中 (下拉未加载完), mention 保持未闭合, 下一次输入会
     插进去, 得到 `#旅A行I工具行vlog` 这种交错串。必须验证后再打下一个。
   - **删除时 chip 是原子的**: 一次 `Backspace` 吃掉整个 chip。要删纯文本残留, 用
     TreeWalker 找到那个文本节点 → `Range.setStart/setEnd` 精确选中 → **一次**真键 Backspace。
     直接连按 Backspace 会连着吃掉前面的 chip 和正文 (踩过两次, 每次都要重打整段)。
   - **最后一个话题后补一个空格**终结编辑态。
4. **封面 (两个槽都要填):** 发布页有 `横封面4:3` 和 `竖封面3:4` 两个 `选择封面` tile,
   分别点开 → 弹窗内 `+上传封面` → 注入对应比例的图 → 裁剪框拖满 → `保存`。
   - **画布加载慢但不是死的**: 主画布转圈时「完成」是灰的, **要等它转完**, 别看到灰就判定失败。
     (2026-07-23 记录的"美国网络画布必死"是误判 —— 07-27 实测正常可用, 只是慢。)
   - 注入口 = `accept` 恰为 `image/png,image/jpeg,image/jpg` 的那个 input (页面有 6 个 file input)。
   - 封面 b64 走 localStorage 同源跨标签接力 (小文件够用; 大文件见 §视频接力的 IndexedDB 方案)。
   - 成功标志: 两个 tile 都显示缩略图 + 右侧「封面检测通过」。
5. **自主声明 (按内容性质选, 不是固定值):**
   - 画面/配音由 AI 生成的 → **「内容由AI生成」**。国内深度合成规定要求 AI 内容标识, 标错有账号风险。
   - 真人解说/观点表达类 → 「内容为个人观点或见解」。
   - 弹窗是**单选**, 二者不可兼得; 拿不准时问用户。
6. **章节:** 发布页的章节弹窗播放器 (video-cn.douyin.com) 在美国网络死加载; **内容管理→编辑 页
   的同一弹窗是好的** — 发布后从编辑页手动添加, 或选智能章节。
7. **定时发布:** 选择器用**浏览器本地时区** (默认=now+2h 本地)。北京 19:00 = 美东 07:00 (夏令时,
   差 12h)。填完核对日历高亮。
8. 提交 → 内容管理里验证 (审核中 + 定时时间同样按本地时区显示)。

---

## 2. 小红书 (creator.xiaohongshu.com)

**用户两条固定规范 (2026-07-23 定, 必须执行):**
1. **章节不进正文** — 用 **内容设置 → 添加章节** 功能设置。⚠️**必须在首次发布时就设好**:
   发布/定时后编辑页里该入口被锁, tooltip「可通过『替换视频』重新设置章节信息」= 只有在
   update 页重传整个视频才能解锁。**别忘了这一步, 忘了代价是重传 82MB。**
2. **原创声明 toggle 必开** (自制解说内容)。

网球标题同样加 🎾 前缀 (抖音规范 1 延伸, 两平台标题保持一致)。

**流程 (发布页 `https://creator.xiaohongshu.com/publish/publish?source=official`):**
1. **视频:** make_relay 返回 URL 设为发布页 → 接力 → 注入 (input accept=.mp4,.mov,…)。
   完成标志 = 「重新上传」出现 + 「检测为高清视频」。(~930KB/s, 82MB 约 10 分钟。)
2. **标题:** 原生 value setter 即可:
   `Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(inp,t)` + input 事件。
3. **正文:** tiptap/ProseMirror 很乖 — 一次 `ClipboardEvent('paste')` 贴整段, 换行保留:
   ```js
   const dt=new DataTransfer(); dt.setData('text/plain', body);
   ed.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
   ```
   正文 = 文案正文, **不含章节块** (规范 1)。
4. **话题:** 逐个 `type "#xx"` → **等下拉真正加载出条目** → 点击第一项 (下拉是异步搜索, 冷门词
   会「加载中」>2s, 此时按 Enter = 白按, 残留纯文本)。验证口径: 数 innerText 里 `[话题]#` 个数。
   **修复残留纯文本话题:** TreeWalker 找含 `#xx` 且不含 `[话题]` 的文本节点 → Range 精确选中 →
   真键 `Backspace` → 重打 → 等下拉 → 点击条目。
5. **⭐ 添加章节 (趁现在, 首发唯一窗口):** 内容设置 → 添加章节 → 去添加 → 按文案的内容章节列表
   逐条填 (时间 mm:ss + 标题, 如 00:00 巅峰崛起 / 00:43 伤病与漫长复出 / 01:54 雅典回暖)。
6. **原创声明:** 点 toggle → 弹「权益」弹窗 → 勾「我已阅读并同意《原创声明须知》」→ 点
   「声明原创」→ toggle 变红。
7. **封面:** 1242×1656 恰好 = XHS 3:4 封面比例, 免裁剪。封面 b64 先经另一 XHS 标签存进
   localStorage → 表单页点第一块封面 tile → hover 出「修改封面」→ 再点开「设置封面」弹窗
   (**画布编辑器在美国网络能正常加载**, 与抖音相反) → 弹窗内出现
   `input[accept="image/png, image/jpeg"]` → 注入 File+change → 画布即显 → 「确定」(转几秒) →
   出「封面效果评估通过, 未发现封面质量问题」。
8. **定时发布:** 更多设置 → 开 toggle → 时间输入框**明标「北京时间」**(语义就是北京时间, 别换算;
   默认值显示的是浏览器本地 now+1h, 是它家的 bug, 无视)。JS 赋值会被 React 回滚 — 点输入框 →
   `cmd+A` → 真键盘打 `YYYY-MM-DD HH:mm` → `Enter`; 日历面板会高亮日期+时分确认。
9. **提交:** 点「定时发布」→ 按钮转圈可达 40s+ (大视频) → 成功 = 跳 `/publish/success` 再回
   `?published=true`。
10. **验证 (笔记管理):** 定时+审核中的笔记落在**「审核中」tab** (不在「定时发布」tab), 卡片上标
    「定时发布 YYYY-MM-DD HH:mm (GMT+8:00 北京时间)」= 排期在。审核通过后按时发布。

**编辑已发布/定时笔记:** `https://creator.xiaohongshu.com/publish/update?id=<noteId>&noteType=video`。
标题/正文/话题/封面/定时全部原样带回; 正文删块 = TreeWalker+Range 选区 + 真键 Backspace (选区从
上一段末尾选到目标块末尾, 一个 Backspace 干净落地); 保存 = 同一颗「定时发布」按钮 → 跳回笔记管理。
编辑保存后笔记回「审核中」, 排期不丢。章节入口在编辑页被锁 (见规范 1)。

**⚠️ 白屏诊断 (创作者站整站白屏, app root 空、console 无错、零 API 调用):** 根因 = 风控域
`as.xiaohongshu.com` 从美国网络黑洞 — SPA 启动卡 `/api/p/pj` + `/api/sec/v1/scripting` 各 30s
超时后放弃挂载。诊断: `performance.getEntriesByType('resource')` 找 transferSize=0 &&
duration>30000。处置: `curl -s -o /dev/null -w "%{http_code}" --max-time 8
https://as.xiaohongshu.com/api/p/pj` 轮询, 返回任意非 000 后刷新页面即可。该域时通时断
(北京凌晨疑似维护窗)。**已 boot 的页面继续能用 (SPA 内部路由不受影响) — 白屏期间别刷好页面**;
登录态与笔记数据全程无恙。同源 API 可直接 fetch 验证会话: `/api/galaxy/user/me` 类端点 200 = 在登录。

---

## 3. 双平台提交前核对清单

- [ ] 标题: 🎾 前缀 (网球), 两平台一致
- [ ] 正文: 全文 + tags 完整; **XHS 正文无章节块**
- [ ] 话题: 数量对得上文案 (XHS 数 `[话题]#`; 抖音末尾空格已补)
- [ ] 章节: XHS 用添加章节功能 (首发时!); 抖音智能章节或编辑页手动
- [ ] 声明: XHS 原创声明开; 抖音自主声明=内容为个人观点或见解
- [ ] **封面两版都已生成** (`封面图-竖3x4.jpg` 1242×1656 + `封面图-横4x3.jpg` 1440×1080)
- [ ] 封面: XHS 用竖版, 评估通过; 抖音**两个槽都填上**且「封面检测通过」(别留 AI 兜底占着竖槽)
- [ ] 话题: 抖音逐个用 `[data-mention]` 验过是真 chip, 无交错幽灵文本残留
- [ ] 定时: XHS 填北京时间原值; 抖音填本地时区换算值 — 两平台指向同一北京时刻
- [ ] 提交后回列表页截图确认 (XHS 审核中卡片带定时标注; 抖音内容管理)

## scripts/
`publish_bridge.py` — 本地文件桥 127.0.0.1:8765 (GET /f/<name>, CORS+PNA 头, ThreadingHTTPServer)
  坑: 端口可能被上次会话遗留的桥占着 (返回 501/服务错目录) — 先 `lsof -nP -iTCP:8765 -sTCP:LISTEN` 查, kill 掉再起。
`make_relay.py` — 生成 window.name 接力页 (文件名 + 返回URL → relay_<tag>.html)
`make_covers.py` — **一条命令出双封面** (竖3:4 + 横4:3), 横版按 4:3 重新排版而非裁切:
```bash
python3 <skill>/scripts/make_covers.py --video 成片.mp4 --t 24.5 --bias 0.72 \
  --title "函館の記憶" --sub "回忆，不必留在这里" --tag "AI 短片 · 北海道函館" --outdir final/
```
  `--t` 选**没有片尾标题的那一帧** (否则片中标题与封面标题重复), 且优先选有故事张力的一帧。
  `--bias` 按主体水平位置给 (见上表下方说明); 出图后**必须 Read 看一眼**竖版有没有把主体裁掉、
  标题有没有压在主体脸/手上 —— 标题落在天空/墙面等留白处最好。
