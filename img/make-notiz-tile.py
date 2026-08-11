#!/usr/bin/env python3
"""Erzeugt img/notiz-tile.webp — die vertikal NAHTLOS kachelbare Ableitung von img/notiz.jpg,
die textarea.note-paper in index.html als Karopapier-Hintergrund nutzt (background-repeat:repeat-y).

Warum: das Originalfoto ist 1297x2780 und war mit background-size:100% auto / no-repeat nach
ca. Feldbreite x 2,1 aufgebraucht — bei langen Notizen brach das Karo in die Feld-Fuellfarbe ab.
Naiv gekachelt zeigt es eine harte Naht (Zeilenhelligkeit oben ~189, unten ~157).

Verfahren: Streifen ueber 21 Rasterzellen a 46px aus dem helligkeitsstabilen oberen Bereich,
vertikale Helligkeitsdrift flachgezogen, dann Kreuzblende mit einer um 11 Zellen (= ganzzahliges
Vielfaches des Rasters, damit die Linien deckungsgleich bleiben) gerollten Kopie.

Nur bei Bedarf neu laufen lassen (Pillow noetig):  python3 img/make-notiz-tile.py
"""
import os
from PIL import Image

HERE=os.path.dirname(os.path.abspath(__file__))
SRC=os.path.join(HERE,'notiz.jpg')
OUT=os.path.join(HERE,'notiz-tile.webp')
PITCH=46

im = Image.open(SRC).convert('RGB')
W,H = im.size
g = im.convert('L')
gp = g.load()

# --- 1. Rasterlinien-Phase im ruhigen oberen Bereich bestimmen -----------------
def rowdark(y):
    return sum(gp[x,y] for x in range(300, 900, 4)) / 150.0

band = [rowdark(y) for y in range(H)]
def rmean(v,k):
    out=[]; half=k//2
    for i in range(len(v)):
        a=max(0,i-half); b=min(len(v),i+half+1)
        out.append(sum(v[a:b])/(b-a))
    return out
sm41 = rmean(band,41)
det = [band[i]-sm41[i] for i in range(H)]

# Phase: welcher Offset 0..45 hat im Bereich 200..1200 die dunkelsten Zeilen?
best=None
for ph in range(PITCH):
    ys=[y for y in range(200,1200) if (y-ph)%PITCH==0]
    s=sum(det[y] for y in ys)/len(ys)
    if best is None or s<best[1]: best=(ph,s)
phase=best[0]
print('phase (Rasterlinie bei y%46==):', phase, 'score', round(best[1],2))

# --- 2. Streifen schneiden: 21 Zellen, auf Rasterlinie ausgerichtet ------------
CELLS=21
y0 = phase
while y0 < 200: y0 += PITCH
TH = CELLS*PITCH
assert y0+TH <= 1300, (y0,TH)
strip = im.crop((0,y0,W,y0+TH))
print('strip', strip.size, 'y0',y0)

# --- 3. vertikalen Helligkeitsverlauf flachziehen ------------------------------
sg = strip.convert('L').load()
prof = [sum(sg[x,y] for x in range(0,W,8))/(W//8) for y in range(TH)]
prof_s = rmean(prof, 201)          # nur die niederfrequente Drift
target = sum(prof_s)/len(prof_s)
px = strip.load()
for y in range(TH):
    f = target/prof_s[y]
    for x in range(W):
        r,gc,b = px[x,y]
        px[x,y] = (min(255,int(r*f+.5)), min(255,int(gc*f+.5)), min(255,int(b*f+.5)))

# --- 4. nahtlos schliessen: Kreuzblende mit um 11 Zellen gerollter Kopie -------
ROLL = 11*PITCH
rolled = Image.new('RGB',(W,TH))
rolled.paste(strip.crop((0,TH-ROLL,W,TH)), (0,0))
rolled.paste(strip.crop((0,0,W,TH-ROLL)), (0,ROLL))
rp = rolled.load()
for y in range(TH):
    w = y/(TH-1)                    # linear 0..1 -> Naht oben/unten verschwindet
    for x in range(W):
        a=px[x,y]; b=rp[x,y]
        px[x,y]=(int(a[0]+(b[0]-a[0])*w), int(a[1]+(b[1]-a[1])*w), int(a[2]+(b[2]-a[2])*w))

# --- 5. skalieren + speichern --------------------------------------------------
OUTW=900
outh = round(TH*OUTW/W)
tile = strip.resize((OUTW,outh), Image.LANCZOS)
tile.save(OUT,'WEBP',quality=82,method=6)
print('tile', tile.size)

# --- 6. Gegenprobe: 3x gestapelt ----------------------------------------------
chk = Image.new('RGB',(OUTW,outh*3))
for i in range(3): chk.paste(tile,(0,i*outh))
chk.resize((360, outh*3*360//OUTW), Image.LANCZOS).save('/tmp/notiz-tilecheck.png')  # Sichtpruefung: keine Naht?
print('check', chk.size)
