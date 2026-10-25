"""Rebuild ../index.html (Telegram Mini App) from the floor data and template.
Run from the repo root:  python3 src/build.py"""
import os, re, runpy
here=os.path.dirname(os.path.abspath(__file__)); os.chdir(here)
runpy.run_path('gen.py')                      # floors.py -> vec.json, seed.json
t=open('template.html',encoding='utf8').read()
page=t.replace('/*SEED*/null',open('seed.json',encoding='utf8').read()).replace('/*VEC*/null',open('vec.json',encoding='utf8').read())
title=re.search(r'<title>.*?</title>',page).group(0); body=page.replace(title,'',1)
body=body.replace('<meta name="claude:viewport-fit-sides" content="cover">','',1)
fonts=re.search(r'<link rel="stylesheet"[^>]+>',body).group(0); body=body.replace(fonts,'',1)
css='<style>.seg{display:none!important}#floors{padding-bottom:max(8px,env(safe-area-inset-bottom,0px))}#legend{bottom:12px}</style>'
html=('<!doctype html>\n<html lang="ru"><head><meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">\n'
      +title+'\n<meta name="theme-color" content="#0a52ad">\n<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'+fonts+'\n'
      '<script src="https://telegram.org/js/telegram-web-app.js"></script>\n<script>window.ULK_NOSCAN=true</script>\n'
      '<style>html,body{margin:0}[hidden]{display:none!important}img{max-width:100%}</style>\n'+css+'\n</head><body>\n'
      +body+'\n'+open('tg_extra.js',encoding='utf8').read()+'</body></html>\n')
open(os.path.join(here,'..','index.html'),'w',encoding='utf8').write(html)
for f in ('vec.json','seed.json'): os.remove(f)
print('index.html', len(html), 'bytes')
