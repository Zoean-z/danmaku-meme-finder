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

推荐直接运行一条命令进行本地采样。它启动 Node 的 `douyudm` 采集器、每 5 秒导入新增 JSONL 到 SQLite；停止时会最终落库并生成候选。候选默认要求至少重复 3 次、排除 `existing_index.json` 中已有文本，并合并明显的近似文本变体。原始弹幕仍只保留在本机数据库，绝不会上传：

```bash
python -m danmaku_meme_finder.cli collect --refresh-existing
```

按 `Ctrl+C` 停止；短时采样可直接指定秒数：

```bash
python -m danmaku_meme_finder.cli collect --duration 180 --refresh-existing
```

每次 `collect` 会在开始时抓取一次公开房间页的标题、分区、封面 URL 和真实 `rid`，并写入 Git 跟踪的 `data/sessions.json`。记录的 `observedStartedAt` / `observedEndedAt` 是本地观察和采集时间，不会伪装成斗鱼官方开播时间；元数据抓取失败不会阻塞弹幕采集。

常用参数：`--room-id`、`--database`、`--flush-interval`、`--batch-size`、`--min-count`、`--similarity-threshold`、`--output`。已有索引不存在时会自动同步；已有缓存时，使用 `--refresh-existing` 获取最新索引。

网站只读 GitHub 数据时，先同步旧接口，再将其与人工确认的 `memes.json` 合并为统一目录。每条目录项都有稳定的五位数字 `id`（例如 `21982`）；首次导出优先沿用旧接口编号，新确认内容从当前最大编号继续分配。旧接口编号也保留在 `sources[].sourceId`。合并按规范化文本去重，保留旧接口分类和每个来源的独立统计；不同来源的次数不会相加：

```bash
python -m danmaku_meme_finder.cli sync-existing
python -m danmaku_meme_finder.cli build-catalog
```

人工审核候选时，运行下面的命令。它会逐条显示候选；输入标签编号（例如 `06,24`）即确认收录，直接回车跳过，输入 `q` 结束。每次确认会立即写入 `data/memes.json`，结束时自动刷新网站目录：

```bash
python -m danmaku_meme_finder.cli review-candidates
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
python -m danmaku_meme_finder.cli build-candidates --window-hours 24 --min-count 3 --max-candidates 200
```

如果同一套话有加长版、重复版或轻微改写版，可额外输出一份近似文本去重后的候选。它只使用字符级比较，不会做语义聚类；原始候选文件不会被改写：

```bash
python -m danmaku_meme_finder.cli build-candidates --min-count 20 --similarity-threshold 0.88 --output data/candidates-deduplicated.json
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
- `data/candidates-deduplicated.json`：可选的近似文本去重结果；代表项的 `similarVariants` 保留被合并的原文和计数。
- `data/memes.json`：人工审核后的正式梗库；`review-candidates` 会以原子方式写入它。
- `data/catalog.json`：网站读取的统一静态目录，融合旧接口梗和本地正式梗，并保留标签与来源信息。
- `data/sessions.json`：公开直播场次快照，保存标题、分区、斗鱼封面 URL、观察时间和消息数；不保存原始弹幕或观众昵称。

候选规则刻意简单：排除已有文本、空/纯标点/纯 Emoji、少于 2 个字符的文本；保留达到次数阈值的高频文本，以及长度至少 20 且仅出现一次的长文本。排序优先考虑次数、独立用户数、最近出现时间和适中长度。

## 隐私与限制

项目不保存昵称。`data/live.jsonl` 按采集需求临时保存稳定用户 ID，且已在 `.gitignore` 中排除；导入 SQLite 后仅保存配置盐参与计算的不可逆 SHA-256 摘要，没有 ID 时该字段为空。所有数据仅存于本机，代码不会上传原始弹幕。

采集器依赖移动页里当前可见的 `rid` 字段和 `douyudm` 的斗鱼 WebSocket 协议实现；当前 v3.2.0 包含连接失败自动换端口重试。斗鱼继续改动页面数据、协议、访问策略或房间状态时仍可能失效；解析失败时会警告并回退为直接连接配置的房间号。`run-collector.js` 会在采集器异常退出后简单重启。项目不做语义聚类、向量检索、自动解释或自动入库。

## 测试

```bash
pytest
```

测试全部使用模拟 HTTP 响应、本地 JSONL 和 SQLite，不依赖真实斗鱼连接。可直接按 `douyudm` 官方 CLI 验证连接和录制：`npx douyudm -i 6657 --record probe.jsonl`。
