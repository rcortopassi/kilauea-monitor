#!/usr/bin/env python3
"""
Monitor do Kilauea (Big Island, Havai).

Roda no GitHub Actions a cada 30 minutos:
  1. Consulta a API publica do USGS/HANS (getElevatedVolcanoes).
  2. Compara color_code / alert_level com o estado anterior (state/state.json).
  3. Se o vulcao subiu para ORANGE ou RED -> push URGENTE via ntfy.sh
     (episodio de fonte de lava comecando: "va para o parque agora").
     Rebaixamento ou outras mudancas -> push informativo.
  4. Busca as fotos oficiais mais recentes do episodio (USGS, dominio publico)
     e verifica quais livestreams do YouTube estao no ar.
  5. Gera a pagina de status (abas Status / Ao vivo / Fotos, PT/EN)
     e sobe para o PythonAnywhere em /kilauea/.

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
TRAD_CACHE = BASE / "state" / "traducao.json"
MIDIA_CACHE = BASE / "state" / "midia.json"

VNUM = "332010"  # Kilauea
ELEVATED_URL = "https://volcanoes.usgs.gov/hans-public/api/volcano/getElevatedVolcanoes"
NOTICE_URL = "https://volcanoes.usgs.gov/hans-public/api/notice/getNotice/{ident}"
CHRONO_URL = "https://www.usgs.gov/volcanoes/kilauea/photo-and-video-chronology"

# Lives conhecidas de monitoramento continuo do Kilauea (a ordem importa)
LIVES_FIXAS = ["gXKuUyKt8mc", "c1EH9TQ2XR0", "iws3rh5vLAQ"]
BUSCA_LIVES = ("https://www.youtube.com/results"
               "?search_query=kilauea+volcano+live+eruption&sp=EgJAAQ%3D%3D")

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
PA_TOKEN = os.environ.get("PA_TOKEN", "")
PA_USER = os.environ.get("PA_USER", "rafaelcortopassi")
PA_API = "https://www.pythonanywhere.com"

HST = ZoneInfo("Pacific/Honolulu")
BRT = ZoneInfo("America/Sao_Paulo")

UA_NAV = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# Ordem de severidade dos codigos de cor da aviacao / niveis de alerta
RANK = {"GREEN": 0, "YELLOW": 1, "ORANGE": 2, "RED": 3}
NIVEL_PT = {
    "GREEN": "Normal",
    "YELLOW": "Atividade elevada (em pausa)",
    "ORANGE": "ERUPCAO EM CURSO",
    "RED": "ERUPCAO MAIOR EM CURSO",
}
NIVEL_EN = {
    "GREEN": "Normal",
    "YELLOW": "Elevated activity (paused)",
    "ORANGE": "ERUPTION IN PROGRESS",
    "RED": "MAJOR ERUPTION IN PROGRESS",
}

# Links uteis
LINK_UPDATES = "https://www.usgs.gov/volcanoes/kilauea/volcano-updates"
LINK_WEBCAMS = "https://www.usgs.gov/volcanoes/kilauea/webcams"
LINK_YOUTUBE = "https://www.youtube.com/@usgs/live"
LINK_PARQUE = "https://www.nps.gov/havo/planyourvisit/conditions.htm"

# Inicio da sequencia eruptiva episodica atual no Halemaumau
INICIO_ERUPCAO = datetime(2024, 12, 23, tzinfo=timezone.utc)

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


def fetch_text(url, tries=2, timeout=45, ua=None):
    """Baixa HTML. www.usgs.gov e YouTube exigem User-Agent de navegador."""
    last = None
    for i in range(1, tries + 1):
        try:
            req = Request(url, headers={
                "User-Agent": ua or "kilauea-monitor/1.0",
                "Accept-Language": "en-US,en;q=0.8",
            })
            with urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            if i < tries:
                time.sleep(5 * i)
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


# ---------------------------------------------------------------- traducao

def _traduz_bloco(texto):
    """Traduz um bloco de texto en->pt pelo endpoint gtx do Google Translate.
    Nao oficial, mas estavel ha anos; em falha, quem chama decide o fallback."""
    url = ("https://translate.googleapis.com/translate_a/single"
           "?client=gtx&sl=en&tl=pt&dt=t&q=" + quote(texto))
    data = fetch_json(url, tries=2, timeout=30)
    return "".join(seg[0] for seg in data[0] if seg and seg[0])


def _linkifica(texto_escapado):
    """Torna URLs clicaveis (o texto ja veio escapado por html.escape)."""
    return re.sub(r"(https?://[^\s<]+[^\s<.,;)\]])",
                  r'<a href="\1">\1</a>', texto_escapado)


def traduz_aviso(ident, resumo_html, sinopse):
    """Versao em portugues do aviso, paragrafo a paragrafo, preservando
    negrito dos titulos de secao e links clicaveis.
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
    origem = resumo_html or f"<p>{html_mod.escape(sinopse)}</p>"
    unidades = re.split(r"(?i)</p\s*>|<br\s*/?>", origem)
    partes = []
    try:
        for u in unidades:
            tem_negrito = re.search(r"(?i)<(strong|b)\b", u) is not None
            texto = html_mod.unescape(re.sub(r"<[^>]+>", "", u)).strip()
            if not texto or texto == "\xa0":
                continue
            trad = _traduz_bloco(texto)
            esc = _linkifica(html_mod.escape(trad))
            if tem_negrito:
                # os <strong> do HVO sao titulos de secao ("Overview:", "NOTE:"):
                # mantem o negrito ate o primeiro dois-pontos
                pos = esc.find(":")
                if 0 < pos < 80:
                    esc = f"<strong>{esc[:pos + 1]}</strong>{esc[pos + 1:]}"
                elif len(esc) < 90:
                    esc = f"<strong>{esc}</strong>"
            partes.append(f"<p>{esc}</p>")
    except Exception as e:  # noqa: BLE001 - traducao e opcional
        print(f"aviso: traducao falhou ({e}); pagina usa o original")
        return ""
    pt_html = "".join(partes)
    TRAD_CACHE.write_text(
        json.dumps({"notice": ident, "pt_html": pt_html}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return pt_html


def frases_chave(sinopse):
    """Extrai do aviso do HVO a frase do ultimo/atual episodio e a de previsao."""
    # "2:36 a.m." viraria fim de frase; normaliza para "2:36 am" antes de extrair
    s = re.sub(r"\b([apAP])\.[mM]\.", r"\1m", sinopse or "")
    ep = re.search(r"(Episode\s+\d+\s+(?:began|ended|started)[^.]*\.)", s)
    prev = re.search(r"([^.]*(?:another episode|next episode|forecast|precursory)[^.]*\.)", s)
    return (ep.group(1).strip() if ep else "",
            prev.group(1).strip() if prev else "")


# ---------------------------------------------------------------- midia

def _status_video(vid):
    """Titulo, canal e flags live/embed de um video do YouTube."""
    try:
        h = fetch_text(f"https://www.youtube.com/watch?v={vid}", ua=UA_NAV)
    except Exception as e:  # noqa: BLE001
        print(f"aviso: youtube {vid} inacessivel ({e})")
        return None
    t = (re.search(r'"title":\{"runs":\[\{"text":"(.*?)"\}', h)
         or re.search(r"<title>(.*?)\s*-\s*YouTube</title>", h))
    c = re.search(r'"ownerChannelName":"(.*?)"', h)
    return {
        "id": vid,
        "titulo": html_mod.unescape(t.group(1))[:90] if t else vid,
        "canal": html_mod.unescape(c.group(1))[:50] if c else "",
        "live": '"isLiveNow":true' in h,
        "embed": '"playableInEmbed":true' in h,
    }


def _busca_lives_extra(excluir, max_ids=6):
    """IDs de outras lives do Kilauea pela busca do YouTube (filtro 'ao vivo')."""
    try:
        h = fetch_text(BUSCA_LIVES, ua=UA_NAV)
    except Exception as e:  # noqa: BLE001
        print(f"aviso: busca de lives falhou ({e})")
        return []
    ids = []
    for vid in re.findall(r'"videoId":"([\w-]{11})"', h):
        if vid not in excluir and vid not in ids:
            ids.append(vid)
        if len(ids) >= max_ids:
            break
    return ids


def lives_atuais(cache):
    """Ate 3 lives no ar e com embed liberado; se as fixas nao bastarem,
    procura substitutas na busca do YouTube. Lives no ar sem embed viram links."""
    infos = [s for s in (_status_video(v) for v in LIVES_FIXAS) if s]
    vivas = [s for s in infos if s["live"] and s["embed"]]
    so_link = [s for s in infos if s["live"] and not s["embed"]]
    if len(vivas) < 2:
        ja = {s["id"] for s in infos}
        for vid in _busca_lives_extra(ja):
            st = _status_video(vid)
            if st and st["live"] and st["embed"]:
                vivas.append(st)
            if len(vivas) >= 3:
                break
    if not vivas and cache.get("lives"):
        print("aviso: nenhuma live confirmada agora; usando a lista anterior")
        return cache["lives"], cache.get("lives_link", [])
    return vivas[:3], so_link[:2]


def fotos_episodio(cache):
    """Fotos oficiais do episodio mais recente na cronologia do USGS
    (dominio publico), com legendas traduzidas. Cache por artigo."""
    antigo = cache.get("fotos") or {}
    try:
        h = fetch_text(CHRONO_URL, ua=UA_NAV)
        m = re.search(r'href="(/observatories/hvo/news/photo-video-chronology-[^"]+)"', h)
        if not m:
            raise RuntimeError("nenhuma entrada na cronologia")
        slug = m.group(1)
        if antigo.get("slug") == slug and antigo.get("itens"):
            return antigo
        art = fetch_text("https://www.usgs.gov" + slug, ua=UA_NAV)
        tm = re.search(r"<title>(.*?)\s*\|", art)
        titulo = html_mod.unescape(tm.group(1)).strip() if tm else "Photo & Video Chronology"
        itens, vistos = [], set()
        for im in re.finditer(r'<img[^>]+src="(https://d9-wret[^"]+?\.(?:jpe?g|png)[^"]*)"[^>]*>',
                              art, re.I):
            src = im.group(1)
            nome = src.rsplit("/", 1)[-1].split("?")[0]
            if nome in vistos:
                continue
            vistos.add(nome)
            alt = re.search(r'alt="([^"]*)"', im.group(0))
            itens.append({
                "src": src,
                "cap_en": html_mod.unescape(alt.group(1)).strip() if alt else "",
                "cap_pt": "",
            })
            if len(itens) >= 6:
                break
        for it in itens:
            if it["cap_en"]:
                try:
                    it["cap_pt"] = _traduz_bloco(it["cap_en"])
                except Exception:  # noqa: BLE001
                    it["cap_pt"] = ""
        return {"slug": slug, "titulo": titulo,
                "url": "https://www.usgs.gov" + slug, "itens": itens}
    except Exception as e:  # noqa: BLE001 - fotos sao opcionais
        print(f"aviso: fotos indisponiveis ({e})")
        return antigo


# ---------------------------------------------------------------- push

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


# ---------------------------------------------------------------- pagina

def gera_pagina(atual, sinopse, resumo_html, historico, agora_utc,
                aviso_pt="", lives=None, lives_link=None, fotos=None, frases=None):
    lives = lives or []
    lives_link = lives_link or []
    fotos = fotos or {}
    frases = frases or {}
    cor = atual["color_code"]
    cores = {"GREEN": "#1e7e34", "YELLOW": "#b8860b", "ORANGE": "#d2691e", "RED": "#b22222"}
    escuras = {"GREEN": "#12481d", "YELLOW": "#7c5a06", "ORANGE": "#8c3d0e", "RED": "#6e1414"}
    fundo = cores.get(cor, "#555")
    sombra = escuras.get(cor, "#333")
    quando = parse_sent(atual["sent_unixtime"])
    nivel = atual["alert_level"] or "?"

    linhas_hist = ""
    for h in reversed(historico[-15:]):
        dt = datetime.fromtimestamp(h["quando_unix"], tz=timezone.utc)
        linhas_hist += (
            f"<tr><td>{dt.astimezone(HST).strftime('%d/%m/%Y %H:%M')}</td>"
            f"<td>{html_mod.escape(h['de'] or '?')} &rarr; {html_mod.escape(h['para'])}</td></tr>"
        )
    if not linhas_hist:
        linhas_hist = '<tr><td colspan=2 data-i18n="hist_empty">Nenhuma mudanca registrada ainda</td></tr>'

    aviso_en = resumo_html or f"<p>{html_mod.escape(sinopse)}</p>" if (resumo_html or sinopse) else "<p>-</p>"
    aviso_pt_html = aviso_pt or aviso_en  # sem traducao, cai no original

    # --- aba Ao vivo (players fora do i18n para nao recarregar ao trocar idioma)
    lives_html = ""
    for s in lives:
        rot = html_mod.escape(f"{s['titulo']} ({s['canal']})" if s["canal"] else s["titulo"])
        lives_html += (
            f'<p class="mono">{rot}</p>'
            f'<div class="video"><iframe data-src="https://www.youtube-nocookie.com/embed/{s["id"]}" '
            f'title="{rot}" allowfullscreen loading="lazy"></iframe></div>'
        )
    if not lives_html:
        lives_html = '<p data-i18n="live_vazio">Nenhuma transmissao confirmada agora.</p>'
    extras = ""
    for s in lives_link:
        rot = html_mod.escape(f"{s['titulo']} ({s['canal']})" if s["canal"] else s["titulo"])
        extras += (f'<a href="https://www.youtube.com/watch?v={s["id"]}">{rot}</a><br>')

    # --- aba Fotos
    fotos_html, caps = "", {}
    for i, it in enumerate((fotos.get("itens") or [])[:6]):
        caps[f"cap_{i}"] = {"pt": it.get("cap_pt") or it.get("cap_en") or "",
                            "en": it.get("cap_en") or ""}
        fotos_html += (
            f'<figure><img src="{html_mod.escape(it["src"], quote=True)}" loading="lazy" '
            f'alt="{html_mod.escape(it.get("cap_en") or "", quote=True)}">'
            f'<figcaption class="mono" data-i18n="cap_{i}"></figcaption></figure>'
        )
    if not fotos_html:
        fotos_html = '<p data-i18n="fotos_vazio">Sem fotos disponiveis no momento.</p>'
    fotos_link = ""
    if fotos.get("url"):
        fotos_link = (f'<p><a href="{html_mod.escape(fotos["url"], quote=True)}">'
                      f'{html_mod.escape(fotos.get("titulo") or "USGS")}</a></p>')

    # --- painel-resumo (acima do texto do aviso)
    em_erupcao = RANK.get(cor, 0) >= RANK["ORANGE"]
    dias = max(0, (agora_utc - INICIO_ERUPCAO).days)
    meses = dias // 30
    if em_erupcao:
        f1_pt = '<span class="dot dot-live"></span>Sim, fontes de lava ativas agora'
        f1_en = '<span class="dot dot-live"></span>Yes, lava fountains active right now'
        f3_pt = "Sim. Va agora: as fontes sao visiveis dos mirantes do parque"
        f3_en = "Yes. Go now: the fountains are visible from the park overlooks"
    elif cor == "YELLOW":
        f1_pt = '<span class="dot dot-pause"></span>Em pausa, sem lava visivel no momento'
        f1_en = '<span class="dot dot-pause"></span>Paused, no lava visible right now'
        f3_pt = "Sim, o parque recebe visitantes normalmente; so nao ha fontes de lava agora"
        f3_en = "Yes, the park is receiving visitors as usual; just no lava fountains right now"
    else:
        f1_pt = '<span class="dot dot-off"></span>Nao, sem erupcao'
        f1_en = '<span class="dot dot-off"></span>No, not erupting'
        f3_pt = "Sim, o parque recebe visitantes normalmente"
        f3_en = "Yes, the park is receiving visitors as usual"
    f2_pt = f'Aberto 24 h, todos os dias <a href="{LINK_PARQUE}">(condicoes atuais)</a>'
    f2_en = f'Open 24/7, every day <a href="{LINK_PARQUE}">(current conditions)</a>'
    f4_pt = f"Sequencia de episodios desde 23/12/2024, ha {meses} meses"
    f4_en = f"Episodic sequence since Dec 23, 2024, {meses} months and counting"
    f5_pt = html_mod.escape(frases.get("ep_pt") or "Sem dados no aviso atual")
    f5_en = html_mod.escape(frases.get("ep_en") or "No data in the current notice")
    f6_pt = html_mod.escape(frases.get("prev_pt") or "Sem previsao divulgada no aviso atual")
    f6_en = html_mod.escape(frases.get("prev_en") or "No forecast in the current notice")

    live_pt = (f'<a href="{LINK_WEBCAMS}">Webcams do USGS na cratera</a><br>'
               f'<a href="{LINK_YOUTUBE}">Canal oficial do USGS no YouTube</a><br>' + extras)
    live_en = (f'<a href="{LINK_WEBCAMS}">USGS crater webcams</a><br>'
               f'<a href="{LINK_YOUTUBE}">Official USGS YouTube channel</a><br>' + extras)
    fonte_pt = f'Fonte: <a href="{LINK_UPDATES}">USGS - Kilauea updates</a>'
    fonte_en = f'Source: <a href="{LINK_UPDATES}">USGS - Kilauea updates</a>'

    i18n = {
        "pt": {
            "title": "Kilauea agora",
            "text": {
                "status": NIVEL_PT.get(cor, cor or "?"),
                "linha_codigo": f"Codigo de aviacao {cor} - nivel {nivel}",
                "linha_aviso": f"Aviso do USGS de {fmt_hora(quando, 'pt') if quando else '-'}",
                "tab_status": "Status",
                "tab_live": "Ao vivo",
                "tab_fotos": "Fotos",
                "h_aviso": ("Ultimo aviso do HVO (traducao automatica do ingles)"
                            if aviso_pt else "Ultimo aviso do HVO (original em ingles)"),
                "h_live": "Transmissoes ao vivo",
                "live_nota": ("Players verificados a cada 30 minutos. Se um deles parar, "
                              "a proxima verificacao busca outra transmissao no ar."),
                "live_vazio": "Nenhuma transmissao confirmada agora.",
                "h_maislinks": "Mais links",
                "h_fotos": "Fotos do episodio (USGS)",
                "fotos_credito": "Fotos: USGS / Hawaiian Volcano Observatory, dominio publico.",
                "fotos_vazio": "Sem fotos disponiveis no momento.",
                "h_hist": "Mudancas de nivel registradas por este monitor",
                "hist_empty": "Nenhuma mudanca registrada ainda",
                "hist_nota": "Horarios do historico em hora do Havai (HST)",
                "fl1": "Em erupcao agora?",
                "fl2": "Parque nacional",
                "fl3": "Da para visitar?",
                "fl4": "Erupcao atual",
                "fl5": "Ultimo episodio",
                "fl6": "Proximo episodio (previsao do HVO)",
                "rodape": (f"Verificado a cada 30 minutos. Ultima checagem: {fmt_hora(agora_utc, 'pt')}. "
                           "Dados: USGS Hawaiian Volcano Observatory (dominio publico). Este site nao e oficial."),
            },
            "html": {"live": live_pt, "fonte": fonte_pt, "aviso": aviso_pt_html,
                     "fv1": f1_pt, "fv2": f2_pt, "fv3": f3_pt,
                     "fv4": f4_pt, "fv5": f5_pt, "fv6": f6_pt},
        },
        "en": {
            "title": "Kilauea now",
            "text": {
                "status": NIVEL_EN.get(cor, cor or "?"),
                "linha_codigo": f"Aviation color code {cor} - alert level {nivel}",
                "linha_aviso": f"USGS notice from {fmt_hora(quando, 'en') if quando else '-'}",
                "tab_status": "Status",
                "tab_live": "Live",
                "tab_fotos": "Photos",
                "h_aviso": "Latest HVO notice",
                "h_live": "Live streams",
                "live_nota": ("Players are checked every 30 minutes. If one goes offline, "
                              "the next check looks for another stream on air."),
                "live_vazio": "No stream confirmed right now.",
                "h_maislinks": "More links",
                "h_fotos": "Episode photos (USGS)",
                "fotos_credito": "Photos: USGS / Hawaiian Volcano Observatory, public domain.",
                "fotos_vazio": "No photos available right now.",
                "h_hist": "Alert changes recorded by this monitor",
                "hist_empty": "No changes recorded yet",
                "hist_nota": "History times are Hawaii time (HST)",
                "fl1": "Erupting right now?",
                "fl2": "National park",
                "fl3": "Can I visit?",
                "fl4": "Current eruption",
                "fl5": "Latest episode",
                "fl6": "Next episode (HVO forecast)",
                "rodape": (f"Checked every 30 minutes. Last check: {fmt_hora(agora_utc, 'en')}. "
                           "Data: USGS Hawaiian Volcano Observatory (public domain). This site is not official."),
            },
            "html": {"live": live_en, "fonte": fonte_en, "aviso": aviso_en,
                     "fv1": f1_en, "fv2": f2_en, "fv3": f3_en,
                     "fv4": f4_en, "fv5": f5_en, "fv6": f6_en},
        },
    }
    for k, v in caps.items():
        i18n["pt"]["text"][k] = v["pt"]
        i18n["en"]["text"][k] = v["en"]

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
function setTab(t) {
  document.querySelectorAll('.pane').forEach(d => d.classList.toggle('on', d.dataset.pane === t));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('on', b.dataset.tab === t));
  if (t === 'live') {
    document.querySelectorAll('iframe[data-src]').forEach(f => {
      f.src = f.dataset.src; f.removeAttribute('data-src');
    });
  }
  try { sessionStorage.setItem('kilauea_tab', t); } catch (e) {}
}
let lang = 'pt';
try { lang = localStorage.getItem('kilauea_lang') || 'pt'; } catch (e) {}
setLang(lang);
let aba = 'status';
try { aba = sessionStorage.getItem('kilauea_tab') || 'status'; } catch (e) {}
setTab(aba);
""".replace("__I18N__", json.dumps(i18n, ensure_ascii=False).replace("</", "<\\/"))

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="300">
<title>Kilauea agora</title>
<style>
body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; background: #f7f3ee; color: #2b2622; }}
.banner {{ background: linear-gradient(160deg, {fundo}, {sombra}); color: #fff;
           padding: 36px 16px 30px; text-align: center; position: relative; }}
.banner h1 {{ margin: 0 0 8px; font-size: 2.1em; letter-spacing: .3px; text-shadow: 0 1px 3px rgba(0,0,0,.25); }}
.banner p {{ margin: 4px 0; opacity: .92; }}
.langs {{ position: absolute; top: 10px; right: 12px; }}
.flag {{ background: none; border: 1px solid rgba(255,255,255,.7); border-radius: 4px; padding: 2px 3px;
         margin-left: 6px; cursor: pointer; line-height: 0; opacity: .55; }}
.flag.active {{ opacity: 1; border-color: #fff; }}
.flag svg {{ display: block; }}
.tabs {{ display: flex; justify-content: center; gap: 8px; background: #fffdfa;
         box-shadow: 0 2px 8px rgba(60,40,20,.08); padding: 10px; position: sticky; top: 0; z-index: 5; }}
.tab-btn {{ background: none; border: 0; border-radius: 999px; font-size: 1em;
            padding: 8px 20px; cursor: pointer; color: #6b6157; }}
.tab-btn.on {{ background: {fundo}; color: #fff; font-weight: 600; }}
.wrap {{ max-width: 780px; margin: 0 auto; padding: 18px 16px 26px; }}
.pane {{ display: none; }}
.pane.on {{ display: block; }}
.facts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; margin: 4px 0 18px; }}
.fact {{ background: #fffdfa; border-radius: 14px; padding: 13px 15px;
         box-shadow: 0 2px 8px rgba(60,40,20,.08); border-left: 4px solid {fundo}; }}
.f-label {{ font-size: .74em; text-transform: uppercase; letter-spacing: .6px; color: #98897a; }}
.f-val {{ margin-top: 3px; font-size: .98em; font-weight: 600; line-height: 1.35; }}
.f-val a {{ font-weight: 400; }}
.dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 7px; }}
.dot-live {{ background: #d2331f; box-shadow: 0 0 0 3px rgba(210,51,31,.22); }}
.dot-pause {{ background: #e0a400; box-shadow: 0 0 0 3px rgba(224,164,0,.2); }}
.dot-off {{ background: #1e7e34; box-shadow: 0 0 0 3px rgba(30,126,52,.2); }}
.card {{ background: #fffdfa; border-radius: 14px; padding: 18px 20px; margin: 14px 0;
         box-shadow: 0 2px 8px rgba(60,40,20,.08); }}
.card h2 {{ margin: 0 0 10px; font-size: 1.02em; color: #6b6157; text-transform: uppercase;
            letter-spacing: .5px; font-weight: 600; }}
.card p {{ line-height: 1.55; }}
table {{ border-collapse: collapse; width: 100%; }}
td {{ padding: 7px 8px; border-bottom: 1px solid #f0e9e0; font-size: .95em; }}
a {{ color: #b3541e; }}
.mono {{ font-size: .85em; color: #98897a; }}
.video {{ position: relative; padding-top: 56.25%; margin: 6px 0 20px; }}
.video iframe {{ position: absolute; inset: 0; width: 100%; height: 100%; border: 0; border-radius: 12px;
                 box-shadow: 0 2px 10px rgba(60,40,20,.15); }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }}
figure {{ margin: 0; }}
figure img {{ width: 100%; border-radius: 10px; display: block; box-shadow: 0 2px 8px rgba(60,40,20,.12); }}
figcaption {{ margin-top: 5px; }}
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
<div class="tabs">
<button class="tab-btn on" data-tab="status" data-i18n="tab_status" onclick="setTab('status')"></button>
<button class="tab-btn" data-tab="live" data-i18n="tab_live" onclick="setTab('live')"></button>
<button class="tab-btn" data-tab="fotos" data-i18n="tab_fotos" onclick="setTab('fotos')"></button>
</div>
<div class="wrap">

<div class="pane on" data-pane="status">
<div class="facts">
<div class="fact"><div class="f-label" data-i18n="fl1"></div><div class="f-val" data-i18n-html="fv1"></div></div>
<div class="fact"><div class="f-label" data-i18n="fl2"></div><div class="f-val" data-i18n-html="fv2"></div></div>
<div class="fact"><div class="f-label" data-i18n="fl3"></div><div class="f-val" data-i18n-html="fv3"></div></div>
<div class="fact"><div class="f-label" data-i18n="fl4"></div><div class="f-val" data-i18n-html="fv4"></div></div>
<div class="fact"><div class="f-label" data-i18n="fl5"></div><div class="f-val" data-i18n-html="fv5"></div></div>
<div class="fact"><div class="f-label" data-i18n="fl6"></div><div class="f-val" data-i18n-html="fv6"></div></div>
</div>
<div class="card"><h2 data-i18n="h_aviso"></h2><div data-i18n-html="aviso"></div>
<p class="mono" data-i18n-html="fonte"></p></div>
<div class="card"><h2 data-i18n="h_hist"></h2>
<table>{linhas_hist}</table>
<p class="mono" data-i18n="hist_nota"></p></div>
</div>

<div class="pane" data-pane="live">
<div class="card"><h2 data-i18n="h_live"></h2>
{lives_html}
<p class="mono" data-i18n="live_nota"></p></div>
<div class="card"><h2 data-i18n="h_maislinks"></h2>
<p data-i18n-html="live"></p></div>
</div>

<div class="pane" data-pane="fotos">
<div class="card"><h2 data-i18n="h_fotos"></h2>
{fotos_link}
<div class="grid">{fotos_html}</div>
<p class="mono" data-i18n="fotos_credito"></p></div>
</div>

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
    midia = {}
    if MIDIA_CACHE.exists():
        try:
            midia = json.loads(MIDIA_CACHE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            midia = {}

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

    lives, lives_link = lives_atuais(midia)
    fotos = fotos_episodio(midia)
    print(f"lives no ar (embed): {[s['id'] for s in lives]}; so link: {[s['id'] for s in lives_link]}")
    print(f"fotos: {len(fotos.get('itens') or [])} de {fotos.get('slug', '-')}")

    STATE_FILE.write_text(json.dumps(atual, indent=2), encoding="utf-8")
    HISTORY_FILE.write_text(json.dumps(historico, indent=2), encoding="utf-8")
    MIDIA_CACHE.write_text(
        json.dumps({"lives": lives, "lives_link": lives_link, "fotos": fotos},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    aviso_pt = traduz_aviso(atual["notice_identifier"], resumo_html, sinopse)
    ep_en, prev_en = frases_chave(sinopse)

    def _t(s):
        if not s:
            return ""
        try:
            return _traduz_bloco(s)
        except Exception:  # noqa: BLE001 - fallback: frase original
            return s

    frases = {"ep_en": ep_en, "ep_pt": _t(ep_en),
              "prev_en": prev_en, "prev_pt": _t(prev_en)}
    pagina = gera_pagina(atual, sinopse, resumo_html, historico, agora_utc,
                         aviso_pt, lives, lives_link, fotos, frases)
    upload_pa(pagina)
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
