from pathlib import Path
p=Path('.temp/add_random_map_evidence.py');s=p.read_text(encoding='utf-8');s=s.replace(r'const notes=(.*?);\n',r'const\s+notes\s*=\s*(.*?);\s*\n').replace(r'const notes=.*?;\n',r'const\s+notes\s*=\s*.*?;\s*\n');p.write_text(s,encoding='utf-8')
p=Path('.temp/check_technical_video.py');s=p.read_text(encoding='utf-8');s=s.replace(r'const notes=(.*?);\n',r'const\s+notes\s*=\s*(.*?);\s*\n');p.write_text(s,encoding='utf-8')
