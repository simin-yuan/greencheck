# numbers_check — 每个数字对应哪个产物

`draft.md` 正文不再印方括号产物名（对外成稿不该像审计报告）。**这份文件是唯一的映射表**：
文中每个数字，到这里指到文件和字段，字段值可以现场重算。

两个来源目录（公开发布后会变成仓库内的 `studies/` 两个子目录）：

- **S** = `schemastore_mutation_study_20261011/`
- **O** = `openapi30_example_seed_v2_20261103/`

全部数字出自**同一份冻结口径 x16（分母 1,382 / 883）**。x12（分母 450/382/932）与 x13（382）
只在推导链里出现，不进正文——一篇文章只许有一套分母。

| # | 文中位置 | 数字 | 产物 | 字段 / 位置 |
|---|---|---|---|---|
| 1 | §2 | commit `778278bb` | S | `out/results.json` → `aggregate.schemastore_commit` |
| 2 | §2 | 38 pairs | S | `out/results.json` → `aggregate.pairs` |
| 3 | §2 | greencheck 0.4.0 | S | `out/results.json` → `aggregate.greencheck`、`greencheck_commit` |
| 4 | §2 | Python jsonschema 4.26.0 | S | `out/results.json` → `aggregate.jsonschema` |
| 5 | §2 | CLI 载入 33 / 38 | S | `out/x3_compare3.json` → `population.pairs_eligible`=33、`pairs_excluded`=5、`excluded_reason` |
| 6 | §2 | 1,681 / 1,699 | S | `out/x3_compare3.json` → `agreement.three_way_agree`、`population.mutants_eligible` |
| 7 | §2 | 1,704 份 OpenAPI 3.0 | O | `out/sample.json` → `frame_size` |
| 8 | §2 | 第二个样本 Sourcemeta 17.3.2 | O | `jsonschema.exe --version`；`out/run.log` |
| 8b | §2 | 第一个样本 Sourcemeta **17.2.0** | S | `out/x3_compare3.json` → `engines.sourcemeta`（`jsonschema v17.2.0 windows-x86_64, --format-assertion (primary)`） |
| 9 | §3 | 1,791 judged | S | `out/results.json` → `aggregate.judged_total` |
| 10 | §3 | 1,382 / 77% | S | `out/x3_compare3.json` → `engines.ci_ajv`（`release 1382 / reject 409`）；1382/1791 = 77.16% |
| 11 | §3 | 1,402 / 78% | S | `out/results.json` → `aggregate.escaped`=1402、`escaped_ratio_judged`=0.78280 |
| 12 | §3 | 差 20 | S | 1402 − 1382，同分母 1791 |
| 13 | §3 | 18 处分歧 | S | `out/x3_compare3.json` → `agreement.divergences`=18、`divergences_within_ci_released`=0、`classification.D2_format_assertion`=18 |
| 14 | §3 | **499** = 368 + 82 + 49 | S | `out/x16_merged_basis.json` → `summary.classes.already-expressed.escapes`；`summary.removal_breakdown` 三个分项 |
| 15 | §3 | **333** = 248 + 85 | S | 同文件 `classes.undeclared-key.escapes`；`composition.added-undeclared-key`=248、`removed-undeclared-key`=85 |
| 16 | §3 | ~~248 = 139 + 109~~ | S | **正文已删这组拆分**。留作推导：`strata.UNDECLARED-KEY`=248，按 `label×op` 拆 139 删行 + 109 清空 |
| 17 | §3 | **550** | S | `out/x16_merged_basis.json` → `classes.unconstrained-value.escapes` |
| 18 | §3 | **883** = 333 + 550 | S | 同文件 `summary.population.needs_annotation` |
| 19 | §3 | 85 抽 / 83 接受 | S | `out/x12_annotation_basis.json` → `classes.already-expressed.real_tool_spot_check`；逐 case 重算见 `out/a_layer_split_v2.json`（83 接受 / 2 拒绝 / 85） |
| 20 | §4 | 217（12.7%） | O | `out/sample.json` → `eligible_size`；217/1704 = 12.73% |
| 21 | §4 | 20 份 / 每份 5 / seed / 8 KB | O | `out/sample.json` → `n`、`cap_per_spec`、`seed=20261103`；8 KB = `study.py` 的 `MAX_EXAMPLE_BYTES=8192` |
| 22 | §4 | 85 seeds | O | `out/stats.txt` → `cases`；`out/cases.csv` 行数 85 |
| 23 | §4 | 71 / 4 / 10 | O | `out/stats.txt` → `baseline`（ACCEPT 71 / REJECT 4 / ENGINE-ERROR 10） |
| 24 | §4 | 1,126 / 581（52%）/ 545 | O | `out/stats.txt` → `mutants`、`parse_broken`、`parse_broken_share` 0.516、`judged` |
| 25 | §4 | 304 / 55.8% / 中位 0.54 | O | `out/stats.txt` → `escaped` 304、`escape_rate_pooled` 0.5578、`escape_rate_median_case` 0.5394 |
| 26 | §4 | 225 / 68 / 11 | O | `out/stats.txt` → `classes`；明细 `out/escapes.jsonl` |
| 27 | §4 | 4 个 example 冲突 | O | `out/baseline_rejects.txt`（四条 CLI 原文，位置 `/sms`、`/attendances/0/comment`、`/comment`、`/orderCustomDataAppId`） |
| 28 | §4 | line 218 / 4219 | O | `out/lint/lgtm.com_v1.0.json.txt`、`out/lint/vtex.local_Marketplace-Protocol_1.0.json.txt` |
| 29 | §6 | 308 / 333、510 / 550 | S | `out/x16_merged_basis.json` → `classes.undeclared-key` / `classes.unconstrained-value` 的 escapes 与 `population.unreachable_by_reason`（25 / 40 在 `map_strata.py` 里拆开） |
| 30 | §6 | 818 / 1,317 / 65 | S | 同文件 `population.coverable`=818、`escaped_mutants`−`unreachable`=1317、`unreachable`=65（31+25+9） |
| 31 | §7 | 中位 2 / min 1 / Q3 4.25 / max 13 / 36 个 | S | `out/x16_merged_basis.json` → `summary.sites_to_half` |
| 32 | §7 | 401 / 883、60 | S | 同文件 `by_write_site.annotation_acts.cumulative_at.20.escaped_mutants`=401（`of_all_escapes` 0.4541，分母 883）；`by_instance_path...cumulative_at.20`=60 |
| 33 | §7 | 41 allOf → 11 基类 | O | `out/bases.txt` → Scope B |
| 34 | §7 | 11/11 没写 `additionalProperties` | O | `out/bases.txt` → 写成 true / schema / false 各 0，缺省 11 |
| 35 | §7 | 11 声明 properties / 9 声明 required | O | `out/bases.txt` 同段 |
| 36 | §7 | 1,009 / 2,793（36.1%） | O | `out/bases.txt` → Scope C；1009/2793 = 36.12% |
| 37 | §8 | 312（17.2.0 口径） | S | `out/x3_positions.json` → `summary.coverage.lint_flags_the_same_node`=312；同文件 `summary.reading` 说明这是 Sourcemeta 自家规则，不是独立证据 |
| 38 | §8 | #632 / #1975 | — | sourcemeta/jsonschema#632（规则已移除）、sourcemeta/core#1975（待办条目 `unbounded_collection_limits`） |
| 39 | §9 | 54 / 16 / 10 / 4 | O | `out/stats.txt` → `cases_with_judged` 54；16 见第四节；10 = ENGINE-ERROR；4 = REJECT |
| 40 | §9 | 197 / 217 未抽中 | O | `out/sample.json`：217 − 20 = 197 |
| 41 | §9 | 6 份下载失败 | O | `out/eligible.json` → `errors` = 6 |
| 42 | §9 | 65 of 883 / 5 of 38 | S | `out/x16_merged_basis.json` → `population.unreachable`=65；`out/x3_compare3.json` → `population.pairs_excluded`=5 |

## 一、口径：这一轮统一到 x16

- **x16**（`x16_merged_basis.json`）：分母 1,382 / 883，正文全部用它。
- **x12**（`x12_annotation_basis.json`）：450 / 382 / 932，只在推导链（499 与 333 怎么从 450+382 移过来）里用。
- **x13**：382 口径，上一版 §6 那段用它的 283/84/15，已整段删除，正文不再出现。

九类 → 三类的合并规则与十条恒等式在 `map_strata.py` / `map_strata.out`；
x16 的逐字段原文在 `x16_numbers.py` / `x16_numbers.out`。两个脚本都在
`studies/openapi30-2026-11/` 下，公开仓库里 `./studies/reproduce.sh` 一条命令跑完。

## 二、248 与 333：正文已删掉这组拆分

**正文只用 333，不出现 248、不出现 382、不出现 139/109/85。** 这组拆分删掉的原因是它挡不住追问：

1. **两个 248 未必是同一批变异体。** `x3_positions` 的 248 是 `label=UNDECLARED-KEY`，
   按算子拆 139 删行 + 109 清空；`x16` 的 248 挂在 `composition.added-undeclared-key` 下。
   产物里没有逐条的 mutant id，所以**无法证明是同一批**（`map_strata.out` 旧版那句
   「两个 248 在不同分区上计数」说的就是这件事，现已改成单线推导）。
2. **"added" 这个标签与算子互斥。** 删行和清空都不是"新增了一个键"。若 x16 的 248 真的含
   139 条删行，标签就是错的；若不含，两个 248 就是两个集合。两种情况下，正文里把
   「139 + 109」挂到 333 上都不成立。

333 现在的单线来源：**382（x12 的 undeclared-key 类）− 49（x16 收回"已声明"的那批）
= 333**。要追 333 就用这条路，不要绕 248。

**对外产物怎么处理**：`x16_merged_basis.json` 是 write-once 冻结件，不改字段名；在
`studies/README.md` 里加一段定义，说明 `added-undeclared-key` 指的是"变异后实例里存在、
而 schema 在该位置及其链路上都没有声明的键"，并注明这个标签沿用旧产物、不精确。

正文只用 333，不出现 248、不出现 382。领英那个 248 与大纲的 333 都能由同一批产物重推。

## 三、这一轮改了什么

1. **删掉 AI 辅助声明整行。** 官方博客投稿指南（`json-schema-org/community/docs/blog-guidelines.md`）
   通篇没有 AI 披露要求，见汇报里的原文核查。
2. **新增 §6 注解草案**（约 200 词），两个关键字各配一个最小 JSON 片段；覆盖数用
   308/333 + 510/550 = 818，加 499 得 1,317/1,382，65 个表达不了。
3. **删掉正文所有方括号产物名**，映射全部搬到本文件。
4. **删掉原 §6「Where the silence lives」**（x13 的 382 口径与正文 333 不同基）。
5. **§6/§7 的数字从 x12 换成 x16**：中位 2、401、60（原来是 423 / 60，分母 932）。
6. **§2 补上第三个引擎**：CLI 载入 33/38，三引擎 1,681/1,699 一致。
7. **§9 补 L 局限**：语料以机器生成的 AWS 描述为主。

## 四、标量种子那 16 个

`out/cases.csv` 85 行，每行的种子是该 spec 的 `components.schemas.<name>.example`。
逐条判 JSON 类型：67 对象、2 数组、**16 标量**。结构算子在这 16 个上只能产
`drop-file` / `empty-file`，全部解析失败，可判变异 0。于是 85 − 16 − 10 − 4 = 55，
再减 1 个「对象但四个算子全部不可判」的 case，得 54 = `stats.csv` 的 `cases_with_judged`。

## 五、17.3.2 下的 lint 重跑：没跑出可用的数

三样输出互相矛盾，所以 §8 只把 312 标成 17.2.0 口径，不声称它代表今天的 CLI。

| 路径 | 结果 |
|---|---|
| 冻结的 17.2.0 artifact | 1,382 个逃逸里 **312** 个落在被标记的节点上，9 条规则 |
| 用 17.3.2 重跑 `x3_positions.py` | **0**（明显是管道问题：1,955 条 finding 的指针都能解析） |
| 我另写的独立匹配 `x3_lint_coverage_1732.py` | 17.3.2 上 **37**，17.2.0 上 **4** |

第三行是关键的仪器自检：它在已知答案（312）的 17.2.0 数据上只给出 4，
说明**这个匹配器本身是错的**，所以它的 37 也不能用。第一、三行都不是可用读数。

规则数量本身是事实，且可复核：`x3_compare3.json` 记 17.2.0 有 103 条；
`jsonschema lint --list` 数 17.3.2 有 310 条。**规则从 103 涨到 310，但这批逃逸在新规则下
被标记多少，目前没有可信的数。**

要拿到这个数，得先把 `x3_positions.py` 的 `idx2sch` / 节点比对在 17.3.2 上修通，
或者用 17.2.0 当阳性对照重写匹配器。这是独立的一小块活，不含在交稿前的范围里。

## 六、§4 那句 #926

> These are the errors `valid_example` (sourcemeta/jsonschema#926) exists to catch;
> at the time of writing the rule had not shipped in a release.

不写 CD、不写构建失败、不写「应该 4/4」的推断。完整核验在 `O/LINT_CHECK.md`。
新版本发布后这句可换成实跑读数，位置不用动。
