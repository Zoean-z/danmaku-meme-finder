# Danmaku Meme Finder

一个本地优先的 MVP：Node.js 使用 `douyudm` v3.2.0 采集斗鱼房间 `6657` 的普通弹幕到 JSONL，Python 将其导入 SQLite，排除已有梗库后输出待人工判断的候选梗。它只用于快速验证“重复出现的新表达是否值得收录”，不会自动写入正式梗库。

## 环境与安装

- Python 3.11 或更高版本
- Node.js 18 或更高版本
- 可访问斗鱼弹幕服务器，以及同步时可访问已有梗库接口

macOS/Linux：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
npm install
cp .env.example .env

python -m danmaku_meme_finder.cli collect --duration 180 --refresh-existing
python -m danmaku_meme_finder.cli stats
```

Windows PowerShell：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
npm install
Copy-Item .env.example .env

python -m danmaku_meme_finder.cli collect --duration 180 --refresh-existing
python -m danmaku_meme_finder.cli stats
```

## 配置

复制 `.env.example` 为 `.env`。支持：

- `USER_HASH_SALT`：可选。导入 SQLite 时会将 JSONL 的稳定用户 ID 保存为加盐 SHA-256 哈希；绝不保存昵称。
- `EXISTING_API_URL`：已有梗库接口地址。
- `EXISTING_PAGE_SIZE`：同步每页记录数，默认 `50`。

环境变量的值优先于 `.env`。不要提交 `.env`。

## 命令

### 本地管理后台

候选和网站内容较多时，推荐直接打开本地管理后台：

```bash
python -m danmaku_meme_finder.cli admin
```

它只监听 `http://127.0.0.1:8765`，默认自动打开浏览器。后台提供：

- “弹幕采集”工作区：设置采集分钟数、开始或安全停止本机 Node 采集器，并查看场次编号、SQLite 导入数和最终候选数。
- 候选逐条审核、完整标签点选、通过、仅拒绝当前文本、永久屏蔽该梗及相似梗和键盘快捷键。
- 集中编辑 `events.json`、`sessions.json`、`tags.json` 和 `memes.json`。
- 使用“新建赛事”和“新建直播场次”快速补录结构化内容；正常采集仍会自动创建直播场次。
- 显式“发布到 GitHub”按钮；点击确认后才会重建活跃目录、月度归档和趋势摘要，再提交并推送公开数据。

不希望自动打开浏览器，或端口被占用时：

```bash
python -m danmaku_meme_finder.cli admin --no-open --port 8766
```

采集按钮只是调用与 CLI 相同的本地 `run_collection()` 流程：一次只能运行一场，停止时仍会完成剩余 JSONL 导入、SQLite 落库、候选生成和场次关闭。关闭管理后台时也会请求安全停止。管理后台不会把 `live.jsonl`、SQLite 或用户标识返回给浏览器，更不能从 Vercel 公网网站远程启动本机进程。开始采集和发布前都需要本机存在最新的 `data/existing_index.json`；缺失时先执行 `sync-existing`。

管理端发布现在也是本地原始数据的安全收尾点：只有当前候选全部通过或拒绝、采集已经停止、JSONL 已完整导入后，才允许发布。GitHub 推送成功后，系统按候选携带的 `collectionOccurrences[].sessionId` 清理对应场次的 SQLite 行与 JSONL 记录，并重写 checkpoint；其他场次、未审核数据和审核拒绝记录不会被删除。清理中断时会用临时备份恢复原 JSONL。

### 采集与命令行审核

推荐直接运行一条命令进行本地采样。它启动 Node 的 `douyudm` 采集器、每 5 秒导入新增 JSONL 到 SQLite；停止时会最终落库并生成候选。候选默认要求至少重复 3 次、排除 `existing_index.json` 中已有文本，并合并明显的近似文本变体。原始弹幕仍只保留在本机数据库，绝不会上传：

```bash
python -m danmaku_meme_finder.cli collect --refresh-existing
```

按 `Ctrl+C` 停止；短时采样可直接指定秒数：

```bash
python -m danmaku_meme_finder.cli collect --duration 180 --refresh-existing
```

每次 `collect` 会在开始时抓取一次公开房间页的标题、分区、封面 URL 和真实 `rid`，并写入 Git 跟踪的 `data/sessions.json`。采集器给该次运行生成唯一 `sessionId`，JSONL 和 SQLite 中的每条弹幕都携带它。候选和正式梗使用 `collectionOccurrences` 保留每个场次内的次数及首末出现时间，网站优先按 `sessionId` 精确筛选；只有没有场次来源的旧接口记录才回退到日期关联。记录的 `observedStartedAt` / `observedEndedAt` 是本地观察和采集时间，不会伪装成斗鱼官方开播时间；元数据抓取失败不会阻塞弹幕采集。

常用参数：`--room-id`、`--database`、`--flush-interval`、`--batch-size`、`--min-count`、`--similarity-threshold`、`--output`。已有索引不存在时会自动同步；已有缓存时，使用 `--refresh-existing` 获取最新索引。

旧版本采集数据如果已经在 `sessions.json` 中补好了起止时间，可以执行一次场次回填；它会给时间范围内尚未关联的 SQLite 弹幕补上 `sessionId`，并刷新正式梗的场次明细：

```bash
python -m danmaku_meme_finder.cli backfill-sessions
```

网站只读 GitHub 数据时，先同步旧接口，再将其与人工确认的 `memes.json` 合并为统一目录。每条目录项都有稳定的五位数字 `id`（例如 `21982`）；首次导出优先沿用旧接口编号，新确认内容从当前最大编号继续分配。旧接口编号也保留在 `sources[].sourceId`。合并按规范化文本去重，保留旧接口分类和每个来源的独立统计；不同来源的次数不会相加：

```bash
python -m danmaku_meme_finder.cli sync-existing
python -m danmaku_meme_finder.cli build-catalog
```

人工审核候选时，运行下面的命令。它会逐条显示候选；输入标签编号或名称（例如 `06,HLTV`）即确认收录，输入 `?` 显示标签表，直接回车跳过，输入 `q` 结束。每次确认会立即写入 `data/memes.json`；结束时自动刷新网站目录分片与趋势摘要，并且只提交这些公开数据后推送 GitHub。传入 `--no-publish` 可只在本地保存：

```bash
python -m danmaku_meme_finder.cli review-candidates
```

一条命令完成采集和审核：运行后持续采集，按 `Ctrl+C`（或使用 `--duration`）安全落库、生成最多 20 条候选并立刻进入审核。候选会默认合并明显的重复、提及用户前缀和轻微改写，并排除与正式梗或显式屏蔽项高度相似的内容。每条候选都会显示完整标签列表；输入标签编号或名称即可收录，输入 `x` 或 `n` 只拒绝当前文本，输入 `b` 会永久屏蔽该梗及相似表达。拒绝结果会写入本地忽略的 `data/review_state.json`，后续审核不会重复显示。

```bash
python -m danmaku_meme_finder.cli collect-and-review --refresh-existing
```

同步已有梗库（自动翻页，直到空页或最后一页）：

```bash
python -m danmaku_meme_finder.cli sync-existing
```

Node 采集器先从斗鱼移动页解析靓号对应的真实 `rid`，再使用 `douyudm` v3.2.0 的 `Client` 监听 `chatmsg`。例如配置房间 `6657` 会解析到真实房间 `6979222`；导出的记录仍使用 `roomId: 6657`。每行包含 `ts`、`roomId`、`uid`、`text`；不写昵称：

```bash
npm install
node collector-js/collector.js
```

只做短时验证时，可设置自动停止时间（秒）：

```powershell
$env:COLLECTOR_MAX_SECONDS = '180'
node collector-js/collector.js
Remove-Item Env:COLLECTOR_MAX_SECONDS
```

若要在采集器因连接断开或异常退出后自动重启，运行：

```bash
node collector-js/run-collector.js
```

将尚未导入的完整 JSONL 行批量写入 SQLite。checkpoint 保存的是已提交的字节偏移，重复执行不会重复导入；正在写入但没有换行的末尾记录会留到下一次：

```bash
python -m danmaku_meme_finder.cli import-jsonl --input data/live.jsonl --checkpoint data/live.import.checkpoint.json
```

生成最近 24 小时候选：

```bash
python -m danmaku_meme_finder.cli build-candidates --window-hours 24 --min-count 3 --max-candidates 20
```

如果同一套话有加长版、重复版或轻微改写版，可额外输出一份近似文本去重后的候选。它只使用字符级比较，不会做语义聚类；原始候选文件不会被改写：

```bash
python -m danmaku_meme_finder.cli build-candidates --min-count 20 --similarity-threshold 0.82
```

查看本地数据量、最近 24 小时去重数、已有索引和候选数：

```bash
python -m danmaku_meme_finder.cli stats
```

## 数据文件

- `data/live.jsonl`：Node 采集器的仅追加原始弹幕流，含稳定用户 ID；已忽略，不应提交。
- `data/live.import.checkpoint.json`：JSONL 导入的已提交字节偏移；已忽略，不应提交。
- `data/danmaku.db`：本地 SQLite 原始弹幕库，已被忽略，不应提交。
- `data/existing_index.json`：从已有梗库同步出的规范化比对索引。
- `data/candidates.json`：稳定排序的候选输出，适合提交到 GitHub 并由后续任务审阅。
- 候选近似去重默认启用；代表项的 `similarVariants` 保留被合并的原文和计数，`familyCount` 表示整个相似文本组的出现总数。
- `data/memes.json`：人工审核后的正式梗库；`review-candidates` 会以原子方式写入它，并保留 `collectionOccurrences[].sessionId` 场次来源。
- `data/catalog/manifest.json`：目录总量、活跃月份和历史归档文件清单。
- `data/catalog/active.json`：最近三个月的活跃目录，网站首屏只读取这一份。
- `data/catalog/hot.json`：每次本地发布时从完整目录计算出的热度前 100，网站只读取结果。
- `data/catalog/search-index.json`：按需加载的全库精简索引，用于历史归档和全库搜索。
- `data/catalog/archive/YYYY-MM.json`：按最新来源月份归档的旧内容；网站进入对应日期或赛事时再加载。
- `data/trends/daily.json`：预计算的每日梗数、关联计数和标签计数，避免趋势图下载历史目录。
- `data/sessions.json`：公开直播场次快照，保存标题、网站封面路径、摘要、统计数和观察时间；发布时根据精确场次来源刷新 `memeCount`，不保存原始弹幕或观众昵称。
- `data/tags.json`：标签编号与名称的公开对照表，供本地审核和网站共用。
- `data/events.json`：手工维护的赛事日期表；网站按 `startDate` / `endDate`（含首尾日期）关联直播场次或正式梗来源日期，不需要把赛事字段重复写入每条原始弹幕。

候选规则刻意简单：排除已有文本、空/纯标点/纯 Emoji、少于 5 个字符的文本；保留达到次数阈值的高频文本，以及长度至少 20 且仅出现一次的长文本。排序优先考虑次数、独立用户数、最近出现时间和适中长度。

## 隐私与限制

项目不保存昵称。`data/live.jsonl` 按采集需求临时保存稳定用户 ID，且已在 `.gitignore` 中排除；导入 SQLite 后仅保存配置盐参与计算的不可逆 SHA-256 摘要，没有 ID 时该字段为空。所有数据仅存于本机，代码不会上传原始弹幕。

采集器依赖移动页里当前可见的 `rid` 字段和 `douyudm` 的斗鱼 WebSocket 协议实现；当前 v3.2.0 包含连接失败自动换端口重试。斗鱼继续改动页面数据、协议、访问策略或房间状态时仍可能失效；解析失败时会警告并回退为直接连接配置的房间号。`run-collector.js` 会在采集器异常退出后简单重启。项目不做语义聚类、向量检索、自动解释或自动入库。

## 测试

```bash
pytest
```

测试全部使用模拟 HTTP 响应、本地 JSONL 和 SQLite，不依赖真实斗鱼连接。可直接按 `douyudm` 官方 CLI 验证连接和录制：`npx douyudm -i 6657 --record probe.jsonl`。
