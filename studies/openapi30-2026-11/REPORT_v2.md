# OpenAPI 3.0 example-as-seed mutation study — v2 结果

2026-11-03。所有数字来自 `out/stats.txt`、`out/bases.txt`、`out/audit_v1.txt`（脚本从产物重算）。
`check.py` 把每一个判定用一条实例一次 CLI 调用重跑过一遍，`all checks agree`，rc=0。
方法在跑之前冻结：`METHOD_v2.md`，sha256 `a3a4aba015a1ace203e6cabfd336aaf272546f78699550c8af631942c74e5fc1`（04:38:44）。

## 0. 先核两件旧事

**主裁判。** 是 `sourcemeta/jsonschema` 的 `validate --entrypoint`，版本 **17.3.2**
（`jsonschema.exe --version` → `17.3.2`；二进制在
`jsonschema`，
zip 与 `CHECKSUMS.txt` 已核 sha256）。v1 和 v2 都是它，不是替身。

**"0 个 required"要分三层说，v1 那句话说过头了。** 逐个展开 91 个入口 schema 的 `$ref` 与
`allOf` 之后：

| 层 | 数 |
|---|---|
| 在入口 schema **自己的对象节点**上声明 `required`（含 allOf 折叠） | **0 / 91** |
| 只在其内部更深的对象里声明（3–4 层下，全是 ECS 的嵌套管段） | 5 / 91 |
| 整棵树里一个 `required` 都没有 | 86 / 91 |

所以正确的说法是：**没有一个例子对象自己说了哪些字段必填**；5 个例子对象内部嵌着的子对象有
`required`（`deploymentCircuitBreaker`、`alarms` 那一层）。v1 报告里的"91 个 schema 里没有一个
声明 required（含 allOf 分支）"在这三层里只对第一层成立，其余两层不成立。已按上表改。

## 1. v1 是试跑，为什么改口径

v1 从整个 3.0 母集抽 20 份，不知道 example 在哪：20 份里只有 5 份有货，427 个逃逸中 306 个
（72%）来自 `amazonaws:ecs` 一份。汇总率描述的是一个文件。
v2 只改两件事——抽样范围（只从至少带一个合格 example 的文档里抽）和每份上限（5 个）。
变异算子、判定、分类、复核全部沿用 v1。v1 的数保留，不覆盖。

## 2. 样本

| 项 | 值 |
|---|---|
| 母集（APIs.guru 的 OpenAPI 3.0 文档） | 1704（下载失败 6） |
| 合格文档（至少 1 个 ≤8KB 的 schema 级 `example`） | **217（12.7%）** |
| 抽样 | 20 份，种子 20261103，每份上限 5 |
| 用例 | 85 |
| 贡献了用例的文档 | **20 / 20**（v1 是 5 / 20） |
| 合格文档里的可用用例总数 | 4846 |

## 3. 基线：example 能不能当种子

| 结果 | 数 |
|---|---|
| 通过自己的 schema | **71** |
| 被自己的 schema 拒绝 | **4** |
| 无法判定（文档本身读不进去） | **10**（2 份文档） |

## 4. 变异

| 项 | 值 |
|---|---|
| 变异体 | 1126 |
| 解析不了（不计入分母） | 581（51.6%）：文件级 170，删行破坏 JSON 411 |
| 可判 | 545 |
| 逃逸 | **304（汇总 55.8%，按 case 中位数 0.539）** |
| 被拒 | 241 |
| 引擎错误 | 0 |

| 类 | 数 |
|---|---|
| `value-level` | 225 |
| `declared-optional-removed` | 68 |
| `undeclared-key` | 11 |
| `ANOMALY` | 0 |
| `unresolved` | 0 |

allOf 基类节点上的逃逸：7（2.3%）。

集中度：最高的 `vtex.local:Giftcard-API` 120 个可判（22%），第二名 77（14%）。
v1 是 306/427 = 72% 一家，v2 面板被摊开了——但 22% 仍然偏重，引用时照 per-spec 给。

## 5. v2 才看见的三件事

**a) 两份文档不是合法的 OpenAPI 3.0，CLI 直接拒读（exit 4）。**
`lgtm.com/v1.0`（line 218，`/analyses/{project-id}`）和 `vtex.local:Marketplace-Protocol/1.0`
（line 4219，`/{marketplaceService…}/pvt/orders/{…}/cancel`）都在 Paths Object 里重复了同一个
模板路径，报错 `The Paths Object keys must not repeat a templated path`——OAS 3.0 明确禁止。
**这是文档的错，不是求值器的错。** 10 个用例因此没有判定；它们不是"逃逸"，也不是"被拦"。
这一条同时说明：拿 CLI 和别的实现做差分时，若不区分"文档层失败"和"实例层判定"，会凭空
生成一批假 bug。

**b) 4 个 example 与自己的 schema 打架，全部是类型层。**

| 文档 / schema | 位置 | 冲突 |
|---|---|---|
| isendpro / SMSRequest | `/sms` | 例子是 string，schema 要 array |
| personio / NewAttendancePeriodRequest | `/attendances/0/comment` | 例子是 object，schema 要 string |
| personio / UpdateAttendancePeriodRequest | `/comment` | 例子是 null，schema 要 string |
| vtex Subscriptions / settings | `/orderCustomDataAppId` | 例子是 null，schema 要 string |

四个里有两个是"作者拿 null 当占位符"（该位置要 string）。这是文档自身的不一致，任何一个
校验器都会拒——**不能当 bug 报给 Juan**。

**c) 种子的形状决定这套方法能不能说话。** 85 个 example 里 67 个是对象、2 个数组、16 个标量。
16 个标量（`CreatedAt`、`JobId`、`TweetText` 这种）上，结构变异算子只能产出文件级噪声，
可判变异为 0。加上 10 个文档级失败和 4 个基线被拒，85 个用例里 **31 个没有产生任何可判变异**，
真正进入统计的是 54 个。这不是参数问题，是 greencheck 的算子形状与种子的形状不匹配。

## 6. 静态统计：Juan 的"基类故意留开口"

不新增算子，只读 schema。

**A. 变异跑过的 85 个入口 schema 里，通过 allOf 继承基类的：0 个。**
即：v1/v2 的变异语料根本没有落到基类上。"未声明 key 逃逸 11 个"回答不了基类问题。

**B. 把范围放到 20 份文档的全部 component schema：**

| 项 | 数 |
|---|---|
| 使用 `allOf` 的 component schema | 41 |
| 经 allOf 抵达的不同基类 | 11 |
| 基类里 `additionalProperties` 写成 `true` / schema / `false` | 0 / 0 / 0 |
| 基类里 **完全没写** `additionalProperties` | **11 / 11** |
| 基类声明了 `properties` | 11 / 11 |
| 基类声明了 `required` | 9 / 11 |

基类确实"留了开口"，但方式不是写 `additionalProperties: true`——是**一个字都不写**。
11 个基类没有一个提到 `additionalProperties`。这正好是默认允许任意额外字段的那一种，
也正好是校验器无法区分的：没法从"没写"推断"故意留开口"还是"忘了写"。

**C. 声明了字段却从不说哪些必填的对象（可做 lint 规则）：**

| 项 | 数 |
|---|---|
| component schema 总数 | 2793 |
| 声明了 `properties`（自身或经 allOf） | 1620 |
| 其中有 `properties`、整棵树没有 `required` | **1009（占全部 36.1%）** |
| 其中复合（allOf）的 | 3 |

集中在 securityhub（563/972）、s3（141/574）、twitter（75/235）、organizations（67/233）。
解读要小心：响应对象大多字段确实可选，36.1% 不等于 36.1% 的错。它说的是"这份语料里
三分之一的字段清单不区分必填与可选"，而不是"三分之一是 bug"。

## 7. 差分

545 个判定同时交给 `openapi_schema_validator` 的 `OAS30Validator`：**0 处不一致**，0 次异常。
（v1：525 次比对 0 分歧。）

**没有找到 Sourcemeta 的 bug。** 不发私信、不提 issue。差分只覆盖文本级变异能碰到的浅层改动，
所以结论只能写成"这批变异里两个实现对同一批实例判断一致"。

## 8. 口径与局限

- 逃逸率分母是"可判变异"（545），不是全部变异体（1126）。
- 51.6% 的变异体连 JSON 都解析不了——这是文本级变异器的结构性上限（见 5c）。
- 197 / 217（90.8%）的合格文档没被抽中；20 份样本对 217 份的主体推断力有限（`out/sample.json`）。
- 6 份文档下载失败，未计入母集，未说明原因（`out/eligible.json` 的 `errors`）。
- "36.1% 不说必填"是描述，不是缺陷率；响应模型天然多可选。
- 没有测类型替换、边界值、添加未声明键——那些需要 JSON 感知的算子。

## 9. 复现

```
cd .
./run_v2.sh                # 全链：抽样 → 变异 → 逐条复核 → 统计 → 静态统计 → v1 复核
./run_v2.sh --from-scan    # 连 1704 份母集重扫（3 分钟）再抽
```

产物：`out/sample.json`（seed、sha256、每份的合格数与选中项）、`out/cases.csv`、
`out/escapes.jsonl`、`out/summary.json`、`out/bases.json`、`out/audit_v1_required.json`。
