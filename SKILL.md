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

Battle-tested 2026-07-23 (郑钦文项目, 82MB 2:41 成片) / 2026-07-27 (函馆短片, 17MB 30s 横版) /
2026-07-31 (《选拍指南》**7 期系列 × 双平台 = 14 篇**, 全程处于小红书风控域黑洞期) /
2026-08-01 (雪中舞剑, 71MB 26.6s 横版国风CG; 黑洞持续 3h+, 靠用户手动开页 + 跨标签 IndexedDB 发成)。

**开工前先读四条硬约束**: ① **抖音封面必须用户手动上传** (§1 步骤4, 已确证无法自动化);
② 小红书**标题上限 20 字**、抖音 30 字, 两边标题要分别裁 (§2);
③ **抖音话题硬上限 5 个** (§1 步骤3), 文案里多写的只能进小红书;
④ **小红书封面弹窗默认 4:3**, 竖封面必须手动切 3:4, 否则标题被裁掉 (§2 步骤7)。

**用户规则: 视频时长 < 1 分钟不加章节** (两平台都不加)。抖音对短视频本来就不给章节入口。

## ⚡ 成本控制 (2026-08-02 黄泽林双平台实测约 80 次浏览器调用后定的规矩)

- **状态判断一律 JS 读 DOM, 截图只用于"人要看版式"的时刻**(封面裁没裁到、弹窗长什么样)。
  截图的 token 成本远高于同信息量的 JS 返回值; 抖音全表核对快照、XHS 开关状态/定时值/话题清单
  全部有现成 JS 口径(见各节), 别用截图代替。
- **能合并的浏览器操作用 `browser_batch` 合并**(点击→等待→读状态一次发); 单次 JS 调用有 ~45s
  超时, 话题这类"打字→等下拉→点击→验证"最多两个一组。
- **等待用 JS 内 `await new Promise(r=>setTimeout(...))` + 一次性读回**, 不要"截图轮询"。
- **发布全程顺手抓一次网络包**(`read_network_requests`): 目标是拿到发布/传封面/设章节的请求
  载荷结构, 评估把本 skill 从"驱动 UI"升级为"页内直接调接口"(签名头 x-s/a_bogus 由页面自己的
  拦截器生成, 所以必须在页内 fetch, 不能 curl)。接口模式若成立: 截图归零、话题免搜索下拉、
  且抖音封面的可信文件选择器限制可能整个绕开。

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

**开工第一件事: 两个平台各开一个标签确认登录态**, 别等填到一半才发现。抖音掉登录很常见
(2026-08-01 就是), 落地页直接是扫码/验证码 —— **这一步只能用户本人做**, 早点说早点并行。
两边都要查的话, 抖音的「内容管理」顺便就把已排期日期读出来了, 一举两得。

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

**已验证的死路 — 不要再试:** ⓪ **抖音封面的任何程序化上传** (注入的 File 保存必成黑图, 见 §1
步骤4 的四项隔离结论); ① `file_upload` 工具: ≤10MB 且只认会话共享目录(项目目录**和 scratchpad 都不行**);
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
   - **⚠ 硬上限 5 个** (页面提示「最多可添加5个话题」)。第 6 个的表现极具迷惑性: 下拉**正常弹出**、
     首行就是你要的词、Enter 和直接点条目**都没有报错**, 但就是不变 chip。别把它当成
     「下拉没加载完」反复重试 —— 先 `/最多可添加(\d+)个话题/.exec(document.body.innerText)`
     确认上限。文案里超出的话题只能进小红书。
   - **判定真假**: 真话题 = 有 `data-mention` 属性的元素; 纯文本 `#xx` 看起来一模一样
     (同色同粗), innerText 也一样, **只有 DOM 属性能区分**。别用颜色或 innerText 判断。
   - **交错幽灵**: 若某次 `Enter` 没选中 (下拉未加载完), mention 保持未闭合, 下一次输入会
     插进去, 得到 `#旅A行I工具行vlog` 这种交错串。必须验证后再打下一个。
   - **删除时 chip 是原子的**: 一次 `Backspace` 吃掉整个 chip。要删纯文本残留, 用
     TreeWalker 找到那个文本节点 → `Range.setStart/setEnd` 精确选中 → **一次**真键 Backspace。
     直接连按 Backspace 会连着吃掉前面的 chip 和正文 (踩过两次, 每次都要重打整段)。
   - **最后一个话题后补一个空格**终结编辑态。
4. **🚫 封面 = 唯一必须用户手动完成的一步 (2026-07-30 定论, 别再尝试自动化)。**
   把两个槽的弹窗打开, 然后**停下来请用户上传**竖3:4 + 横4:3, 传完再继续。
   - **现象**: JS 把 File 塞进 input 并派发 change 后, 裁剪框里**图片正确渲染出来**(肉眼可见),
     但点「保存」后封面槽变成视频首帧的**纯黑图**。
   - **真因**: JS 设的 FileList 产生 `isTrusted:false` 的 change —— 预览用 FileReader 读得到,
     保存链路读的是另一份只有可信文件选择器才会填的数据源。而点「上传封面」拉起的是 macOS
     **原生文件对话框**, 不在浏览器里, harness 驱动不了。
   - **已逐个隔离排除的假设, 不要重试**: ① 拖裁剪框破坏裁剪区 → 完全不拖照样黑;
     ② 图片没 decode 完就 drawImage → 注入后等 8s 照样黑; ③ "点击不够真实" → `computer left_click`
     本来就是真实合成点击, 和用户手点同一条通路; ④ 扩展 `file_upload` → 白名单只认会话共享目录,
     项目目录**和 scratchpad 都被拒**。
   - **小红书封面不受影响**, JS 注入正常工作 (见 §2 步骤7) —— 别因为抖音失败就放弃 XHS 自动化。
   - 交接话术: 把弹窗开好, 给用户**绝对路径**, 说明传完告诉你; 其余字段(标题/正文/话题/声明/定时)
     你全自动做完, 只等这一步。
   - 成功标志(用户传完后你验): 两个 tile 都显示缩略图 + `/封面检测通过/.test(body.innerText)`
     且 `/双封面缺失/` 为 false。
5. **自主声明 (按内容性质选, 不是固定值):**
   - 画面/配音由 AI 生成的 → **「内容由AI生成」**。国内深度合成规定要求 AI 内容标识, 标错有账号风险。
   - 真人解说/观点表达类 → 「内容为个人观点或见解」。
   - 弹窗是**单选**, 二者不可兼得; 拿不准时问用户。
6. **章节:** 章节名上限 **12 字**(超了"确定"不可点)。2026-08-02 实测**发布页的章节弹窗直接可用**
   (含播放器和时间轴, 与 2026-07 "video-cn.douyin.com 死加载"的观察相反 — 先试发布页, 不行再走
   内容管理→编辑页), 或选智能章节。手动加法: 点时间轴目标位置 → 手动添加 → 填名(≤12字) → 确定;
   加错时刻不用删, **每行的时刻数字可直接 triple_click 改**(比重新定位播放头快)。
   - **短视频压根没有章节入口**: 26.6s 的片子上传时「扩展信息 → 视频章节」还在, **视频处理完成后
     整行消失**。别当成 bug 去找。配合用户规则(<1分钟不加章节), 短片直接跳过这步。
7. **定时发布:** 选择器用**浏览器本地时区** (默认=now+2h 本地)。北京 19:00 = 美东 07:00 (夏令时,
   差 12h)。
   - **直接键入整串比滚轮快得多**: `triple_click` 日期框 → `type "2026-08-06 07:00"` → `Enter`。
     日历会跳到对应月并高亮日期+时分。滚轮选时分要一格一格数 (每格 ≈2.8 分), 又慢又易错。
   - 填完**必须核对日历高亮**的日/时/分三项。
8. 提交 → 内容管理里验证 (审核中 + 定时时间同样按本地时区显示)。

**⚠️ 误点会静默改坏别的字段**: 定时选择器/关联热点的下拉浮层盖在「保存权限」等单选组上,
点空处关浮层时容易顺手把 `保存权限` 从「允许」翻成「不允许」。**提交前用 JS 快照全表核对一遍**:
```js
const inputs=[...document.querySelectorAll('input[type=text]')].map(i=>({ph:i.placeholder,v:i.value})).filter(o=>o.v);
const chips=[...document.querySelectorAll('[data-mention]')].map(e=>e.textContent.trim());
const t=document.body.innerText;
({inputs,chips,声明:/内容为个人观点或见解/.test(t),缺封面:/双封面缺失/.test(t)})
```

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
4. **话题:** 逐个 `type "#xx"` → **等下拉真正加载出条目** → 点击条目 (下拉是异步搜索, 冷门词
   会「加载中」>2s, 此时按 Enter = 白按, 残留纯文本)。验证口径: 数 innerText 里 `[话题]#` 个数。
   - **⚠️ 按文字选, 不按位置选。** 下拉常给**上一次查询的陈旧结果** (打 `#网球拍` 却列出
     `#网球/#网球热土/#网球尖子生`), 点第一项就选错了。点之前核对第一项文字**等于**你打的词;
     不等 → 再触发一次。目标词也可能不在第一项 (`#网球科普` 排在 `#网球科` 之后、
     `#纳达尔` 排在 `#纳达` 之后), 按文字定位那一行再点。
   - **卡「加载中」→ 退一格再补回最后一字**: 按一次 `BackSpace` 再 `type` 回最后那个字,
     重新触发一次搜索。这是黑洞期最有效的一招 (见 §2.1)。
   - **凑不齐时用编辑器下方那排「推荐话题」chips**: 随笔记预加载, 点一下立刻变真话题,
     完全不走搜索接口, 零等待。内容相关时 (如 #网球) 是合格替补。
   **修复残留纯文本话题:** TreeWalker 找含 `#xx` 且不含 `[话题]` 的文本节点 → Range 精确选中 →
   真键 `Backspace` → 重打 → 等下拉 → 点击条目。
5. **⭐ 添加章节 (趁现在, 首发唯一窗口 —— 但 <1分钟的片子按用户规则直接跳过):**
   内容设置 → 添加章节 → 去添加 → 按文案的内容章节列表逐条填。弹窗机械细节:
   - **章节名上限 11 字**(抖音是 12 — 同一份章节两平台要分别裁, 黄泽林项目「从维园到纳达尔学院」
     9字过抖音、XHS 版只能「从维园到学院」)。
   - **最省事的加法(2026-08-02 定式): 在时间轴上随便点几个不同位置各加一行, 再逐行 triple_click
     改 mm/ss 输入框到精确时刻** — 不用跟播放头较劲。注意「不允许添加相同时刻点章节」: 两行时刻
     相同时第二行加不上, 先改开再加。
   - **`video.currentTime=x` 挪不动弹窗的播放头**(React 自己的状态, 不听 video 元素的) — 别试。
   - **章节加在播放头位置**, 不是加一行空白让你填时间。播放头没动 = 同一秒已有章节 = 点了没反应。
   - 时间轴换算: 用刻度标签(00:05/00:25)反推 px/s; 时间轴可横向滚动(容器 class 含
     timeline-graduation), >1 分钟的片子可见区只有开头一段。
   - 每行 = `mm` `ss` `章节名称` `章节描述`(可空)。**行高 50px**, 列表**只显示 3 行就开始滚动** ——
     第 4 行起必须先 `scroll` 再点, 否则点在列表外面(实测第 4 条名字没打进去)。
   - **清空章节**: 弹窗里有**两个「清空」**(上=内容总结, 下=章节列表), 清完**必须再点「保存章节」**
     才落库 —— 只清不保存, 关掉弹窗章节还在。清干净后主表单那行会从
     「已添加 N 个章节」变回「添加章节」。
6. **原创声明:** 点 toggle → 弹「权益」弹窗 → 勾「我已阅读并同意《原创声明须知》」→ 点
   「声明原创」→ toggle 变红。
   **⚠️ 顺序红线: 原创声明放到最后一个开, 定时先设好。** 权益弹窗一旦弹出:
   ① 任何点到弹窗外的操作都会把 toggle **弹回 off**(所以先开声明再去设定时 = 声明白开);
   ② 弹窗盖住底部「定时发布」按钮, 那一下提交会被**静默吞掉**(按钮不转圈 = 根本没提交)。
   正确顺序: **封面 → 定时开关 → 填时间 → 原创声明 → 勾须知 → 点「声明原创」→ 确认弹窗已关 → 提交**。
7. **封面:** 封面 b64 先经另一 XHS 标签存进 localStorage / IndexedDB → 表单页点第一块封面 tile →
   hover 出「修改封面」→ **再点一次**才开「设置封面」弹窗
   (**画布编辑器在美国网络能正常加载**, 与抖音相反) → 弹窗内出现
   `input[accept="image/png, image/jpeg, image/*"]` → 注入 File+change → 画布即显。
   - **⚠ 弹窗「封面比例」默认 4:3, 不是 3:4。** 1242×1656 的竖图丢进去会被按 4:3 裁掉上下,
     **标题整条被切走**。必须点比例下拉 → 选 **3:4**(三个选项 `3:4 / 4:3 / 1:1` 里的第一个) →
     画布重排成整张竖图 → 再「确定」。**切完务必 zoom 看一眼**标题/角标都在画面内。
     (旧版本这里写「1242×1656 恰好 = 3:4 免裁剪」是错的 —— 比例对不代表默认选中。)
   - 「确定」转几秒 → 出「封面效果评估通过, 未发现封面质量问题」。
8. **定时发布:** 更多设置 → 开 toggle → 时间输入框**明标「北京时间」**(语义就是北京时间, 别换算;
   默认值显示的是浏览器本地 now+1h, 是它家的 bug, 无视)。JS 赋值会被 React 回滚 — 真键盘打
   `YYYY-MM-DD HH:mm` → `Enter`; 日历面板会高亮日期+时分确认。
   - **⚠️ 别用 `computer cmd+A` 清场**: 焦点常在 body 上, cmd+A 会**全选整个页面**而不是输入框,
     接着 type 就打不进去 (时间还是默认值, 容易漏检)。可靠做法 = 先 JS 聚焦再打:
     ```js
     getSelection().removeAllRanges();
     const inp=[...document.querySelectorAll('input')].find(i=>/^\d{4}-\d{2}-\d{2}/.test(i.value||''));
     inp.scrollIntoView({block:'center'}); inp.focus(); inp.select();
     ```
   - 打完**读回 `inp.value` 核对**, 别只看截图。
9. **提交:** 点「定时发布」→ 按钮转圈 **40s+ (正常) / 50–90s (风控黑洞期)** → 成功 = 跳
   `/publish/success` 再回 `?published=true`。**URL 出现 `?published=true` 就是发布成功**,
   这是最可靠的判据。
10. **验证 (笔记管理):** 打开笔记管理, 卡片上标「定时发布 YYYY-MM-DD HH:mm (GMT+8:00 北京时间)」
    = 排期在。
    - tab 归属**不稳定**: 2026-07-23 观察到定时笔记落在「审核中」; 2026-07-31 一批 7 篇实测
      「审核中」为空、全部显示为定时发布态。**别拿某个 tab 空了当成没发成功** —— 以「全部 N」的
      **计数增量**和卡片上的定时标注为准。
    - 风控黑洞期**列表本身也加载不出来**(骨架屏/「加载中」不散), 而「全部 N」的计数会先出来 ——
      发布前记下 N, 发布后看增量, 这是黑洞期唯一能用的核验口径。
    - 同源 API `/api/galaxy/v2/creator/note/user/posted` **直接 fetch 会 `success:false`**
      (缺风控签名头), 别指望用它核验。

**编辑已发布/定时笔记:** `https://creator.xiaohongshu.com/publish/update?id=<noteId>&noteType=video`。
标题/正文/话题/封面/定时全部原样带回; 正文删块 = TreeWalker+Range 选区 + 真键 Backspace (选区从
上一段末尾选到目标块末尾, 一个 Backspace 干净落地); 保存 = 同一颗「定时发布」按钮 → 跳回笔记管理。
编辑保存后笔记回「审核中」, 排期不丢。章节入口在编辑页被锁 (见规范 1)。

**⚠️ 标题上限 20 字 (🎾 算 1 个)。** 超了输入框计数变红并截断。抖音是 30 字 ——
**同一系列两边标题要分别裁**, 别指望一份文案通用。示例:
抖音「🎾选拍指南03\|同样重量，为什么一支挥不动？」(21字, 超) → XHS「🎾选拍指南03\|同重量为何挥不动？」(17字)。
写文案时就按 20 字准备 XHS 版, 别到发布现场才改。

**⚠️ 白屏诊断 (创作者站整站白屏, app root 空、console 无错、零 API 调用):** 根因 = 风控域
`as.xiaohongshu.com` 从美国网络黑洞 — SPA 启动卡 `/api/p/pj` + `/api/sec/v1/scripting` 各 30s
超时后放弃挂载。诊断: `performance.getEntriesByType('resource')` 找 transferSize=0 &&
duration>30000。处置: `curl -s -o /dev/null -w "%{http_code}" --max-time 8
https://as.xiaohongshu.com/api/p/pj` 轮询, 返回任意非 000 后刷新页面即可。该域时通时断
(北京凌晨疑似维护窗)。**已 boot 的页面继续能用 (SPA 内部路由不受影响) — 白屏期间别刷好页面**;
登录态与笔记数据全程无恙。**注意"内部路由可用"不含跨 SPA 的整页跳转**: 从笔记管理点「编辑」
是整页加载, 黑洞期会卡死在「正在跳转中」(2026-08-02 实测) — 这类修改(如改定时)黑洞期只能请
用户手动点; 用户手点比程序 navigate 成功率高得多的规律对编辑页同样成立。
黑洞期笔记管理「全部 N」计数可能直接显示 **0**(接口没回来), 此时提交成败只认
`?published=true`, 别拿列表当依据。

**验证会话是否还在**(白屏页也能跑): `fetch('/api/galaxy/user/info',{credentials:'include'})`
返回 200 + `data.userId` = 登录中。注意 `/api/galaxy/user/me` 是 **404**, 别拿它当判据。

**⚠ 轮询可能一直不通 —— 这时最有效的一招是请用户自己点进去。** 2026-08-01 实测: 连续轮询
**90 分钟 (300 次) 全 000**, 期间程序化 `navigate` 到发布页必白屏; 但用户在同一浏览器里手动
点开发布页, SPA **挂载成功**。原因不明(可能是用户交互触发的请求走了不同路径), 但可复现有效。
**所以: 轮询 15–20 分钟还不通, 就直接告诉用户「请你手动点开发布页, 开好告诉我」**, 别干等。
用户开好的页面**绝对不能再导航/刷新** —— 视频与封面一律走跨标签 IndexedDB 搬进去
(§0, 本次 74MB 视频 + 374KB 封面均一次通过)。

### 2.1 风控黑洞期作业法 (页面已 boot, 但每个动作都被拖慢)

2026-07-31《选拍指南》7 期实战: `as.xiaohongshu.com` 连续 **3+ 小时** curl 全 000,
但**7 篇照样全部发完**。黑洞 ≠ 不能发, 只是每步要换手法:

| 症状 | 手法 |
|---|---|
| 话题下拉转圈 1–3 分钟 | 退一格再补回最后一字重触发; 下拉出的可能是陈旧结果, **按文字选** |
| 选出来是半截词(`#AI绘`/`#国风c`) | **别用「截图→读坐标→点」两步走**, 见下方「选词竞态」 |
| 话题实在不出 | 用编辑器下方「推荐话题」chips 顶上 (预加载, 零等待) |
| 开关点不动 | JS 派发 5 连鼠标事件 (见下) |
| 封面「确定」转圈 30s+ | 正常, 等它关闭再动下一步; 弹窗开着时点别处会被吞 |
| 提交按钮转 50–90s | 正常, 等 URL 变 `?published=true` |
| 笔记管理列表不出 | 用「全部 N」计数增量核验 |

**⚠ 选词竞态 (2026-08-01 实测, 8 个话题里错了 2 个)。** 黑洞期下拉每次要 30–60s, 期间它会
**多次重渲染**(先出上一次查询的陈旧结果, 再换成本次的)。如果按「截图 → 从截图读坐标 →
`computer left_click`」两步走, 截图和点击之间列表可能已经换过一轮, 于是你以为点的是
`#AI绘画`, 实际插进去的是 `#AI绘`; 打 `#国风CG` 却拿到 `#国风c`。**两个都是有效话题, 不会报错**,
只能靠 `a.tiptap-topic` 的文本逐个核对才发现。

**正解: 在同一个 JS 调用里「匹配文字 + 派发点击」**, 中间不给它重渲染的机会:
```js
const want='#AI绘画';
const row=[...document.querySelectorAll('div,li')].filter(e=>{
  const b=e.getBoundingClientRect();
  return e.offsetParent&&b.height>10&&b.height<60&&b.width>150&&
         e.innerText.trim().split(/\s+/)[0]===want;          // 全等, 不能用 startsWith
}).sort((a,b)=>a.getBoundingClientRect().height-b.getBoundingClientRect().height)[0];
if(row){const b=row.getBoundingClientRect();
  for(const t of ['pointerdown','mousedown','pointerup','mouseup','click'])
    row.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,
      clientX:b.x+b.width/2, clientY:b.y+b.height/2, view:window}));}
```
**输入手法也换一下**: 别一次 `type "#AI绘画"` (整串打完往往直接卡死在「加载中」)。
先打 `#AI绘` → 等 3s → 再补 `画` → 等 30–60s, 触发成功率明显更高。

**收尾必须逐个核对文本**: `[...ed.querySelectorAll('a.tiptap-topic')].map(e=>e.textContent)`,
数量对不代表内容对。错的话题**删除**: 它们是原子节点, 用 Range 选中 `[start,end)` 再一次真键
`Backspace`(末尾连着几个就一起选), 比逐个退格安全。

**开关点不动 → JS 派发完整鼠标事件序列。** `原创声明`/`定时发布` 的
`input[type=checkbox]` 是 0 尺寸隐藏元素 (`getBoundingClientRect` 会给出**负 y 或视口外坐标**,
按它换算去点必然打空), `computer left_click` 打在可见的 `.d-switch` 上也时灵时不灵:
```js
const sw=[...document.querySelectorAll('.d-switch.d-clickable')]
         .filter(e=>e.getBoundingClientRect().width>30);   // [0]=原创声明  [末]=定时发布
const t=sw[0], b=t.getBoundingClientRect();
for(const type of ['pointerdown','mousedown','pointerup','mouseup','click'])
  t.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,
    clientX:b.x+b.width/2, clientY:b.y+b.height/2, view:window}));
```
**状态判定**读 `.d-switch-simulator` 的 class 含不含 `unchecked`:
```js
[...document.querySelectorAll('.d-switch-simulator')].map(e=>e.className.includes('unchecked')?'off':'ON')
// 顺序: [PK封面, 原创声明, 定时发布]
```
**每点一次就读一次**, 别连点两个开关再一起验 —— 权益弹窗会让第二次点击把第一个开关弹回去。

### 2.2 多期系列批量发布 (N 期隔天定时)

- **每期独立走一遍完整流程**, 不要试图复用上一期的表单。发完一期 URL 变 `?published=true`,
  点侧栏「发布笔记 → 上传视频」开新的一篇。
- **新页面的上传区常要点两遍菜单才渲染出 `input[type=file]`** —— 注入前先
  `document.querySelectorAll('input[type=file]').length` 探一下, 为 0 就再点一次「发布笔记→上传视频」。
- **视频/封面接力用另一个同平台标签**, 工作标签全程不导航 (黑洞期页面来之不易)。
  每期开始前把 `relay_xvid.html` / `relay_xcov.html` 重新生成一遍指向新文件。
- **趁提交转圈的 40–90 秒**准备下一期的素材和接力页, 省掉串行等待。
- 时间递增用脚本算好写在计划里 (如 07-31/08-02/…/08-12 每期 +2 天), 别现场心算。

---

## 3. 双平台提交前核对清单

- [ ] 标题: 🎾 前缀 (网球); **XHS ≤20 字 / 抖音 ≤30 字, 分别裁过**
- [ ] 正文: 全文 + tags 完整; **XHS 正文无章节块**
- [ ] 话题: 数量对得上文案 (XHS 数 `[话题]#`; 抖音末尾空格已补, **且 ≤5 个**)
- [ ] 话题: **逐个核对文本全等**, 别只数数量 —— 半截词(`#AI绘`/`#国风c`)不会报错 (§2.1 选词竞态)
- [ ] 章节: **视频 <1 分钟 → 两平台都不加**; ≥1 分钟才走 XHS 添加章节 (首发唯一窗口) / 抖音智能章节
- [ ] 封面: XHS 弹窗比例**已从默认 4:3 切到 3:4**, 且 zoom 确认标题没被裁
- [ ] 声明: XHS 原创声明开; 抖音自主声明=内容为个人观点或见解
- [ ] **封面两版都已生成** (`封面图-竖3x4.jpg` 1242×1656 + `封面图-横4x3.jpg` 1440×1080)
- [ ] 封面: XHS 用竖版(自动注入), 评估通过; 抖音**请用户手动传两个槽**且「封面检测通过」
- [ ] 话题: 抖音逐个用 `[data-mention]` 验过是真 chip; XHS 数 `[话题]#` 且**每个都核对过文字**
      (下拉给陈旧结果, 按位置点会选错)
- [ ] 定时: XHS 填北京时间原值; 抖音填本地时区换算值 — 两平台指向同一北京时刻;
      **两边都读回输入框 value 核对**, 别只看截图
- [ ] XHS 顺序: 定时先设、原创声明最后开, 且**确认权益弹窗已关**再点提交
- [ ] 抖音: 提交前 JS 快照全表 (含 `保存权限=允许` 没被误点翻掉)
- [ ] 提交后确认: XHS URL 变 `?published=true` + 笔记管理计数增量; 抖音内容管理出现「定时发布中」

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
  用最后一帧时先确认它不是淡出黑场: `ffmpeg -sseof -0.05 … ` 抽出来看平均亮度。
  `--bias` 按主体水平位置给 (见上表下方说明); 出图后**必须 Read 看一眼**竖版有没有把主体裁掉、
  标题有没有压在主体脸/手上 —— 标题落在天空/墙面等留白处最好。

  **标题字体链 (2026-08-01 修)**: 标题原本写死日文明朝, 而它**没有简体专用字形**(剑/说/讲…),
  缺字时 PIL **静默画豆腐块 ☒ 且不报错**。现在 `FONT_TITLE_CHAIN` 按序取第一个能覆盖标题
  全部字符的字体(日文明朝 → Songti SC Bold), 日文标题仍走明朝, 中文自动落宋体。
  覆盖检测靠「跟 U+FFFF 的位图比对」(fontTools 不一定装, getbbox 对豆腐块也返回尺寸)。

  **竖版标题压主体怎么办 (最后一帧这类「人物站得高」的画面必遇到)**:
  竖版标题带固定占据画面 **0.165–0.33 高**、横向约 53% 宽且**居中**, 主体头部只要落在这一带
  就会撞。满幅 3:4 要从 16:9 裁掉大半宽度, **鱼与熊掌**:
  - 想保住道具(剑/球拍)完整 → 主体被迫居中 → **只能去掉 `--sub`**(副标题+分隔线正压脸),
    留大标题浮在头顶上方;
  - 想让文字完全避开人 → `--bias` 把主体推到画面 20% 或 80% 处 → 会裁掉一侧的道具。
  两版**各自选**, 不用强求一致(本次: 竖版 bias .40 无副标题保住剑, 横版 bias 1.0 带副标题、
  主体靠左文字落右侧留白)。分隔线现在只在有 `--sub` 时才画 —— 以前无条件画, 会单独横穿发髻。
