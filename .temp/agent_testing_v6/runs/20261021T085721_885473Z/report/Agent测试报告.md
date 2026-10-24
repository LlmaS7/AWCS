# AWCS AI Agent 能力测试报告

生成时间：2026-10-21T17:16:38.942063+08:00

**结论：证据尚不完整，不能判定 Agent 能力通过。**

停止原因：`UNEXPECTED_SIDE_EFFECT`。
离线预设模型只验证生产保护和驱动，不计真实模型能力；网络失败不记模型业务失败。

| 层次 | 计划 | 已执行 | 结果 |
| --- | ---: | ---: | --- |
| H 测试系统自检 | 20 | 20 | {"PASS": 20} |
| O 生产保护 | 40 | 40 | {"PASS": 40} |
| 主矩阵 | 180 | 157 | {"PASS": 53, "INCONCLUSIVE": 97, "FAIL": 7, "NOT_RUN": 23} |
| U 独立挑战 | 24 | 0 | {"NOT_RUN": 24} |
| X 搬运闭环 | 6 | 0 | {"NOT_RUN": 6} |

主矩阵有效 PASS/180：53/180；三次稳定通过：0/60。

## 配置、版本与实际调用

项目：`E:\_PROJECTS\AWCS`。源码前后指纹一致：`True`。
Git 提交：`13d87c59de37ea5236e707572382edeebc0de444`；方案 SHA256：`9884593dd10d23eeca2e8c87a4094090ea253ee8e2b501d3538c387dbf8ed74d`。
配置只保留非敏感字段，密钥不保存于产物；未调用其他模型、未调整生产 effort、提示词、输出上限或重试策略。

本批为版本化证据继承：保留父批次41个有效首轮样本（包括C01和F01失败），其余案例由本版本继续执行；不声称全部由新驱动重测。
父批次D09为测试无效，原记录保留，修正输入的新D09须另测；129次历史API预留继承，总调用额度不重置。新版本4小时执行窗单独记录。
父批次：`E:\_PROJECTS\SDITADC\.temp\agent_testing\runs\20261021T081305_800091Z`；本批继承41段，本批实际新增执行116段。

```json
{
  "base_url": "https://api.deepseek.com",
  "model": "deepseek-flash",
  "effort": "high",
  "remember": false
}
```

API 预留 425 次，尝试发送 425 次，完整流 424 次，可得 usage 424 次。
无可靠价格或 usage 时不估算金额；尝试连接失败不等于已产生账单。

## 阻塞、失败与测试缺陷


只读协议预检：`PASS`。
```json
{
  "stage": "protocol",
  "passed": true,
  "scope": "read-only production adapter and tool roundtrip",
  "events": [
    {
      "id": 1,
      "kind": "start",
      "request_id": "59f2781a46884da4bb62db7fa483611b",
      "job": "test",
      "generation": 0,
      "text": "",
      "task_id": null
    },
    {
      "id": 2,
      "kind": "notice",
      "request_id": "59f2781a46884da4bb62db7fa483611b",
      "message": "连接与只读工具往返测试通过"
    },
    {
      "id": 3,
      "kind": "done",
      "request_id": "59f2781a46884da4bb62db7fa483611b"
    }
  ],
  "calls": 2,
  "tasks": 0,
  "network_errors": [],
  "evidence_origin": "E:\\_PROJECTS\\SDITADC\\.temp\\agent_testing\\runs\\20261021T081305_800091Z\\protocol\\result.json",
  "inherited": true
}
```
- C01/repeat_1：FAIL；`E:\_PROJECTS\SDITADC\.temp\agent_testing\runs\20261021T081305_800091Z\cases\C01\repeat_1`。
- D07/repeat_3：FAIL；`E:\_PROJECTS\AWCS\.temp\agent_testing_v6\runs\20261021T085721_885473Z\cases\D07\repeat_3`。
- F01/repeat_1：FAIL；`E:\_PROJECTS\SDITADC\.temp\agent_testing\runs\20261021T081305_800091Z\cases\F01\repeat_1`。
- F01/repeat_2：FAIL；`E:\_PROJECTS\AWCS\.temp\agent_testing_v6\runs\20261021T085721_885473Z\cases\F01\repeat_2`。
- F02/repeat_1：FAIL；`E:\_PROJECTS\AWCS\.temp\agent_testing_v6\runs\20261021T085721_885473Z\cases\F02\repeat_1`。
- F03/repeat_1：FAIL；`E:\_PROJECTS\AWCS\.temp\agent_testing_v6\runs\20261021T085721_885473Z\cases\F03\repeat_1`。
- F03/repeat_2：FAIL；`E:\_PROJECTS\AWCS\.temp\agent_testing_v6\runs\20261021T085721_885473Z\cases\F03\repeat_2`。

## 地图与范围

| 地图 | 轮廓 | 四号货架实际映射 | 来源 |
| --- | --- | --- | --- |
| M01 | rectangle | P03 | 历史地图网格副本，重新登记业务名称 |
| M02 | rooms | P01 | 历史地图网格副本，重新登记业务名称 |
| M03 | l | P05 | 历史地图网格副本，重新登记业务名称 |

没有进行浏览器/桌面 UI 验收、长期稳定性或算法规模复测。未执行的矩阵、挑战、闭环和必要语义审阅均不能推定通过。

## 复核与复现

运行入口：`E:\_PROJECTS\AWCS\.temp\agent_testing_v6\run_local.ps1`。本批证据：`E:\_PROJECTS\AWCS\.temp\agent_testing_v6\runs\20261021T085721_885473Z`。
本地执行后查看 `report/Agent测试报告.md` 和 `summary.json`，再依据逐例证据完成 `review/packet.json` 中的主张复核。
评审标明 execution AI / human，保留原始首次结果，禁止被测模型自评分或拼接最好成绩。
