# AWCS 隔离测试工具

仅测试任务分配、路径规划、执行状态与相关保护机制。全部产物在本目录内，禁止覆盖正式地图、个人地图库或 outputs。

## 文件

- checkers.py：独立匹配穷举、时空动态规划、联合 BFS、路线与业务状态检查。
- core.py：匹配对照、预约与 SIPP、业务规则、故障保护。
- run_case.py：在子进程中执行单个集成用例，记录计划和逐步轨迹。
- run_suite.py：生成并冻结用例矩阵，串行调度、设置子进程硬超时、汇总结果。
- supplement.py：参数边界、额外约束、障碍下多作业点对照与实际轨迹审计。
- replay_case.py：用已归档实际地图重现一个集成用例。
- runs/：独立运行批次；results.jsonl 是逐例原始记录，summary.csv/summary.md 是汇总，交付测试报告.md 是解释性结论。

## 执行

在项目根目录使用当前虚拟环境：

```powershell
.\.venv\Scripts\python.exe -B .temp/testing/run_suite.py --stage all
```

也可将 all 换为 core、generated 或 extended，每次默认新建运行批次。运行期间不要修改生产代码；不要并行运行规划性能用例。

主批次结束后，再执行补充测试与完整轨迹审计：

```powershell
.\.venv\Scripts\python.exe -B .temp/testing/supplement.py ".temp/testing/runs/具体批次"
.\.venv\Scripts\python.exe -B .temp/testing/run_suite.py --stage summarize --run-dir ".temp/testing/runs/具体批次"
```

run_suite 会按固定种子生成并保存 manifest，具体输入在每个 cases/<case_id>/input.json；本实现不提供方案示意命令中的 --manifest 参数。单例重放使用 replay_case，保留旧输入与输出。

```powershell
.\.venv\Scripts\python.exe -B .temp/testing/replay_case.py ".temp/testing/runs/具体批次/cases/具体用例/input.json"
```

重现仍受机器速度与规划预算影响，不承诺每次路径逐格相同。主流程代码退出码 0 表示本次选定范围通过，1 表示含失败，2 表示含未完成结果；同时核对逐例状态与报告范围。

本工具不接入大模型，不启动图形界面。实验性能力和保护拒绝行为与正常搬运完成分别计数。