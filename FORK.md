# CloudSubscribeFork Plex compatibility fork

This fork tracks `odomu/MoviePilot-Plugins` and publishes CloudSubscribeFork builds
that use MoviePilot's generic media-server API when calculating existing TV
episodes. Since upstream 1.5.7, this uses the native generic resolver. Native
Mikan and dynamic source definitions replace our old adapter. Personal subtitle
policy remains fork-owned; see `docs/refactor-1.5.7.md` for migration ownership.

## Versioning

Published versions use:

`<upstream-version>.<upstream-commit-count>.<short-commit-as-decimal>.<fork-revision>`

Only numeric components are used because MoviePilot's version comparator treats
unknown text components as older than a normal release. The full commit remains
available in `.github/UPSTREAM_COMMIT` and in each release note.

`.github/UPSTREAM_COMMIT` records the exact upstream source commit.

## Automated updates

`sync-upstream.yml` checks upstream daily and can also be run manually. It:

1. Creates a `codex/sync-upstream-<full-SHA>` branch from fork `main`, records
   `.github/UPSTREAM_TARGET`, and opens a PR
   against fork `main` **before** attempting the merge.
2. Merges current fork `main` normally. For the upstream merge the
   `fork-identity` Git strategy presents the common ancestor and upstream tip
   under the installed backend and frontend paths. It maps the plugin identifier
   in source, tests and package metadata, then runs Git's three-way merge against
   the real fork head. Binary assets keep their original contents. The actual
   upstream SHA is the second parent. A merge base different from the recorded
   upstream commit requires review. Only numeric version metadata conflicts may be resolved
   automatically. Business conflicts stop the merge: it is aborted,
   conflicting paths are commented on the PR, and its validation status fails.
   The proposal branch need not show GitHub's native conflict banner: its failed
   validation status is the gate. Never manually merge a failed proposal PR.
3. Checks the fail-closed Plex/Mikan integration and derives a commit-based version.
4. Runs backend tests, compilation, a frontend build and disposable runtime/DB
   smoke checks with network access blocked during the test, publishing the
   `upstream-sync/validation` commit status and failure comments on the PR.
5. After successful validation, merges the exact tested PR head using a merge
   commit, then explicitly dispatches `plugins-release.yml` for CloudSubscribeFork.

No rebase, tree replacement, force push, or direct push to `main` is used.
An existing unresolved sync PR is resumed rather than creating daily duplicates.
If `main` advances during tests, the run stops and must be rerun to merge/retest.
Resolve conflicts or failed integration on the PR branch, push normally, and rerun
the sync workflow; blocked PRs are never silently discarded. A closed unmerged PR
may be proposed again if its upstream commit remains unmerged.

GitHub Actions must be allowed to create PRs in repository Actions settings.
Raw upstream branches can change workflow files relative to the fork and are
rejected by `GITHUB_TOKEN` before PR creation. Starting from fork main avoids
that failure. Actual upstream workflow changes stop with an explicit PR comment
and require an authorized account to push the reviewed merge; they are not dropped.
The workflow explicitly records validation status and dispatches release; it does
not rely on `GITHUB_TOKEN` PR/push events automatically triggering other workflows.
The release workflow builds assets after merging; failed releases remain visible
as failed Actions runs and can be retried manually. Patch scripts remain
compatibility assertions, not a mechanism to overwrite conflicts.
# Mikan search

Upstream 1.3.5 integration retains Mikan, fansub ranking, Plex compatibility,
pending-episode deduplication and immediate new-subscription search. Upstream
1.3.4 removed the Butailing provider; this fork follows that removal rather than
keeping UI options for a deleted backend. PirateBay/UIndex additions and the new
resource aggregation page are retained; existing live configuration is not edited.

The fork includes a public Mikan search provider, defaulting to https://mikanani.me.
Enable `mikan` in search source order and `magnet` in resource types. It searches
up to three title aliases, matches release titles, deduplicates info hashes,
and reuses the existing subscription filtering and 115 offline pipeline.
The configurable URL, request interval, timeout and result limit are exposed in
the Mikan settings tab. No Mikan account is required. Later seasons without an
explicit season marker are conservatively rejected; full absolute-number mapping
and per-show RSS/subgroup pinning are not implemented yet.

Fork revision `.1` adds Mikan. Normal merges preserve fork changes and history.
Integration scripts check exact markers; a conflict stops the PR for review.
# Personal anime subtitle policy (fork revision 2)

Fork revision 7 immediately queues `SubscribeAdded` events when the plugin and
`takeover_new_subscribes` are enabled and the subscription is in scope. Movies and
TV use the existing per-media debounced queue; no direct download is started by
the callback. Disabled/excluded subscriptions and invalid IDs are ignored. Cron
still retries unresolved subscriptions. This does not replay previously added
subscriptions on upgrade; those can be searched manually or wait for Cron.

Fork revision 3 supplies explicit season/episode fields for Mikan `[08]`,
`[01-03]`, and ` - 08v2` titles. Resolution and year tags are not episode numbers.
This avoids unnecessary remote torrent metadata lookups during offline submission.

Fork revision 4 reserves pending Magnet episodes per subscription/season, avoiding
simultaneous downloads of simplified/traditional/embedded variants of one episode.
Reservations disappear with the pending task; failures can be retried later.

Fork revision 5 preserves immutable CloudFile objects during file-tree traversal.
Mikan finalization validates actual filenames against the bilingual aliases in the
already-matched release, explicit episode number, season and Chinese fansub tags.
Other sources retain the normal platform matcher. Native file identities are kept
intact for cloud move and playback URL generation.

Fork revision 6 treats MoviePilot's Plex void refresh return as an accepted
request (exceptions and False still fail), not evidence of completed indexing.

Mikan results, and Japanese-animation candidates from all other automated search
sources, require both a named translation group in release tags and an explicit
Chinese-language marker. No-group, explicitly unsubtitled, and encode-only releases
(including LoliHouse or Nix-Raws without a translation-group credit) are rejected.
This is conservative title-based filtering, not inspection of subtitle tracks.
Unknown explicitly named `字幕组/字幕社/字幕屋` remain fallback candidates. English-only
unknown group names are rejected until added to the alias list.

Subjective preference tiers (equal rank within a tier): SweetSub / 千夏 / 拨雪寻春 /
喵萌奶茶屋; then 诸神 / 澄空 / 华盟 / 北宇治 / 霜庭云花; then 桜都 / 豌豆 / 动漫国 /
极影; then other named groups. Preferences precede episode coverage within the
existing resource-type, availability and official-source ordering. No automatic
replacement of already-owned episodes is enabled. Applies to new candidates only,
never renames or rejects files already in the library.

Reference checked 2026-09-05: https://flynncao.uk/posts/translation-group-review/
and community discussion https://bangumi.tv/group/topic/385688 . These are opinions,
not universal scores; the second/third tiers include coverage-oriented fallback
choices rather than claiming every group has been scientifically ranked.
The policy is maintained in `search/fansubs.py`, covered by tests and preserved
by upstream-sync. Mikan UI describes the active policy.

## Fork 保留的洗版与整理说明
“启用网盘洗版”处理网盘搜索候选。订阅必须已开启 MoviePilot 原生 `best_version`；未选择洗版范围时处理全部此类订阅，选择后只处理指定订阅。

插件以 MoviePilot `pri_order`、真实整理记录、插件转存历史、媒体库路径和真实网盘文件建立旧版本基线。无法确认旧网盘文件时不执行替换；没有旧版本的普通候选仍按正常转存处理。

### PT 洗版

“启用 PT 洗版”默认关闭。开启后监听 MoviePilot `TransferComplete`：只有带下载器和下载 Hash、且已整理到本地存储的 PT/RSS
文件才进入判断。符合 `best_version`、洗版范围和评分条件后，文件上传到当前网盘暂存目录，再复用统一替换与后处理链。

115、123、夸克和光鸭均支持 PT 上传。上传在后台执行，不移动或删除下载器源文件，不影响保种。电视剧只处理能明确识别季集的单集文件，季包或无法确认集号的文件会跳过。

洗版模式：

- 保留最大文件：评分相同仅在新文件更大时替换。
- 保留最小文件：评分相同仅在新文件更小时替换。
- 直接替换：满足优先级条件后替换旧版本。
- 新旧共存：保留旧文件，并为新版本生成不冲突的名称。

“评分自愈间隔”用于刷新洗版基线。PT 洗版没有找到旧网盘文件时，可将符合条件的本地文件作为新的网盘版本上传。

## 通知与历史

- “发送消息通知”控制 MoviePilot 消息，并可选择通知类型。
- “启用入库通知”在 STRM 或目标文件就绪后通知所选媒体服务器，不执行全库扫描。
- Emby 媒体信息提取使用 MoviePilot 中已配置的 Emby 服务。
- 订阅缺集检查和洗版基线通过 MoviePilot 媒体服务器接口读取，支持 Emby、Jellyfin、Plex、飞牛影视、 MediaVault、极影视和绿联影视；Emby
  媒体流详情提取仍仅用于 Emby。
- 媒体服务器路径映射每行使用 `媒体服务器路径#MoviePilot 路径`。
- Webhook 支持 GET/POST、独立地址和超时。

历史页支持筛选、通知、重试、单条/批量删除和从历史或媒体服务器内容发起手动网盘洗版。运行中的后处理历史允许删除其任务状态；关联文件删除必须由用户单独选择。

## 平台入口

- 侧栏工作台：运行任务、PT 上传进度、历史、手动资源、离线任务和缓存管理。
- 远程命令：`/cloud_sync`、`/cloud_status`、`/cloud_link`、`/cloud_cache_clear`。
- 智能体：查询状态、启动同步、搜索与选择资源、提交链接、清理缓存和更新配置。
- 工作流：执行订阅搜索或处理上下文中的资源链接。
- 仪表板：显示运行摘要、任务和转存统计。

## 源码与许可

源码模块和 Release 目录结构见 [`plugins.v2/cloudsubscribefork/README.md`](plugins.v2/cloudsubscribefork/README.md)
。本插件按 [GNU General Public License v3.0](LICENSE) 许可。
