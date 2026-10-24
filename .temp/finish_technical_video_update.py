from pathlib import Path
p=Path('.temp/build_technical_video.py');s=p.read_text(encoding='utf-8')
s=s.replace('任务真实变为 cancelled。<br>对象、阶段合法，但取消目标未明确。','T001 实际变为 cancelled（误取消）。')
s=s.replace('明确 T 编号优先；无编号时取本轮界面关联对象。','本轮明确编号优先；无编号时采用界面关联。').replace('查询结果、旧对话和摘要不新增可取消对象。','查询、旧对话、摘要不新增可取消对象。').replace('只要含未指定目标，整批不执行；要求补充明确指令。','含未指定目标 → 整批拒绝，要求补充编号。')
s=s.replace('.d07-case-grid .panel{padding:22px 24px}', '.d07-case-grid .panel{padding:20px 22px}').replace('.d07-case-grid h2{font-size:25px;line-height:1.45;margin:12px 0 17px}', '.d07-case-grid h2{font-size:24px;line-height:1.4;margin:10px 0 12px}').replace('.case-problem blockquote{margin:18px 0;padding:15px 16px;', '.case-problem blockquote{margin:12px 0;padding:12px 14px;').replace('background:#f4b6810a;font-size:24px}', 'background:#f4b6810a;font-size:22px;line-height:1.4}').replace('.case-chain{font-size:18px;', '.case-chain{font-size:17px;').replace('.case-detail{font-size:18px;margin-top:18px;', '.case-detail{font-size:17px;margin-top:14px;').replace('.case-verdict{font-size:19px;color:var(--teal);margin-top:21px;padding-top:16px;', '.case-verdict{font-size:18px;line-height:1.5;color:var(--teal);margin-top:14px;padding-top:12px;').replace('.fix-list li{padding-left:5px;margin-bottom:15px;', '.fix-list li{padding-left:5px;margin-bottom:13px;')
p.write_text(s,encoding='utf-8')
exec(compile(s,str(p),'exec'),{'__file__':str(p.resolve()),'__name__':'__main__'})
folder=Path('.report/演示视频_20261022')
page=(folder/'04_关键技术与测试_录屏讲解.html').read_text(encoding='utf-8')
import re,json
six=re.search(r'<section class="slide" id="slide6".*?</section>',page,re.S)[0]
assert '16 台有限动态流' not in six and '1 / 3' not in six and '其余 3 例' in six
seven=re.search(r'<section class="slide" id="slide7".*?</section>',page,re.S)[0]
assert all(x in seven for x in ['清空会话','未关联任务','T001','实际取消','整批拒绝','3 / 3','guard_rejections = 0'])
assert ':fullscreen #toolbar,.fullscreen-view #toolbar{display:none!important}' in page
assert "document.addEventListener('fullscreenchange',syncFullscreen)" in page
notes=json.loads(re.search(r'const notes=(.*?);\n',page,re.S)[1])
assert sum(n[1] for n in notes)==240
md=folder/'05_关键技术与测试_配套讲稿.md'
with md.open('a',encoding='utf-8') as f:f.write('\n## 制作检查记录\n\n已核对源码与证据数字、7 页结构、240 秒预算、本地链接、页内外讲稿一致性，脚本语法检查通过。全屏隐藏覆盖页面全屏及 F11 浏览器全屏检测；当前环境尚未完成浏览器实际显示与全屏行为验收，正式录制前请试读一次。\n')
print('Requested content and fullscreen rules verified. Page durations:',[n[1] for n in notes])
