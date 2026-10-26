# 发布手册

不放进 README 的链接，是给发布的人看的：发哪里、先说什么、被质疑怎么答。
每一条答案都指向仓库里已经有证据的文件，而不是「我们觉得」。

## 一句话（贴哪都能用）

> 把演示原样回放，在演示页上 100 分，页面改一次只剩 25 分；而从一次演示里归纳出的
> skill，两个页面都是 100。这个仓库把这条基线跑了，也把「agent 说完成了」值多少
> 钱量了出来：无校验 10/10 是假的，有闸门 18/18 是真的。

英文版：

> Replaying the recorded demonstration scores 100 on the page it came from and 25
> after a UI revision. A skill induced from the same single demonstration scores
> 100 on both. That baseline is the one nobody runs.

## 发哪里

| 地方 | 形态 | 备注 |
|---|---|---|
| Show HN | 标题 + 正文 + 自己首评 | 用 [en.md](en.md)；首评必须自己先把弱点说了，否则前三条评论都在问 N=3 |
| r/MachineLearning | `[P]` 帖 | 同上；标题里带 benchmark / evaluation 比带 tool 有效 |
| X / Twitter | 1 条主帖 + 3 条回复 | 用下面的「三条引用句」 |
| V2EX「分享创造」 | 标题 + 正文 | 用 [zh.md](zh.md)；V2EX 会问「所以能干嘛」，准备好第 2 条答案 |
| 即刻 / 小红书 | 短版 | 只留一个数 + 一张图（`docs/assets/ladder.png`） |

**别同时全发。** 先发一个（HN 或 V2EX），看第一条真实反对意见是什么，再按那个反对意见改另外两处的开头。

## 会被问什么，怎么答

1. **「这不就是那篇 Work2Skill 吗？」**
   借了骨架（episode 形状、工具式证据探索、skill 编写策略），README 的
   *What this builds on* 里写着。但它没跑回放基线、它的 `finalize_extraction`
   不验证正确性、它没有完成闸门，也没有扰动阶梯。三条差别都在
   `docs/results.md` 里有 run 文件。

2. **「N=3，只有一个 app。」**
   对。`docs/technical-report.md` §6 列了七条效度威胁，包括这一条。所以才有
   `reproduce.py`：数字可被陌生人无模型重算，比我多说几句更值钱。

3. **「100/100 是跨模型比的吧？」**
   是，Addendum 12 自己写着。Addendum 14 做了单变量消融：条款不是原因，模型是
   候选（N=1 对 N=3、`image_max_size` 未测）。第二个执行器上同一份 skill 是
   100/100/85。

4. **「verifier 全绿但干错了事，那你这校验有什么用？」**
   那正是我们公开的那条边界（walkthrough 第 4 步）。页面状态能查「最后对不对」，
   查不了「用的是不是给你的值」。这条没被修掉，是被写进文档当作限制。

5. **「页面不变的时候回放就赢了，那要你干嘛？」**
   对，页面不变请直接回放或者写脚本，它免费同分。这个工具只在页面会动、并且你需要
   知道「这次到底干完没有」的时候有意义。

6. **「为什么要装 Python / 要模型？」**
   现在确实要。上线路径写在 `docs/quickstart.md`；一键版是 Codespaces
   （README 顶部按钮）。它不是给普通员工直接用的产品，这一点文档里明说。

7. **「内网能用吗？」**
   今天不能。没有会话持久化（SSO 进不去），而且任务给的凭据会随指令进模型。
   记录里的密码已经脱敏到按键级别，但那是必要条件不是充分条件。

8. **「有 bug / 抄的 / 数据造假？」**
   十个故障、五次公开纠正、隔离运行都留着，`results/_invalid/` 的文件名里写着原因。
   如果复现出不同数字，那是最有用的反馈 —— 请贴 `reproduce.py` 的输出。

## 三条引用句（配图用）

- 「控制组什么都没做，看起来却像 skill 扛住了。」（扰动 no-op 那个故障）
- 「分数说 9 次都好，`finished` 说只有 5 次走到终点。」
- 「回放在演示页 100，页面一改 25 —— 这就是没人跑的基线。」

配图：`docs/assets/ladder.png`（回放塌陷）、`docs/assets/score-vs-finished.png`
（分数与完成分家）。两张图的数据都由测试重算，被人质疑时可以直接让他跑
`python tests/test_artifacts.py`。

## 发布后 48 小时

- 有人复现 → 把他的环境、数字、结论收进 `docs/results.md` 的一条 addendum。**这
  比涨星有用**：一个外部复现是这类工作的第一个真实信号。
- 有人报「我按 quickstart 跑不通」→ 那就是 quickstart 的 bug，当天修。
- 没人理 → 别改标题重发。把「求一次外部复现」写成一条明确的请求（给命令、给预期
  时间、说明不同数字同样有用），单独发一次。
