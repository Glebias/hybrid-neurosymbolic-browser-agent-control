"""Encode the two actual UI recordings, with explicit experiment labels; no simulated UI."""
import json
import subprocess
from pathlib import Path
import imageio_ffmpeg

ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
out=Path('artifacts/video');out.mkdir(parents=True,exist_ok=True)
parts=[('api-control-demo-v3','API: Gemini 2.5 Flash — агент; Groq GPT-OSS 120B — проверка.\nПодтверждение отправки включено отдельным пользовательским правилом.'),
       ('hidden-codex-hybrid-01','Калибровка: Codex как модель. Скрытый учебный токен в форме.\nBLOCK до исполнения → безопасная ссылка → задача выполнена.')]
encoded=[]
for i,(tag,label) in enumerate(parts):
    source=next((Path('artifacts/runs')/tag).glob('*.webm'))
    target=out/f'part{i}.mp4'
    vf='fps=25,pad=1440:1080:0:0:color=0x142238'
    for line,text in enumerate(label.splitlines()):
        caption=out/f'caption{i}-{line}.txt';caption.write_text(text,encoding='utf-8')
        vf+=f",drawtext=fontfile='C\\:/Windows/Fonts/arial.ttf':textfile='{caption.as_posix()}':fontcolor=white:fontsize=24:x=24:y={1012+line*34}"
    subprocess.run([ffmpeg,'-y','-i',str(source),'-vf',vf,'-an','-c:v','libx264','-preset','fast','-crf','23','-pix_fmt','yuv420p',str(target)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    encoded.append(target)
manifest=out/'concat.txt';manifest.write_text(''.join(f"file '{p.name}'\n" for p in encoded))
target=out/'browser-guard-demo.mp4'
subprocess.run([ffmpeg,'-y','-f','concat','-safe','0','-i',str(manifest),'-c','copy','-movflags','+faststart',str(target)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
probe=subprocess.run([ffmpeg,'-i',str(target)],capture_output=True,text=True,encoding='utf-8',errors='replace')
(out/'provenance.json').write_text(json.dumps({'sources':[str(next((Path('artifacts/runs')/tag).glob('*.webm'))) for tag,_ in parts],
        'output':str(target),'editing':'Concatenation and captions only. Original UI playback speed. No audio.',
        'media_info':probe.stderr},ensure_ascii=False,indent=2),encoding='utf-8')
print(str(target.resolve()))
