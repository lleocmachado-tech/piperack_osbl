"""Embed the exact requested OFL font families for serverless/offline report delivery."""
import urllib.request,re,base64,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
url='https://fonts.googleapis.com/css2?family=Kodchasan:wght@400;500;600;700&family=Open+Sans:wght@400;600;700&display=swap'
request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 Chrome/120.0.0.0 Safari/537.36'})
css=urllib.request.urlopen(request,timeout=30).read().decode()
faces=[];sources=[]
for block in re.findall(r'@font-face\s*\{[^}]+\}',css):
    links=re.findall(r'url\((https://[^)]+)\)',block)
    if not links:continue
    for link in links:
        content=urllib.request.urlopen(link,timeout=30).read();mime='font/woff2' if 'woff2' in block else 'font/ttf'
        block=block.replace(link,'data:'+mime+';base64,'+base64.b64encode(content).decode())
        sources.append(link)
    faces.append(block)
(ROOT/'backend/fonts.css').write_text('\n'.join(faces),encoding='utf-8')
(ROOT/'reports/evidence/font-sources.json').write_text(json.dumps({'families':['Kodchasan','Open Sans'],'license':'SIL Open Font License 1.1','css_source':url,'font_sources':sources,'delivery':'embedded base64, offline'},indent=2),encoding='utf-8')
for family,path in [('kodchasan','Kodchasan-OFL.txt'),('opensans','OpenSans-OFL.txt')]:
    license_url=f'https://raw.githubusercontent.com/google/fonts/main/ofl/{family}/OFL.txt'
    content=urllib.request.urlopen(license_url,timeout=30).read()
    (ROOT/'reports/evidence'/path).write_bytes(content)
print('Embedded',len(faces),'font faces')
