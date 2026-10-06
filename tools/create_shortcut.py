"""Local launcher icon from the project's COMBIO palette; no network required."""
from pathlib import Path
import re
from PIL import Image, ImageDraw, ImageFont

root=Path(__file__).resolve().parents[1]
palette=dict(re.findall(r'--([\w-]+):\s*(#[0-9A-Fa-f]+)',(root/'backend/combio.css').read_text(encoding='utf-8')))
out=root/'assets';out.mkdir(exist_ok=True)
image=Image.new('RGBA',(256,256),(0,0,0,0));draw=ImageDraw.Draw(image)
draw.rounded_rectangle((8,8,248,248),radius=48,fill=palette['combio'])
try:font=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',164)
except OSError:font=ImageFont.load_default(size=164)
box=draw.textbbox((0,0),'C',font=font)
draw.text(((256-(box[2]-box[0]))/2-box[0],(256-(box[3]-box[1]))/2-box[1]-3),'C',font=font,fill=palette['superficie'])
image.save(out/'combio-app.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print(out/'combio-app.ico')
