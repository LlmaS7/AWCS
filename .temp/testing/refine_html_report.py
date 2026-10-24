from pathlib import Path
p=Path('.temp/testing/report_template.html')
s=p.read_text(encoding='utf-8').replace('<title>AWCS · 项目测试报告</title>','<title>AWCS · 项目测试报告</title><link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 40 40%27%3E%3Crect width=%2740%27 height=%2740%27 rx=%278%27 fill=%27%23086d62%27/%3E%3Ctext x=%2720%27 y=%2728%27 text-anchor=%27middle%27 font-size=%2727%27 fill=%27white%27 font-family=%27sans-serif%27%3EA%3C/text%3E%3C/svg%3E">')
s=s.replace("已到原批次停滞时刻之后 · 已完成", "原停滞时刻及之后 · 已完成")
p.write_text(s,encoding='utf-8')
