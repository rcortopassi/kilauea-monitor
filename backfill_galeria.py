#!/usr/bin/env python3
"""
Backfill da galeria: varre a Photo & Video Chronology do USGS atras dos artigos
de cada episodio do Kilauea (dez/2024 em diante), pegando data e a primeira
foto de cada um. Grava state/galeria.json, que o monitor passa a manter.

Rodar uma vez, localmente:  python3 backfill_galeria.py
"""
import html as html_mod
import json
import re
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

BASE = Path(__file__).parent
SAIDA = BASE / "state" / "galeria.json"
LISTA = "https://www.usgs.gov/volcanoes/kilauea/photo-and-video-chronology?page={n}"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
MAX_PAGINAS = 20  # ~12 entradas/pagina; folga para chegar a dez/2024


def fetch(url):
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def artigo(slug):
    """(episodio, data ISO, src, cap_en) do artigo; episodio=None se nao achar."""
    h = fetch("https://www.usgs.gov" + slug)
    ep = None
    m = re.search(r"[Ee]pisode\s+(\d+)", h)
    if m:
        ep = int(m.group(1))
    dm = (re.search(r'datetime="(\d{4}-\d{2}-\d{2})', h)
          or re.search(r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})', h))
    data = dm.group(1) if dm else ""
    if not data:
        # fallback: data no proprio slug (january-12-2026-...)
        sm = re.search(r"(january|february|march|april|may|june|july|august|"
                       r"september|october|november|december)-(\d{1,2})-(\d{4})", slug)
        if sm:
            meses = ["january", "february", "march", "april", "may", "june", "july",
                     "august", "september", "october", "november", "december"]
            data = f"{sm.group(3)}-{meses.index(sm.group(1)) + 1:02d}-{int(sm.group(2)):02d}"
    im = re.search(r'<img[^>]+src="(https://d9-wret[^"]+?\.(?:jpe?g|png)[^"]*)"[^>]*>', h, re.I)
    src, cap = "", ""
    if im:
        src = im.group(1)
        am = re.search(r'alt="([^"]*)"', im.group(0))
        cap = html_mod.unescape(am.group(1)).strip() if am else ""
    return ep, data, src, cap


def main():
    slugs = []
    for n in range(MAX_PAGINAS):
        try:
            h = fetch(LISTA.format(n=n))
        except Exception as e:  # noqa: BLE001
            print(f"pagina {n} falhou ({e}); parando a listagem")
            break
        novos = re.findall(r'href="(/observatories/hvo/news/photo-video-chronology-[^"]+)"', h)
        novos = [s for s in dict.fromkeys(novos) if "episode" in s]
        slugs.extend(s for s in novos if s not in slugs)
        # ja passou de dez/2024? os slugs carregam o ano
        anos = re.findall(r"-(\d{4})-|-(\d{4})$", " ".join(novos))
        if any("2024" in a for par in anos for a in par if a) and n > 2:
            print(f"pagina {n}: alcancei 2024, parando")
            break
        print(f"pagina {n}: {len(slugs)} slugs acumulados")
        time.sleep(1)

    galeria = {}
    for i, slug in enumerate(slugs, 1):
        try:
            ep, data, src, cap = artigo(slug)
        except Exception as e:  # noqa: BLE001
            print(f"  {slug}: falhou ({e})")
            continue
        if not (ep and src):
            print(f"  {slug}: sem episodio ou sem foto, pulado")
            continue
        # um por episodio: fica o artigo mais antigo (foto do episodio em si,
        # nao de fieldwork posterior); listagem vem do mais novo para o mais velho
        galeria[ep] = {"ep": ep, "data": data, "src": src, "cap_en": cap, "slug": slug}
        print(f"  ep {ep} ({data}): ok  [{i}/{len(slugs)}]")
        time.sleep(1)

    itens = sorted(galeria.values(), key=lambda x: -x["ep"])
    SAIDA.write_text(json.dumps(itens, ensure_ascii=False, indent=2), encoding="utf-8")
    eps = [x["ep"] for x in itens]
    print(f"\ngravado {SAIDA.name}: {len(itens)} episodios "
          f"(de {min(eps)} a {max(eps)})" if itens else "nada gravado")
    faltam = sorted(set(range(1, max(eps) + 1)) - set(eps)) if itens else []
    if faltam:
        print(f"sem artigo proprio na cronologia: episodios {faltam}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
