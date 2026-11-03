# #926 示例检查的核验

2026-11-03。问题：`sourcemeta/jsonschema` 10 月 29 日合并的「检查 OpenAPI `example` 字段」
那条规则，能不能抓到 v2 里那 4 个和自己 schema 冲突的 example？以及能不能碰到两份被拒读的文档？

**结论先说：抓不到——因为那条规则还没有出现在任何一个已发布的版本里。所以这次核验只能到
「规则的条件全部满足、机制判定为拒」为止，不能给一次真实运行的读数。**

## 1. 规则本身（读源码，不是猜）

PR `sourcemeta/jsonschema#926`「Lint the `example` keyword in OpenAPI schema objects」，
合并时间 **2026-10-29T14:35:27Z**，6 个文件，新规则在
`vendor/blaze/src/alterschema/linter/valid_example.h`。

- 规则 id：`valid_example`（单数）
- 描述字符串：`Only set an \`example\` value that validates against the schema`
- 生效条件（`ONLY_CONTINUE_IF`）：
  1. 文档词表含 `OPENAPI_3_0_BASE` / `3_1_BASE` / `3_2_BASE` 之一；
  2. 该 schema 对象是 object 且**定义了 `example`**；
  3. 若是 3.0，该对象**不能有同级 `$ref`**（有就跳过）。
- 命中时报告在 `{"example"}` 这个位置；`--fix` 的行为是**直接删掉这个 `example`**。

## 2. 为什么跑不了

| 检查 | 结果 |
|---|---|
| `jsonschema lint <file> --only valid_example` | `error: The following linting rule does not exist`，**exit 5** |
| `jsonschema lint <file> --only valid_examples` | exit 0（这是另一个旧规则，只查 `examples` 数组） |
| `jsonschema lint --list`（310 条规则）里 id 含 `example` 的 | 只有 `duplicate_examples`、`top_level_examples`、`valid_examples` |
| 二进制里搜描述串 `Only set an` | 0 命中 |

版本时间对不上：v17.3.2 发布于 **2026-10-28T22:54:08Z**，比 #926 合并早 **16 小时**。
#926 之后没有新 release（`/releases` 最新仍是 v17.3.2）。

CI 侧也没有可捡的产物：#926 合并后 main 上的 CD 运行全部失败——
`40893007233`（#926，19m13s，failure）、`41122107323`（#927，30m13s，failure）、
`41543840291`（#928，14m51s，failure）。只有 tag 触发的 CD 成功过（v17.3.0/17.3.1/17.3.2）。

本机也没有编译条件：`cl.exe`、`clang++`、`g++`、`cmake` 四个都不在 PATH 上。

## 3. 规则的条件在 4 个站点是否满足（静态判定）

4 个冲突 example 全部长在 `components.schemas.<Name>` 的 schema 对象上，都不是 property 级，
都没有同级 `$ref`：

| 文件 :: schema | 对象键 | 同级 `$ref` | 满足规则条件 |
|---|---|---|---|
| isendpro :: `SMSRequest` | `example, properties, required, type` | 否 | 是 |
| personio :: `NewAttendancePeriodRequest` | `example, properties, title, type` | 否 | 是 |
| personio :: `UpdateAttendancePeriodRequest` | `example, properties, title, type` | 否 | 是 |
| vtex Subscriptions :: `settings` | `description, example, properties, required, title, type` | 否 | 是 |

## 4. 规则会用的那套机制，用 17.3.2 实际跑了

规则做的事就是「编译该 schema 对象 + 用同一个求值器验证它的 `example`」。这套机制在 17.3.2
里可用，逐个跑（原始输出 `out/baseline_rejects.txt`）：

| 站点 | exit | 失败位置 | 原文 |
|---|---|---|---|
| isendpro `SMSRequest` | 2 | `/sms` | `The value was expected to be of type array but it was of type string` |
| personio `NewAttendancePeriodRequest` | 2 | `/attendances/0/comment` | `expected to be of type string but it was of type object` |
| personio `UpdateAttendancePeriodRequest` | 2 | `/comment` | `expected to be of type string but it was of type null` |
| vtex Subscriptions `settings` | 2 | `/orderCustomDataAppId` | `expected to be of type string but it was of type null` |

**这是推断，不是运行**：规则将来跑起来应该 4 个全报，理由是条件全部满足、且它调用的求值器
在同样的输入上给出 4 个失败。谁也没法在 17.3.2 上直接观察 `valid_example` 的输出。

顺带一个细节：personio 的 `NewAttendancePeriodRequest.example` 里，`comment` 的值写成了
`{"$ref": "#/components/schemas/UpdateAttendancePeriodRequest/example/comment"}`——
作者在 example 里用 `$ref` 指向另一个 example 的子树，而那个子树的值是 `null`。
OAS 3.0 里 example 内部的 `$ref` 只是数据，不解析，所以这个对象原样进了验证，被要求是 string。

## 5. 两份被拒读的文档

`lint` 在这两份上同样在文档层就退出，根本没走到任何 example 检查：

```
error: The Paths Object keys must not repeat a templated path
  at line 218        (lgtm.com/v1.0)
  at line 4219       (vtex.local:Marketplace-Protocol/1.0)
```

`lint` 的退出码 4，无 JSON 输出，`rules={}`。也就是说这类文档对 `valid_example` 是不可见的——
不是规则漏报，是文档在更早的一层就被拦了。

## 6. 对文章的影响

不能写「他的新规则在真实数据上抓到了 5%」。能写的事实只有两条：

1. 他的 CLI 会在读文档这一层拒掉不合规的 OpenAPI（2/20 份），别的只查 schema 的实现碰不到；
2. `valid_example` 规则在 main 上，还没进 release。这条对 Juan 有用：他 10 月 29 日合并的功能，
   到现在（11 月 3 日）没有任何一个发布版本带它，而 main 上的 CD 连续三次失败。

第 2 条要不要告他、怎么告，等你看完再定。我不主动发。

## 7. 复现

```
python lint_check.py          # 5 份文档的 lint 原始输出 → out/lint/
jsonschema lint <file> --only valid_example    # 期望 exit 5：规则不存在
```
