# подача пачки: строки с «*» вместо подписи пропускаются с показом слова (их правлю отдельно)
import json,sys,subprocess,os
f=sys.argv[1]; out=[]
for l in open(f,encoding='utf-8').read().splitlines():
    if not l.strip(): continue
    loc,g=[x.strip() for x in l.split('|')][:2]
    s,a,p=loc.split(':'); w=[x for x in json.load(open(f'sources/wbw_ru_refs/{s}_{a}.json',encoding='utf-8'))['words'] if x['pos']==int(p)][0]
    if g=='*' or w['ru_now'].strip()=='*':
        print('STAR',loc,w['ar'],'=',w['ru_now'],'<-',g); continue
    out.append(l)
r=subprocess.run([sys.executable,'scripts/wbw_ru_add.py'],input='\n'.join(out),text=True,encoding='utf-8',capture_output=True)
print(r.stdout,r.stderr[-300:])
