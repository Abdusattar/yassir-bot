# Фактура бумаги: мягкий шум волокон 1080x1920, серый, среднее ~215, накладывать multiply .05
import numpy as np
from PIL import Image, ImageFilter
rng=np.random.default_rng(1405)
W,H=1080,1920
def blur(a,rx,ry):
    im=Image.fromarray(np.uint8(np.clip(a,0,255)))
    im=im.resize((max(1,W//rx),max(1,H//ry)),Image.BILINEAR) if False else im
    return a
# 1) мелкое зерно
g=rng.normal(0,1,(H,W))
fine=np.array(Image.fromarray(np.uint8(np.clip(128+g*60,0,255))).filter(ImageFilter.GaussianBlur(0.7)),float)-128
# 2) волокна: шум, растянутый по горизонтали (анизотропный blur через ресайз)
f=rng.normal(0,1,(H//2,W//24))
fib=np.array(Image.fromarray(np.uint8(np.clip(128+f*50,0,255))).resize((W,H),Image.BICUBIC),float)-128
# 3) крупные пятна (неравномерность листа)
c=rng.normal(0,1,(H//160,W//160))
cl=np.array(Image.fromarray(np.uint8(np.clip(128+c*50,0,255))).resize((W,H),Image.BICUBIC),float)-128
t=215+fine*0.55+fib*0.45+cl*0.25
t=np.clip(t,0,255)
print('mean',t.mean().round(1),'std',t.std().round(1))
Image.fromarray(np.uint8(t.round()),'L').save(r"D:\aispace\yassir_Bot\media\brand\paper_texture.png",optimize=True)
