#!/usr/bin/env python3
"""
Monitor do Kilauea (Big Island, Havai).

Roda no GitHub Actions a cada 30 minutos:
  1. Consulta a API publica do USGS/HANS (getElevatedVolcanoes).
  2. Compara color_code / alert_level com o estado anterior (state/state.json).
  3. Se o vulcao subiu para ORANGE ou RED -> push URGENTE via ntfy.sh
     (episodio de fonte de lava comecando: "va para o parque agora").
     Rebaixamento ou outras mudancas -> push informativo.
  4. Gera a pagina de status e sobe para o PythonAnywhere em /kilauea/.

Somente stdlib. Variaveis de ambiente:
  NTFY_TOPIC  - topico do ntfy.sh (secreto; quem souber o nome pode ler/postar)
  PA_TOKEN    - token da API do PythonAnywhere (o mesmo de painel/.env)
  PA_USER     - usuario do PythonAnywhere (default: rafaelcortopassi)
"""
import html as html_mod
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

BASE = Path(__file__).parent
STATE_FILE = BASE / "state" / "state.json"
HISTORY_FILE = BASE / "state" / "history.json"

VNUM = "332010"  # Kilauea
ELEVATED_URL = "https://volcanoes.usgs.gov/hans-public/api/volcano/getElevatedVolcanoes"
NOTICE_URL = "https://volcanoes.usgs.gov/hans-public/api/notice/getNotice/{ident}"

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
PA_TOKEN = os.environ.get("PA_TOKEN", "")
PA_USER = os.environ.get("PA_USER", "rafaelcortopassi")
PA_API = "https://www.pythonanywhere.com"

HST = ZoneInfo("Pacific/Honolulu")
BRT = ZoneInfo("America/Sao_Paulo")

# Ordem de severidade dos codigos de cor da aviacao / niveis de alerta
RANK = {"GREEN": 0, "YELLOW": 1, "ORANGE": 2, "RED": 3}
NIVEL_PT = {
    "GREEN": "Normal",
    "YELLOW": "Atividade elevada (em pausa)",
    "ORANGE": "ERUPCAO EM CURSO",
    "RED": "ERUPCAO MAIOR EM CURSO",
}

# Links uteis (aparecem na pagina e no push)
LINK_UPDATES = "https://www.usgs.gov/volcanoes/kilauea/volcano-updates"
LINK_WEBCAMS = "https://www.usgs.gov/volcanoes/kilauea/webcams"
LINK_YOUTUBE = "https://www.youtube.com/@usgs/live"


def fetch_json(url, tries=3, timeout=45):
    last = None
    for i in range(1, tries + 1):
        try:
            req = Request(url, headers={"User-Agent": "kilauea-monitor/1.0"})
            with urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 - qualquer falha de rede conta igual
            last = e
            if i < tries:
                time.sleep(10 * i)
    raise RuntimeError(f"falha ao buscar {url}: {last}")


def kilauea_atual():
    """Estado atual do Kilauea segundo o USGS. Se nao estiver na lista de
    vulcoes elevados, esta GREEN/NORMAL."""
    data = fetch_json(ELEVATED_URL)
    entradas = [d for d in data if str(d.get("vnum")) == VNUM]
    if not entradas:
        return {
            "color_code": "GREEN",
            "alert_level": "NORMAL",
            "notice_identifier": "",
            "sent_utc": "",
            "sent_unixtime": 0,
        }
    e = max(entradas, key=lambda d: int(d.get("sent_unixtime") or 0))
    return {
        "color_code": (e.get("color_code") or "").upper(),
        "alert_level": (e.get("alert_level") or "").upper(),
        "notice_identifier": e.get("notice_identifier") or "",
        "sent_utc": e.get("sent_utc") or "",
        "sent_unixtime": int(e.get("sent_unixtime") or 0),
    }


def detalhe_notice(ident):
    """Sinopse (texto puro) e resumo (HTML) do aviso mais recente."""
    if not ident:
        return "", ""
    try:
        d = fetch_json(NOTICE_URL.format(ident=quote(ident, safe="")))
        secs = d.get("notice_sections") or []
        sec = next((s for s in secs if str(s.get("vnum")) == VNUM), secs[0] if secs else {})
        return (sec.get("synopsis") or "").strip(), (sec.get("summary") or "").strip()
    except Exception as e:  # noqa: BLE001 - detalhe e opcional, nao derruba o monitor
        print(f"aviso: nao consegui o detalhe do notice ({e})")
        return "", ""


TRAD_CACHE = BASE / "state" / "traducao.json"


def _traduz_bloco(texto):
    """Traduz um bloco de texto en->pt pelo endpoint gtx do Google Translate.
    Nao oficial, mas estavel ha anos; em falha, retorna vazio (usamos o original)."""
    url = ("https://translate.googleapis.com/translate_a/single"
           "?client=gtx&sl=en&tl=pt&dt=t&q=" + quote(texto))
    data = fetch_json(url, tries=2, timeout=30)
    return "".join(seg[0] for seg in data[0] if seg and seg[0])


def traduz_aviso(ident, resumo_html, sinopse):
    """Versao em portugues do aviso, como HTML em paragrafos.
    Cacheada por notice_identifier em state/traducao.json."""
    if not (resumo_html or sinopse):
        return ""
    if TRAD_CACHE.exists():
        try:
            cache = json.loads(TRAD_CACHE.read_text(encoding="utf-8"))
            if cache.get("notice") == ident and cache.get("pt_html"):
                return cache["pt_html"]
        except Exception:  # noqa: BLE001 - cache corrompido: retraduz
            pass
    # HTML -> texto em paragrafos
    txt = resumo_html or sinopse
    txt = re.sub(r"(?i)</p\s*>|<br\s*/?>", "\n", txt)
    txt = re.sub(r"<[^>]+>", "", txt)
    txt = html_mod.unescape(txt)
    paragrafos = [p.strip() for p in txt.split("\n") if p.strip()]
    traduzidos = []
    try:
        # blocos de ate ~1500 chars para nao estourar a URL
        bloco, blocos = "", []
        for p in paragrafos:
            if bloco and len(bloco) + len(p) > 1500:
                blocos.append(bloco)
                bloco = p
            else:
                bloco = f"{bloco}\n{p}" if bloco else p
        if bloco:
            blocos.append(bloco)
        for b in blocos:
            traduzidos.append(_traduz_bloco(b))
    except Exception as e:  # noqa: BLE001 - traducao e opcional
        print(f"aviso: traducao falhou ({e}); pagina usa o original")
        return ""
    linhas = [ln.strip() for t in traduzidos for ln in t.split("\n") if ln.strip()]
    pt_html = "".join(f"<p>{html_mod.escape(ln)}</p>" for ln in linhas)
    TRAD_CACHE.write_text(
        json.dumps({"notice": ident, "pt_html": pt_html}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return pt_html


def push_ntfy(titulo, corpo, prioridade="default", tags="", click=""):
    """Manda push pelo ntfy.sh. Headers precisam ser ASCII; o corpo vai em UTF-8."""
    if not NTFY_TOPIC:
        print("aviso: NTFY_TOPIC nao definido; push pulado")
        return
    headers = {
        "Title": titulo.encode("ascii", "replace").decode("ascii"),
        "Priority": prioridade,
    }
    if tags:
        headers["Tags"] = tags
    if click:
        headers["Click"] = click
    req = Request(f"https://ntfy.sh/{NTFY_TOPIC}", data=corpo.encode("utf-8"),
                  method="POST", headers=headers)
    try:
        with urlopen(req, timeout=30) as r:
            print(f"push enviado ({r.getcode()}): {titulo}")
    except Exception as e:  # noqa: BLE001
        print(f"ERRO no push: {e}")


def fmt_hora(dt_utc, lang="pt"):
    if not dt_utc:
        return "-"
    hst = dt_utc.astimezone(HST).strftime("%d/%m %H:%M")
    brt = dt_utc.astimezone(BRT).strftime("%d/%m %H:%M")
    if lang == "en":
        return f"{hst} in Hawaii ({brt} in Brasilia)"
    return f"{hst} no Havai ({brt} em Brasilia)"


def parse_sent(sent_unixtime):
    if not sent_unixtime:
        return None
    return datetime.fromtimestamp(int(sent_unixtime), tz=timezone.utc)


def decide_push(prev, atual, sinopse):
    """Regras de notificacao. Retorna None ou (titulo, corpo, prioridade, tags)."""
    pc, ac = prev.get("color_code", ""), atual["color_code"]
    if pc == ac:
        return None
    quando = parse_sent(atual["sent_unixtime"])
    hora = fmt_hora(quando) if quando else ""
    corpo_base = sinopse or f"Kilauea mudou de {pc or '?'} para {ac}."
    if RANK.get(ac, -1) >= RANK["ORANGE"] and RANK.get(pc, 0) < RANK.get(ac, -1):
        return (
            "KILAUEA EM ERUPCAO - VA AGORA",
            f"Alerta subiu para {ac}/{atual['alert_level']} as {hora}.\n\n"
            f"{corpo_base}\n\nWebcams: {LINK_WEBCAMS}",
            "urgent",
            "volcano,rotating_light",
        )
    if RANK.get(pc, 0) >= RANK["ORANGE"] > RANK.get(ac, 0):
        return (
            "Kilauea: episodio encerrado",
            f"Alerta desceu para {ac}/{atual['alert_level']} as {hora}.\n\n{corpo_base}",
            "default",
            "volcano",
        )
    return (
        f"Kilauea: {pc or '?'} -> {ac}",
        f"Nivel agora e {ac}/{atual['alert_level']} as {hora}.\n\n{corpo_base}",
        "low",
        "volcano",
    )


NIVEL_EN = {
    "GREEN": "Normal",
    "YELLOW": "Elevated activity (paused)",
    "ORANGE": "ERUPTION IN PROGRESS",
    "RED": "MAJOR ERUPTION IN PROGRESS",
}

# Bandeiras pequenas (SVG inline): Havai = ingles, Brasil = portugues
FLAG_HI = """<svg viewBox="0 0 24 16" width="24" height="16">
<rect width="24" height="16" fill="#fff"/>
<rect y="2" width="24" height="2" fill="#c8102e"/><rect y="4" width="24" height="2" fill="#012169"/>
<rect y="8" width="24" height="2" fill="#c8102e"/><rect y="10" width="24" height="2" fill="#012169"/>
<rect y="14" width="24" height="2" fill="#c8102e"/>
<rect width="12" height="8" fill="#012169"/>
<path d="M0 0 12 8 M12 0 0 8" stroke="#fff" stroke-width="1.8"/>
<path d="M0 0 12 8 M12 0 0 8" stroke="#c8102e" stroke-width=".8"/>
<path d="M6 0 V8 M0 4 H12" stroke="#fff" stroke-width="2.6"/>
<path d="M6 0 V8 M0 4 H12" stroke="#c8102e" stroke-width="1.4"/>
</svg>"""
FLAG_BR = """<svg viewBox="0 0 24 16" width="24" height="16">
<rect width="24" height="16" fill="#009c3b"/>
<polygon points="12,1.5 22.5,8 12,14.5 1.5,8" fill="#ffdf00"/>
<circle cx="12" cy="8" r="3.6" fill="#002776"/>
<path d="M8.9 7.1 A5.4 5.4 0 0 1 15.1 8.9" stroke="#fff" stroke-width=".7" fill="none"/>
</svg>"""


def gera_pagina(atual, sinopse, resumo_html, historico, agora_utc, aviso_pt=""):
    cor = atual["color_code"]
    cores = {"GREEN": "#1e7e34", "YELLOW": "#b8860b", "ORANGE": "#d2691e", "RED": "#b22222"}
    fundo = cores.get(cor, "#555")
    quando = parse_sent(atual["sent_unixtime"])
    nivel = atual["alert_level"] or "?"
    linhas_hist = ""
    for h in reversed(historico[-15:]):
        dt = datetime.fromtimestamp(h["quando_unix"], tz=timezone.utc)
        linhas_hist += (
            f"<tr><td>{dt.astimezone(HST).strftime('%d/%m/%Y %H:%M')}</td>"
            f"<td>{html_mod.escape(h['de'] or '?')} &rarr; {html_mod.escape(h['para'])}</td></tr>"
        )
    hist_vazio = not linhas_hist
    if hist_vazio:
        linhas_hist = '<tr><td colspan=2 data-i18n="hist_empty">Nenhuma mudanca registrada ainda</td></tr>'
    aviso_en = resumo_html or f"<p>{html_mod.escape(sinopse)}</p>" if (resumo_html or sinopse) else "<p>-</p>"
    aviso_pt_html = aviso_pt or aviso_en  # sem traducao, cai no original

    live_pt = (f'<a href="{LINK_WEBCAMS}">Webcams do USGS na cratera</a><br>'
               f'<a href="{LINK_YOUTUBE}">Transmissao do USGS no YouTube</a>')
    live_en = (f'<a href="{LINK_WEBCAMS}">USGS crater webcams</a><br>'
               f'<a href="{LINK_YOUTUBE}">USGS live stream on YouTube</a>')
    fonte_pt = f'Fonte: <a href="{LINK_UPDATES}">USGS - Kilauea updates</a>'
    fonte_en = f'Source: <a href="{LINK_UPDATES}">USGS - Kilauea updates</a>'

    i18n = {
        "pt": {
            "title": "Kilauea agora",
            "text": {
                "status": NIVEL_PT.get(cor, cor or "?"),
                "linha_codigo": f"Codigo de aviacao {cor} - nivel {nivel}",
                "linha_aviso": f"Aviso do USGS de {fmt_hora(quando, 'pt') if quando else '-'}",
                "h_aviso": ("Ultimo aviso do HVO (traducao automatica do ingles)"
                            if aviso_pt else "Ultimo aviso do HVO (original em ingles)"),
                "h_live": "Ver ao vivo",
                "h_hist": "Mudancas de nivel registradas por este monitor",
                "hist_empty": "Nenhuma mudanca registrada ainda",
                "hist_nota": "Horarios do historico em hora do Havai (HST)",
                "rodape": (f"Verificado a cada 30 minutos. Ultima checagem: {fmt_hora(agora_utc, 'pt')}. "
                           "Dados: USGS Hawaiian Volcano Observatory (dominio publico). Este site nao e oficial."),
            },
            "html": {"live": live_pt, "fonte": fonte_pt, "aviso": aviso_pt_html},
        },
        "en": {
            "title": "Kilauea now",
            "text": {
                "status": NIVEL_EN.get(cor, cor or "?"),
                "linha_codigo": f"Aviation color code {cor} - alert level {nivel}",
                "linha_aviso": f"USGS notice from {fmt_hora(quando, 'en') if quando else '-'}",
                "h_aviso": "Latest HVO notice",
                "h_live": "Watch live",
                "h_hist": "Alert changes recorded by this monitor",
                "hist_empty": "No changes recorded yet",
                "hist_nota": "History times are Hawaii time (HST)",
                "rodape": (f"Checked every 30 minutes. Last check: {fmt_hora(agora_utc, 'en')}. "
                           "Data: USGS Hawaiian Volcano Observatory (public domain). This site is not official."),
            },
            "html": {"live": live_en, "fonte": fonte_en, "aviso": aviso_en},
        },
    }

    js = """
const I18N = __I18N__;
function setLang(l) {
  try { localStorage.setItem('kilauea_lang', l); } catch (e) {}
  document.documentElement.lang = (l === 'pt') ? 'pt-BR' : 'en';
  document.title = I18N[l].title;
  for (const [k, v] of Object.entries(I18N[l].text)) {
    document.querySelectorAll('[data-i18n="' + k + '"]').forEach(el => { el.textContent = v; });
  }
  for (const [k, v] of Object.entries(I18N[l].html)) {
    document.querySelectorAll('[data-i18n-html="' + k + '"]').forEach(el => { el.innerHTML = v; });
  }
  document.querySelectorAll('.flag').forEach(b => b.classList.toggle('active', b.dataset.lang === l));
}
let lang = 'pt';
try { lang = localStorage.getItem('kilauea_lang') || 'pt'; } catch (e) {}
setLang(lang);
""".replace("__I18N__", json.dumps(i18n, ensure_ascii=False).replace("</", "<\\/"))

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="300">
<title>Kilauea agora</title>
<style>
body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; background: #f4f4f4; color: #222; }}
.banner {{ background: {fundo}; color: #fff; padding: 28px 16px; text-align: center; position: relative; }}
.banner h1 {{ margin: 0 0 6px; font-size: 1.9em; }}
.banner p {{ margin: 4px 0; opacity: .95; }}
.langs {{ position: absolute; top: 8px; right: 10px; }}
.flag {{ background: none; border: 1px solid rgba(255,255,255,.7); border-radius: 3px; padding: 2px 3px;
         margin-left: 6px; cursor: pointer; line-height: 0; opacity: .55; }}
.flag.active {{ opacity: 1; border-color: #fff; }}
.flag svg {{ display: block; }}
.wrap {{ max-width: 760px; margin: 0 auto; padding: 16px; }}
.card {{ background: #fff; border-radius: 10px; padding: 16px 18px; margin: 14px 0; box-shadow: 0 1px 3px rgba(0,0,0,.12); }}
.card h2 {{ margin: 0 0 10px; font-size: 1.05em; color: #444; }}
table {{ border-collapse: collapse; width: 100%; }}
td {{ padding: 6px 8px; border-bottom: 1px solid #eee; font-size: .95em; }}
a {{ color: #0a58ca; }}
.mono {{ font-size: .85em; color: #777; }}
</style>
</head>
<body>
<div class="banner">
<div class="langs">
<button class="flag" data-lang="en" title="English" aria-label="English" onclick="setLang('en')">{FLAG_HI}</button>
<button class="flag active" data-lang="pt" title="Portugues" aria-label="Portugues" onclick="setLang('pt')">{FLAG_BR}</button>
</div>
<h1 data-i18n="status"></h1>
<p data-i18n="linha_codigo"></p>
<p data-i18n="linha_aviso"></p>
</div>
<div class="wrap">
<div class="card"><h2 data-i18n="h_aviso"></h2><div data-i18n-html="aviso"></div>
<p class="mono" data-i18n-html="fonte"></p></div>
<div class="card"><h2 data-i18n="h_live"></h2>
<p data-i18n-html="live"></p></div>
<div class="card"><h2 data-i18n="h_hist"></h2>
<table>{linhas_hist}</table>
<p class="mono" data-i18n="hist_nota"></p></div>
<p class="mono" data-i18n="rodape"></p>
</div>
<script>{js}</script>
</body>
</html>
"""


def upload_pa(conteudo, nome="index.html"):
    if not PA_TOKEN:
        print("aviso: PA_TOKEN nao definido; upload pulado")
        return
    dest = f"/home/{PA_USER}/kilauea/{nome}"
    url = f"{PA_API}/api/v0/user/{PA_USER}/files/path{dest}"
    data = conteudo.encode("utf-8")
    boundary = "----pa" + uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="content"; filename="{nome}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = Request(url, data=body, method="POST", headers={
        "Authorization": f"Token {PA_TOKEN}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    })
    for tent in range(1, 4):
        try:
            with urlopen(req, timeout=90) as r:
                print(f"pagina publicada ({r.getcode()}): {dest}")
                return
        except Exception as e:  # noqa: BLE001
            if tent < 3:
                print(f"upload tentativa {tent} falhou ({e}); repetindo")
                time.sleep(10 * tent)
            else:
                print(f"ERRO: upload para o PythonAnywhere falhou: {e}")


def main():
    agora_utc = datetime.now(timezone.utc)
    atual = kilauea_atual()
    print(f"USGS: {atual['color_code']}/{atual['alert_level']} "
          f"(aviso {atual['notice_identifier'] or '-'})")

    prev = {}
    if STATE_FILE.exists():
        prev = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    historico = []
    if HISTORY_FILE.exists():
        historico = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))

    sinopse, resumo_html = detalhe_notice(atual["notice_identifier"])

    primeira_vez = not prev
    if primeira_vez:
        push_ntfy(
            "Monitor do Kilauea ativado",
            f"Estado atual: {atual['color_code']}/{atual['alert_level']}.\n\n"
            f"{sinopse}"[:800],
            "low", "white_check_mark",
        )
    else:
        decisao = decide_push(prev, atual, sinopse)
        if decisao:
            titulo, corpo, prio, tags = decisao
            push_ntfy(titulo, corpo[:1500], prio, tags, click=LINK_WEBCAMS)
            historico.append({
                "quando_unix": int(agora_utc.timestamp()),
                "de": prev.get("color_code", ""),
                "para": atual["color_code"],
                "notice": atual["notice_identifier"],
            })
            historico = historico[-50:]

    STATE_FILE.write_text(json.dumps(atual, indent=2), encoding="utf-8")
    HISTORY_FILE.write_text(json.dumps(historico, indent=2), encoding="utf-8")

    aviso_pt = traduz_aviso(atual["notice_identifier"], resumo_html, sinopse)
    pagina = gera_pagina(atual, sinopse, resumo_html, historico, agora_utc, aviso_pt)
    upload_pa(pagina)
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
