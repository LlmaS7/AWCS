> 本页为全部原始记录，含 17 条已修复并重测通过的测试夹具编码错误。有效验收结果见 交付测试报告.md、验收结果.csv 和 adjudications.json。

# AWCS 测试运行汇总

运行目录：20261020_144032_8fe978

逐例记录：2046；状态：{'PASS': 2023, 'INCONCLUSIVE': 6, 'FAIL': 17}

| 阶段 | 状态数量 |
| --- | --- |
| P0 | {'PASS': 10} |
| P1 | {'PASS': 1325} |
| P2 | {'PASS': 12} |
| P2-supplement | {'PASS': 3} |
| P3 | {'PASS': 354} |
| P3-supplement | {'PASS': 120} |
| P4-boundary | {'PASS': 31} |
| P4-dynamic | {'PASS': 3} |
| P4-main | {'PASS': 28} |
| P4-probe | {'PASS': 2} |
| P4-static | {'PASS': 23} |
| P4-static-audit | {'FAIL': 16, 'PASS': 16} |
| P5 | {'PASS': 14} |
| P5-process | {'FAIL': 1, 'PASS': 1} |
| P5-supplement | {'PASS': 2} |
| P6-32 | {'PASS': 8} |
| P6-64 | {'INCONCLUSIVE': 6} |
| P6-coupling | {'PASS': 9} |
| P6-coupling-contract | {'PASS': 3} |
| P6-mode | {'PASS': 2} |
| P6-mode-contract | {'PASS': 1} |
| TRACE-audit | {'PASS': 56} |

## 非通过结果

- EXPERIMENT64-experimental_128x96-20262018：INCONCLUSIVE；T095 已完成 · R64 可接新任务
- EXPERIMENT64-experimental_128x96-20262019：INCONCLUSIVE；T110 已完成 · R59 可接新任务
- EXPERIMENT64-rectangle-20262018：INCONCLUSIVE；已安全暂停：当前预算内未形成完整安全方案（不是无解证明）
- EXPERIMENT64-rectangle-20262019：INCONCLUSIVE；已安全暂停：当前预算内未形成完整安全方案（不是无解证明）
- EXPERIMENT64-rooms-20262018：INCONCLUSIVE；已安全暂停：当前预算内未形成完整安全方案（不是无解证明）
- EXPERIMENT64-rooms-20262019：INCONCLUSIVE；已安全暂停：当前预算内未形成完整安全方案（不是无解证明）
- WORKER-PROCESS：FAIL；UnicodeDecodeError: 'gbk' codec can't decode byte 0xb0 in position 86: illegal multibyte sequence
- G-independent-courtyard_20261018：FAIL；UnicodeDecodeError: 'gbk' codec can't decode byte 0xad in position 61: illegal multibyte sequence
- G-independent-courtyard_20261019：FAIL；UnicodeDecodeError: 'gbk' codec can't decode byte 0xad in position 61: illegal multibyte sequence
- G-independent-l_20261018：FAIL；UnicodeDecodeError: 'gbk' codec can't decode byte 0xa2 in position 63: illegal multibyte sequence
- G-independent-l_20261019：FAIL；UnicodeDecodeError: 'gbk' codec can't decode byte 0xa2 in position 63: illegal multibyte sequence
- G-independent-random_20261018：FAIL；UnicodeDecodeError: 'gbk' codec can't decode byte 0xb0 in position 86: illegal multibyte sequence
- G-independent-random_20261019：FAIL；UnicodeDecodeError: 'gbk' codec can't decode byte 0xb0 in position 86: illegal multibyte sequence
- G-independent-rectangle_20261018：FAIL；UnicodeDecodeError: 'gbk' codec can't decode byte 0xb0 in position 86: illegal multibyte sequence
- G-independent-rectangle_20261019：FAIL；UnicodeDecodeError: 'gbk' codec can't decode byte 0xb0 in position 86: illegal multibyte sequence
- G-independent-rectangle_64：FAIL；UnicodeDecodeError: 'gbk' codec can't decode byte 0x89 in position 99: illegal multibyte sequence
- G-independent-rooms_20261018：FAIL；UnicodeDecodeError: 'gbk' codec can't decode byte 0xb0 in position 86: illegal multibyte sequence
- G-independent-rooms_20261019：FAIL；UnicodeDecodeError: 'gbk' codec can't decode byte 0xb0 in position 86: illegal multibyte sequence
- G-independent-rooms_64：FAIL；UnicodeDecodeError: 'gbk' codec can't decode byte 0x89 in position 99: illegal multibyte sequence
- G-independent-t_20261018：FAIL；UnicodeDecodeError: 'gbk' codec can't decode byte 0xa2 in position 63: illegal multibyte sequence
- G-independent-t_20261019：FAIL；UnicodeDecodeError: 'gbk' codec can't decode byte 0xa2 in position 63: illegal multibyte sequence
- G-independent-u_20261018：FAIL；UnicodeDecodeError: 'gbk' codec can't decode byte 0xa2 in position 63: illegal multibyte sequence
- G-independent-u_20261019：FAIL；UnicodeDecodeError: 'gbk' codec can't decode byte 0xa2 in position 63: illegal multibyte sequence

本汇总仅陈述实际运行结果；完整范围与交付结论见本批次的交付报告。
