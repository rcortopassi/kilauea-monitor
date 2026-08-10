#!/usr/bin/env python3
"""
Monitor do Kilauea (Big Island, Havai).

Roda no GitHub Actions a cada 5 minutos:
  1. Consulta a API publica do USGS/HANS (getElevatedVolcanoes).
  2. Compara color_code / alert_level com o estado anterior (state/state.json).
  3. Se o vulcao subiu para ORANGE ou RED -> alerta URGENTE via ntfy.sh e
     Telegram (episodio de fonte de lava: "va para o parque agora").
     Rebaixamento ou outras mudancas -> aviso informativo.
  4. Busca as fotos oficiais mais recentes do episodio (USGS, dominio publico)
     e verifica quais livestreams do YouTube estao no ar.
  5. Gera a pagina de status (abas Status / Ao vivo / Fotos, PT/EN)
     e sobe para o PythonAnywhere em /kilauea/.

Somente stdlib. Variaveis de ambiente:
  NTFY_TOPIC     - topico do ntfy.sh (secreto; quem souber o nome pode ler/postar)
  TELEGRAM_TOKEN - token do bot do Telegram (opcional; redundancia ao ntfy)
  TELEGRAM_CHAT  - chat_id de destino no Telegram (opcional)
  PA_TOKEN       - token da API do PythonAnywhere (o mesmo de painel/.env)
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
GALERIA_FILE = BASE / "state" / "galeria.json"

VNUM = "332010"  # Kilauea
ELEVATED_URL = "https://volcanoes.usgs.gov/hans-public/api/volcano/getElevatedVolcanoes"
NOTICE_URL = "https://volcanoes.usgs.gov/hans-public/api/notice/getNotice/{ident}"
CHRONO_URL = "https://www.usgs.gov/volcanoes/kilauea/photo-and-video-chronology"

# Lives conhecidas de monitoramento continuo do Kilauea (a ordem importa)
# As tres cameras OFICIAIS do USGS no Halemaumau vem primeiro: imagem melhor e
# fonte primaria. As de terceiros ficam como reserva, so entram se as oficiais
# sairem do ar (o codigo pega as 3 primeiras que estiverem vivas e com embed).
LIVES_FIXAS = [
    "HggWKlZv9yk",  # USGS V1cam - oeste da cratera
    "gXKuUyKt8mc",  # USGS V3cam - sul da cratera
    "Tz5tPqRRv1Y",  # USGS V2cam - leste da cratera
    "c1EH9TQ2XR0",  # Lava Watchers (reserva)
    "FVdmnpJ2kM0",  # afarTV (reserva)
]

# Legenda curta por camera conhecida: id -> (pt, en). O titulo do YouTube so
# existe em ingles, entao isto e o que o visitante brasileiro le.
LIVES_ROTULO = {
    "HggWKlZv9yk": ("USGS V1cam, lado oeste da cratera Halemaʻumaʻu",
                    "USGS V1cam, west side of Halemaʻumaʻu crater"),
    "Tz5tPqRRv1Y": ("USGS V2cam, lado leste da cratera Halemaʻumaʻu",
                    "USGS V2cam, east side of Halemaʻumaʻu crater"),
    "gXKuUyKt8mc": ("USGS V3cam, lado sul da cratera Halemaʻumaʻu",
                    "USGS V3cam, south side of Halemaʻumaʻu crater"),
}
BUSCA_LIVES = ("https://www.youtube.com/results"
               "?search_query=kilauea+volcano+live+eruption&sp=EgJAAQ%3D%3D")

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT", "")
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
    "ORANGE": "ERUPÇÃO EM CURSO",
    "RED": "ERUPÇÃO MAIOR EM CURSO",
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
LINK_PARKING = "https://www.nps.gov/havo/planyourvisit/parking.htm"
LINK_VIEWING = "https://www.nps.gov/havo/planyourvisit/eruption-viewing.htm"
LINK_SITE = "https://rafaelcortopassi.pythonanywhere.com/kilauea/"

# Avisos ativos do parque nacional (API oficial do NPS; DEMO_KEY funciona,
# mas aceita chave propria via env NPS_KEY se um dia limitar)
NPS_KEY = os.environ.get("NPS_KEY", "DEMO_KEY")
NPS_ALERTS_URL = ("https://developer.nps.gov/api/v1/alerts"
                  "?parkCode=havo&limit=50&api_key={key}")
ALERTAS_CACHE = BASE / "state" / "alertas_nps.json"

# Onde fica cada ponto citado nos avisos do parque: palavra-chave no texto ->
# (nome PT, nome EN, lat, lng). O primeiro que casar vence.
LOCAIS_ALERTA = [
    ("sulfur banks", "Trilha Sulphur Banks (Haʻakulamanu)",
     "Sulfur Banks Trail (Haʻakulamanu)", 19.4322, -155.2644),
    ("nāhuku", "Nāhuku (Thurston Lava Tube)",
     "Nāhuku (Thurston Lava Tube)", 19.4134, -155.2381),
    ("lava tube", "Nāhuku (Thurston Lava Tube)",
     "Nāhuku (Thurston Lava Tube)", 19.4134, -155.2381),
    ("kīpukapuaulu", "Kīpukapuaulu (Bird Park), Mauna Loa Road",
     "Kīpukapuaulu (Bird Park), Mauna Loa Road", 19.4386, -155.3034),
    ("kahuku", "Unidade Kahuku (entrada, Hwy 11)",
     "Kahuku Unit (entrance, Hwy 11)", 19.0690, -155.6778),
    ("tephra", "Cume do Kīlauea, área a favor do vento",
     "Kīlauea summit, downwind area", 19.4040, -155.2920),
    ("eruption", "Halemaʻumaʻu (cratera em erupção)",
     "Halemaʻumaʻu (erupting crater)", 19.4067, -155.2800),
]

# DE ONDE SAI A LAVA. Todos os episodios desde 23/12/2024 vem da MESMA cratera,
# a Halemaumau, dentro da caldeira do cume; dentro dela ha duas bocas (norte e
# sul), lado a lado, no setor SUDOESTE do piso. O USGS nao publica a coordenada
# de cada boca, entao marcamos a cratera e desenhamos a AREA aproximada delas.
HALEMAUMAU = (19.4067, -155.2800)
BOCAS_APROX = (19.4052, -155.2830)
BOCAS_RAIO_M = 350

# De onde cada camera do USGS filma. O USGS publica apenas o SETOR da borda
# ("northwest rim of Halemaumau", "northeast rim of the summit caldera",
# "southern rim of the summit caldera"), nunca a coordenada; e as tres sao
# pan-tilt-zoom, ou seja, o enquadramento muda conforme a atividade. Logo: a
# posicao aqui e aproximada dentro do setor certo e a linha ate as bocas
# indica a direcao geral do olhar, nao o campo de visao exato.
CAMERAS = [
    ("HggWKlZv9yk", "V1cam", 19.4110, -155.2850,
     "Borda noroeste da própria cratera Halemaʻumaʻu. É a mais próxima das bocas.",
     "Northwest rim of Halemaʻumaʻu crater itself. The closest one to the vents."),
    ("Tz5tPqRRv1Y", "V2cam", 19.4270, -155.2610,
     "Borda nordeste da caldeira do cume. É a mais distante: mostra a cratera "
     "inteira, de longe.",
     "Northeast rim of the summit caldera. The farthest one: it shows the whole "
     "crater from a distance."),
    ("gXKuUyKt8mc", "V3cam", 19.3970, -155.2760,
     "Borda sul da caldeira do cume. É a que o próprio USGS descreve como a vista "
     "ao vivo das bocas que entram em erupção no setor sudoeste do Halemaʻumaʻu.",
     "South rim of the summit caldera. USGS describes it as the live view of the "
     "vents that erupt in the southwest part of Halemaʻumaʻu."),
]

# Avisos fixos ("Park Notices" e politicas da pagina de condicoes do NPS,
# que NAO vem pela API de alertas). Textos ja escritos nas duas linguas.
AVISOS_FIXOS = [
    {"id": "fixo-obras", "cat": "closure",
     "titulo": "Summit construction: closures and delays",
     "titulo_pt": "Obras no cume: fechamentos e atrasos",
     "desc": ("Expect closures and delays due to a two-year construction project "
              "to repair or remove damaged buildings and infrastructure at the "
              "summit. The visitor center is closed during renovations."),
     "desc_pt": ("Espere fechamentos e atrasos por causa de uma obra de dois anos "
                 "para reparar ou remover prédios e infraestrutura danificados no "
                 "cume. O centro de visitantes está fechado durante a reforma."),
     "url": LINK_PARQUE, "data": "",
     "local_pt": "Área do cume, junto ao Kīlauea Visitor Center",
     "local_en": "Summit area, by the Kīlauea Visitor Center",
     "lat": 19.4293, "lng": -155.2575},
    {"id": "fixo-ar", "cat": "caution",
     "titulo": "Air quality: volcanic gases",
     "titulo_pt": "Qualidade do ar: gases vulcânicos",
     "desc": ("Hazardous volcanic gases (SO2/vog) can be dangerous to sensitive "
              "groups. Check the air quality frequently during your visit."),
     "desc_pt": ("Gases vulcânicos perigosos (SO2/vog) podem ser um risco para "
                 "grupos sensíveis. Confira a qualidade do ar com frequência "
                 "durante a visita."),
     "url": "https://www.nps.gov/havo/air-quality-alert.htm", "data": "",
     "local_pt": "", "local_en": "", "lat": None, "lng": None},
    {"id": "fixo-drones", "cat": "info",
     "titulo": "Drones are prohibited",
     "titulo_pt": "Drones são proibidos",
     "desc": ("Launching, landing or operating unmanned aircraft anywhere in the "
              "park is prohibited unless approved in writing by the superintendent."),
     "desc_pt": ("Decolar, pousar ou operar drones em qualquer ponto do parque é "
                 "proibido, salvo autorização escrita do superintendente."),
     "url": "https://www.nps.gov/havo/learn/management/2015_unmanned_aircraft.htm",
     "data": "", "local_pt": "", "local_en": "", "lat": None, "lng": None},
]

# Mirantes oficiais de observacao da erupcao (pagina Eruption Viewing do NPS,
# /havo/planyourvisit/eruption-viewing.htm; resumos condensados dos textos
# oficiais): (nome, desc PT, desc EN, lat, lng, url da pagina do lugar)
MIRANTES = [
    ("Mirante perto do Welcome Center",
     "Do Welcome Center, cruze o gramado e a Crater Rim Drive, entre na floresta "
     "e vire à esquerda na Crater Rim Trail rumo aos Steam Vents; o primeiro "
     "mirante à direita tem ótima vista da caldeira e da erupção.",
     "From the Welcome Center, cross the lawn and Crater Rim Drive, enter the "
     "forest and turn left on Crater Rim Trail toward Steam Vents; the first "
     "overlook on the right has great views of the caldera and the eruption.",
     19.4298, -155.2740,
     "https://www.nps.gov/places/eruption-viewing-near-welcome-center.htm"),
    ("Uēkahuna",
     "Vista ampla da Halemaʻumaʻu no fim da Crater Rim Drive West, a 4,5 km da "
     "entrada. Bom para famílias, guardas costumam estar no local e há mais "
     "vagas que nos outros mirantes.",
     "Great views into Halemaʻumaʻu at the end of Crater Rim Drive West, 2.8 mi "
     "from the entrance. Family friendly, rangers often on site and more "
     "parking than other overlooks.",
     19.4203, -155.2882,
     "https://www.nps.gov/places/eruption-viewing-from-uekahuna.htm"),
    ("Kīlauea Overlook",
     "Vista desimpedida do fundo da cratera durante a erupção, a 4 km da "
     "entrada. Caminhada curta desde o estacionamento, ou 650 m a pé de "
     "Uēkahuna.",
     "Unobstructed views of the crater floor during an eruption, 2.5 mi from "
     "the entrance. Short walk from the lot, or a 0.4 mi walk from Uēkahuna.",
     19.4234, -155.2839,
     "https://www.nps.gov/places/eruption-viewing-from-kapalikapuokamohoalii.htm"),
    ("Perto de Keanakākoʻi",
     "A vista mais de perto, mas exige planejamento: 3,2 km ida e volta a pé "
     "(cerca de 1h) pela antiga Crater Rim Drive desde o estacionamento "
     "Devastation; vagas extremamente limitadas durante erupções.",
     "The closest views, but plan ahead: a 2 mi round-trip hike (about 1 h) on "
     "old Crater Rim Drive from the Devastation parking area; parking is "
     "extremely limited during eruptions.",
     19.4060, -155.2610,
     "https://www.nps.gov/places/eruption-viewing-at-keanakakoi.htm"),
    ("Wahinekapu (Steaming Bluff)",
     "Vista panorâmica do cone inteiro, com o calor dos steam vents ao lado. "
     "Primeiro mirante depois da entrada (1,6 km), popular e congestionado.",
     "Panoramic, unobstructed views of the whole cinder cone, with steam vents "
     "nearby. First overlook after the entrance (1 mi), popular and congested.",
     19.4312, -155.2668,
     "https://www.nps.gov/places/eruption-viewing-from-wahinekapu.htm"),
    ("Kūpinaʻi Pali (Waldron Ledge)",
     "Para fugir das multidões: o mirante mais distante da erupção, com vista "
     "aberta da caldeira. Estacione no visitor center (fechado) e caminhe 800 m "
     "passando o Volcano House, pela Crater Rim Trail.",
     "Escape the crowds: the furthest overlook from the eruption, with wide "
     "views of the caldera. Park at the closed visitor center and walk 0.5 mi "
     "past Volcano House on Crater Rim Trail.",
     19.4277, -155.2549,
     "https://www.nps.gov/places/eruption-viewing-from-kupinai-pali.htm"),
]

# Estacionamentos oficiais (pagina Parking do NPS, coordenadas de la):
# (nome, vagas, vagas grandes, lat, lng, obs PT, obs EN, fora da vista inicial,
#  minutos de carro alem da ENTRADA do parque)
# Tempo ate a entrada do parque pela Hwy 11, sem transito: Hilo ~45 min,
# Kailua-Kona ~2h15 (via Kaʻū). O popup soma o trecho interno de cada bolsao.
MIN_HILO_ENTRADA = 45
MIN_KONA_ENTRADA = 135
ESTACIONAMENTOS = [
    ("Welcome Center Parking Lot", 100, 3, 19.432721, -155.275361,
     "Dentro do Kilauea Military Camp; o Welcome Center fica a 270 m do bolsão",
     "Inside Kilauea Military Camp; the Welcome Center is 900 ft from the lot", False, 5),
    ("Kīlauea Visitor Center Parking", 38, 2, 19.429496, -155.257103,
     "Centro de visitantes em reforma; acesso ao Volcano House, galeria de arte e trilhas",
     "Visitor center closed for renovations; access to Volcano House, art gallery and trails", False, 2),
    ("Uēkahuna Parking", 70, 7, 19.420228, -155.288968,
     "Mirante mais alto da borda da caldeira", "Highest overlook on the caldera rim", False, 10),
    ("Kīlauea Overlook Parking", 36, 2, 19.423602, -155.284341,
     "Na Crater Rim Drive; vista clássica das fontes de lava",
     "On Crater Rim Drive; classic view of the lava fountains", False, 8),
    ("Kīlauea Iki Overlook Parking Lot", 64, 0, 19.416584, -155.242891, "", "", False, 8),
    ("Nāhuku (Lava Tube)", 14, 2, 19.413590, -155.238811,
     "Poucas vagas; lota cedo", "Few stalls; fills early", False, 10),
    ("Puʻupuaʻi Parking Lot", 28, 0, 19.411314, -155.249661, "", "", False, 10),
    ("Devastation Trail Parking Lot", 30, 0, 19.406470, -155.252939, "", "", False, 10),
    ("End of Chain of Craters Road Parking", 37, 0, 19.295039, -155.098597,
     "Fim da estrada, junto ao arco Hōlei", "Road's end, near Hōlei Sea Arch", True, 45),
    ("Kūkamāhuākea (Steam Vents)", None, None, 19.4306, -155.2660,
     "Acesso ao trecho aberto da trilha Sulphur Banks",
     "Access to the open section of Sulfur Banks Trail", False, 4),
]


def _fmt_min(m):
    """75 -> '1h15'; 50 -> '50 min' (arredondando a 5 min)."""
    m = 5 * round(m / 5)
    if m < 60:
        return f"{m} min"
    h, r = divmod(m, 60)
    return f"{h}h{r:02d}" if r else f"{h}h"

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


MES_NUM = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"])}
_MESES_RE = "|".join(MES_NUM)


def extrai_ultimo_ep(texto, ano_padrao):
    """Numero, inicio e fim do episodio mais recente citado no aviso do HVO.
    Cobre "episode 52 on July 28-29, 2026", "on June 30-July 1" e frases
    separadas de began/ended. Retorna dict {ep, inicio, fim} ou None."""
    t = re.sub(r"\b([apAP])\.[mM]\.", r"\1m", texto or "")

    def iso(mes, dia, ano):
        return f"{int(ano):04d}-{MES_NUM[mes.lower()]:02d}-{int(dia):02d}"

    m = re.search(rf"[Ee]pisode\s+(\d+)[^.]*?\bon\s+({_MESES_RE})\s+(\d+)\s*[-–]\s*"
                  rf"(?:({_MESES_RE})\s+)?(\d+)(?:,\s*(\d{{4}}))?", t, re.I)
    if m:
        ano = m.group(6) or ano_padrao
        return {"ep": int(m.group(1)),
                "inicio": iso(m.group(2), m.group(3), ano),
                "fim": iso(m.group(4) or m.group(2), m.group(5), ano)}
    res = {}
    for chave, verbo in (("inicio", "began|started"), ("fim", "ended")):
        mm = re.search(rf"[Ee]pisode\s+(\d+)\s+(?:{verbo})[^.]*?\bon\s+"
                       rf"({_MESES_RE})\s+(\d+)(?:,\s*(\d{{4}}))?", t, re.I)
        if mm:
            res.setdefault("ep", int(mm.group(1)))
            res[chave] = iso(mm.group(2), mm.group(3), mm.group(4) or ano_padrao)
    return res or None


def frases_chave(sinopse):
    """Extrai do aviso do HVO a frase do ultimo/atual episodio e a de previsao."""
    # "2:36 a.m." viraria fim de frase; normaliza para "2:36 am" antes de extrair
    s = re.sub(r"\b([apAP])\.[mM]\.", r"\1m", sinopse or "")
    ep = (re.search(r"([^.]*[Ee]pisode\s+\d+\s+(?:began|ended|started)[^.]*\.)", s)
          or re.search(r"([^.]*(?:end|start|beginning) of [Ee]pisode\s+\d+[^.]*\.)", s))
    prev = re.search(r"([^.]*(?:another episode|next episode|forecast|precursory)[^.]*\.)", s)
    return (ep.group(1).strip() if ep else "",
            prev.group(1).strip() if prev else "")


# ---------------------------------------------------------------- parque (NPS)

def _cat_alerta(cat):
    """Categoria do NPS -> chave curta usada em cores e rotulos."""
    c = (cat or "").lower()
    if "danger" in c:
        return "danger"
    if "caution" in c:
        return "caution"
    if "closure" in c:
        return "closure"
    return "info"


def alertas_nps(cache):
    """Avisos ativos do parque nacional (Park Closures, Danger, Caution...)
    pela API oficial do NPS. Traducao PT via gtx, reaproveitada do cache
    (state/alertas_nps.json) enquanto o texto nao mudar; coordenadas do
    ponto real do parque via palavra-chave (LOCAIS_ALERTA). Em falha de
    rede, devolve o cache como esta."""
    antigos = {a.get("id"): a for a in cache.get("alertas", [])}
    try:
        d = fetch_json(NPS_ALERTS_URL.format(key=quote(NPS_KEY, safe="")))
        brutos = d.get("data") or []
    except Exception as e:  # noqa: BLE001 - alertas sao opcionais
        print(f"aviso: alertas do NPS indisponiveis ({e}); usando cache")
        return cache.get("alertas", [])
    saida = []
    for b in brutos:
        titulo = (b.get("title") or "").strip()
        desc = (b.get("description") or "").strip()
        if not (titulo or desc):
            continue
        aid = b.get("id") or titulo
        ant = antigos.get(aid) or {}
        if ant.get("titulo") == titulo and ant.get("desc") == desc and ant.get("titulo_pt"):
            titulo_pt, desc_pt = ant["titulo_pt"], ant["desc_pt"]
        else:
            try:
                titulo_pt = _traduz_bloco(titulo) if titulo else ""
                desc_pt = _traduz_bloco(desc) if desc else ""
            except Exception as e:  # noqa: BLE001 - sem traducao, fica o original
                print(f"aviso: traducao de alerta do NPS falhou ({e})")
                titulo_pt, desc_pt = titulo, desc
        chave = f"{titulo} {desc}".lower()
        local_pt = local_en = ""
        lat = lng = None
        for kw, npt, nen, la, ln in LOCAIS_ALERTA:
            if kw in chave:
                local_pt, local_en, lat, lng = npt, nen, la, ln
                break
        saida.append({
            "id": aid,
            "titulo": titulo, "titulo_pt": titulo_pt,
            "desc": desc, "desc_pt": desc_pt,
            "cat": _cat_alerta(b.get("category")),
            "url": (b.get("url") or "").strip(),
            "data": (b.get("lastIndexedDate") or "")[:10],
            "local_pt": local_pt, "local_en": local_en,
            "lat": lat, "lng": lng,
        })
    return saida


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
        em = re.search(r"[Ee]pisode\s+(\d+)", titulo) or re.search(r"episode-(\d+)", slug)
        ep_num = int(em.group(1)) if em else 0
        dm = (re.search(r'datetime="(\d{4}-\d{2}-\d{2})', art)
              or re.search(r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})', art))
        data = dm.group(1) if dm else ""
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
        return {"slug": slug, "titulo": titulo, "ep": ep_num, "data": data,
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


def push_telegram(titulo, corpo, urgente=False):
    """Redundancia ao ntfy: manda o mesmo alerta por um bot do Telegram.
    Inerte se TELEGRAM_TOKEN/TELEGRAM_CHAT nao estiverem definidos."""
    if not (TG_TOKEN and TG_CHAT):
        return
    sino = "\U0001f6a8 " if urgente else ""
    texto = (f"{sino}<b>{html_mod.escape(titulo)}</b>\n\n{html_mod.escape(corpo)}\n\n"
             f"{LINK_SITE}")
    dados = json.dumps({
        "chat_id": TG_CHAT,
        "text": texto[:4000],
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "disable_notification": not urgente,
    }).encode("utf-8")
    req = Request(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                  data=dados, method="POST",
                  headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=30) as r:
            print(f"telegram enviado ({r.getcode()}): {titulo}")
    except Exception as e:  # noqa: BLE001 - telegram e redundancia, nao pode derrubar o monitor
        print(f"ERRO no telegram: {e}")


def notifica(titulo, corpo, prioridade="default", tags="", click=""):
    """Dispara o alerta por todos os canais configurados."""
    push_ntfy(titulo, corpo, prioridade, tags, click)
    push_telegram(titulo, corpo, urgente=(prioridade in ("urgent", "high")))


def fmt_hora(dt_utc, lang="pt"):
    if not dt_utc:
        return "-"
    hst = dt_utc.astimezone(HST).strftime("%d/%m %H:%M")
    brt = dt_utc.astimezone(BRT).strftime("%d/%m %H:%M")
    if lang == "en":
        return f"{hst} in Hawaii ({brt} in Brasilia)"
    return f"{hst} no Havaí ({brt} em Brasília)"


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

CAT_ROTULO = {
    "danger": ("Perigo", "Danger"),
    "caution": ("Atenção", "Caution"),
    "closure": ("Fechamento", "Closure"),
    "info": ("Informação", "Info"),
}


def _bloco_alertas(alertas, lang):
    """HTML da lista de avisos ativos do parque, num idioma."""
    pt = lang == "pt"
    if not alertas:
        return ("<p>Nenhum aviso ativo do parque no momento.</p>" if pt
                else "<p>No active park alerts right now.</p>")
    partes = []
    for a in alertas:
        rot = CAT_ROTULO.get(a["cat"], CAT_ROTULO["info"])[0 if pt else 1]
        tit = a["titulo_pt"] if pt else a["titulo"]
        desc = a["desc_pt"] if pt else a["desc"]
        rodape = []
        local = a["local_pt"] if pt else a["local_en"]
        if local:
            rodape.append(html_mod.escape(local))
        if a.get("url"):
            u = html_mod.escape(a["url"], quote=True)
            rodape.append(f'<a href="{u}">{"Detalhes" if pt else "Details"}</a>')
        rod = f'<p class="mono">{" &middot; ".join(rodape)}</p>' if rodape else ""
        partes.append(
            f'<div class="alerta"><p><span class="cat cat-{a["cat"]}">{rot}</span> '
            f'<strong>{html_mod.escape(tit)}</strong></p>'
            f'<p>{html_mod.escape(desc)}</p>{rod}</div>'
        )
    return "".join(partes)


def gera_pagina(atual, sinopse, resumo_html, historico, agora_utc,
                aviso_pt="", lives=None, lives_link=None, fotos=None, frases=None,
                galeria=None, alertas=None):
    lives = lives or []
    lives_link = lives_link or []
    fotos = fotos or {}
    frases = frases or {}
    galeria = galeria or []
    alertas = alertas or []
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
    lives_html, lcaps = "", {}
    for i, s in enumerate(lives):
        rot = html_mod.escape(f"{s['titulo']} ({s['canal']})" if s["canal"] else s["titulo"])
        pt_rot, en_rot = LIVES_ROTULO.get(s["id"], ("", ""))
        lcaps[f"lcap_{i}"] = {"pt": pt_rot or rot, "en": en_rot or rot}
        lives_html += (
            f'<p class="mono" data-i18n="lcap_{i}"></p>'
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
        visita_pt = "As fontes são visíveis dos mirantes e atraem multidões. "
        visita_en = "The fountains are visible from the overlooks and draw crowds. "
    elif cor == "YELLOW":
        f1_pt = '<span class="dot dot-pause"></span>Em pausa, sem lava visível no momento'
        f1_en = '<span class="dot dot-pause"></span>Paused, no lava visible right now'
        visita_pt = ""
        visita_en = ""
    else:
        f1_pt = '<span class="dot dot-off"></span>Não, sem erupção'
        f1_en = '<span class="dot dot-off"></span>No, not erupting'
        visita_pt = ""
        visita_en = ""
    f2_pt = (f"Costuma abrir 24 h, mas não é garantido: gases vulcânicos tóxicos (SO2/vog), "
             f"cinzas ou fios de vidro (cabelo de Pele) fecham áreas ou o parque inteiro "
             f"quando o vento muda. {visita_pt}"
             f'<a href="{LINK_PARQUE}">Confira as condições atuais antes de ir</a>')
    f2_en = (f"Usually open 24/7, but not guaranteed: toxic volcanic gases (SO2/vog), ash "
             f"or glass strands (Pele's hair) close areas or the whole park when the wind "
             f"shifts. {visita_en}"
             f'<a href="{LINK_PARQUE}">Check current conditions before you go</a>')
    f3_pt = f"Sequência de episódios desde 23/12/2024, há {meses} meses"
    f3_en = f"Episodic sequence since Dec 23, 2024, {meses} months and counting"
    f5_pt = html_mod.escape(frases.get("prev_pt") or "Sem previsão divulgada no aviso atual")
    f5_en = html_mod.escape(frases.get("prev_en") or "No forecast in the current notice")

    def fmt_data(iso, lang):
        try:
            y, m, d = iso.split("-")
            if lang == "en":
                mes = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(m) - 1]
                return f"{mes} {int(d)}, {y}"
            return f"{d}/{m}/{y}"
        except Exception:  # noqa: BLE001
            return ""

    # --- ultimo episodio: numero + inicio e fim, do dado estruturado persistido
    ult = frases.get("ult") or {}
    if ult.get("ep"):
        n = ult["ep"]
        i_pt, f_pt = fmt_data(ult.get("inicio", ""), "pt"), fmt_data(ult.get("fim", ""), "pt")
        i_en, f_en = fmt_data(ult.get("inicio", ""), "en"), fmt_data(ult.get("fim", ""), "en")
        if i_pt and f_pt:
            f4_pt = f"Episódio {n}: começou em {i_pt} e terminou em {f_pt}"
            f4_en = f"Episode {n}: started {i_en} and ended {f_en}"
        elif f_pt:
            f4_pt = f"Episódio {n}: terminou em {f_pt}"
            f4_en = f"Episode {n}: ended {f_en}"
        elif i_pt:
            f4_pt = f"Episódio {n}: começou em {i_pt}"
            f4_en = f"Episode {n}: started {i_en}"
        else:
            f4_pt, f4_en = f"Episódio {n}", f"Episode {n}"
    else:
        f4_pt = html_mod.escape(frases.get("ep_pt") or "Sem dados no aviso atual")
        f4_en = html_mod.escape(frases.get("ep_en") or "No data in the current notice")

    # --- galeria dos episodios anteriores
    galeria_html, gcaps = "", {}
    for i, g in enumerate(galeria):
        d_pt, d_en = fmt_data(g.get("data", ""), "pt"), fmt_data(g.get("data", ""), "en")
        gcaps[f"gcap_{i}"] = {
            "pt": f"Episódio {g['ep']}" + (f", {d_pt}" if d_pt else ""),
            "en": f"Episode {g['ep']}" + (f", {d_en}" if d_en else ""),
        }
        galeria_html += (
            f'<figure><img src="{html_mod.escape(g["src"], quote=True)}" loading="lazy" '
            f'alt="{html_mod.escape(g.get("cap_en") or "", quote=True)}">'
            f'<figcaption class="mono" data-i18n="gcap_{i}"></figcaption></figure>'
        )

    # --- de onde sai a lava (texto do popup da cratera no mapa)
    ep_txt_pt = ep_txt_en = ""
    if ult.get("ep"):
        di, df = fmt_data(ult.get("inicio", ""), "pt"), fmt_data(ult.get("fim", ""), "pt")
        ei, ef = fmt_data(ult.get("inicio", ""), "en"), fmt_data(ult.get("fim", ""), "en")
        quando_pt = f" ({di} a {df})" if di and df else (f" ({di})" if di else "")
        quando_en = f" ({ei} to {ef})" if ei and ef else (f" ({ei})" if ei else "")
        ep_txt_pt = (f"O episódio {ult['ep']}{quando_pt}, o mais recente, "
                     f"saiu daqui. ")
        ep_txt_en = (f"Episode {ult['ep']}{quando_en}, the most recent one, "
                     f"came from here. ")
    erup_pt = (
        "Todos os episódios desde 23/12/2024 saem desta mesma cratera, a "
        "Halemaʻumaʻu, dentro da caldeira do cume. Não é uma cratera nova a cada vez. "
        + ep_txt_pt +
        "Dentro dela existem duas bocas lado a lado, no setor sudoeste do piso: "
        "a boca norte e a boca sul. A boca norte é a que tem jorrado mais alto nos "
        "últimos episódios; a sul costuma só brilhar ou soltar chamas. "
        "O círculo tracejado é a área aproximada das bocas: o USGS não publica a "
        "coordenada exata de cada uma."
    )
    erup_en = (
        "Every episode since Dec 23, 2024 comes from this same crater, "
        "Halemaʻumaʻu, inside the summit caldera. It is not a new crater each time. "
        + ep_txt_en +
        "Inside it there are two vents side by side, on the southwest part of the "
        "floor: the north vent and the south vent. The north vent has produced the "
        "tallest fountains in recent episodes; the south one usually just glows or "
        "emits flames. The dashed circle is the approximate vent area: the USGS does "
        "not publish exact coordinates for each vent."
    )

    # --- avisos do parque nacional + dados do mapa
    alertas_html_pt = _bloco_alertas(alertas, "pt")
    alertas_html_en = _bloco_alertas(alertas, "en")
    mapa_dados = {
        "alertas": [
            {"t": a["titulo"], "t_pt": a["titulo_pt"],
             "d": a["desc"], "d_pt": a["desc_pt"],
             "cat": a["cat"], "url": a["url"],
             "l": a["local_en"], "l_pt": a["local_pt"],
             "lat": a["lat"], "lng": a["lng"],
             "longe": a["lat"] < 19.2}
            for a in alertas if a.get("lat") is not None
        ],
        "estac": [
            {"n": n, "v": v, "o": o, "lat": la, "lng": ln,
             "obs": oen, "obs_pt": opt, "longe": longe,
             "hilo": _fmt_min(MIN_HILO_ENTRADA + extra),
             "kona": _fmt_min(MIN_KONA_ENTRADA + extra)}
            for (n, v, o, la, ln, opt, oen, longe, extra) in ESTACIONAMENTOS
        ],
        "mirantes": [
            {"n": n, "d_pt": dpt, "d": den, "lat": la, "lng": ln, "url": url}
            for (n, dpt, den, la, ln, url) in MIRANTES
        ],
        "erupcao": {
            "lat": HALEMAUMAU[0], "lng": HALEMAUMAU[1],
            "blat": BOCAS_APROX[0], "blng": BOCAS_APROX[1], "raio": BOCAS_RAIO_M,
            "t_pt": "Halemaʻumaʻu: é daqui que sai a lava",
            "t": "Halemaʻumaʻu: this is where the lava comes out",
            "d_pt": erup_pt, "d": erup_en,
        },
        "cameras": [
            {"id": vid, "n": nome, "lat": la, "lng": ln, "d_pt": dpt, "d": den,
             "ativa": any(s["id"] == vid for s in lives)}
            for (vid, nome, la, ln, dpt, den) in CAMERAS
        ],
    }
    alertas_fonte_pt = f'Fonte: <a href="{LINK_PARQUE}">NPS – condições atuais do parque</a>'
    alertas_fonte_en = f'Source: <a href="{LINK_PARQUE}">NPS – current park conditions</a>'
    mapa_fonte_pt = (f'Dados: <a href="{LINK_PARQUE}">NPS – condições</a>, '
                     f'<a href="{LINK_PARKING}">estacionamentos</a> e '
                     f'<a href="{LINK_VIEWING}">mirantes da erupção</a>. '
                     f'Toque num ponto para ver o aviso ou as vagas e abrir no Google Maps. '
                     f'Os bolsões costumam lotar por volta das 10h. '
                     f'Tempos de carro a partir de Hilo e Kona são estimativas sem trânsito, '
                     f'pela Hwy 11; confirme a rota no Google Maps.')
    mapa_fonte_en = (f'Data: <a href="{LINK_PARQUE}">NPS – conditions</a>, '
                     f'<a href="{LINK_PARKING}">parking</a> and '
                     f'<a href="{LINK_VIEWING}">eruption viewpoints</a>. '
                     f'Tap a point to see the alert or stall count and open it in Google Maps. '
                     f'Lots are often full by 10 am. '
                     f'Driving times from Hilo and Kona are no-traffic estimates via Hwy 11; '
                     f'confirm the route in Google Maps.')

    live_pt = (f'<a href="{LINK_WEBCAMS}">Webcams do USGS na cratera</a><br>'
               f'<a href="{LINK_YOUTUBE}">Canal oficial do USGS no YouTube</a><br>' + extras)
    live_en = (f'<a href="{LINK_WEBCAMS}">USGS crater webcams</a><br>'
               f'<a href="{LINK_YOUTUBE}">Official USGS YouTube channel</a><br>' + extras)
    fonte_pt = f'Fonte: <a href="{LINK_UPDATES}">USGS - Kilauea updates</a>'
    fonte_en = f'Source: <a href="{LINK_UPDATES}">USGS - Kilauea updates</a>'

    i18n = {
        "pt": {
            "title": "Live Kilauea",
            "text": {
                "status": NIVEL_PT.get(cor, cor or "?"),
                "linha_codigo": f"Código de aviação {cor}, nível {nivel}",
                "linha_aviso": f"Aviso do USGS de {fmt_hora(quando, 'pt') if quando else '-'}",
                "linha_atualizacao": f"Página atualizada em {fmt_hora(agora_utc, 'pt')}",
                "tab_status": "Status",
                "tab_live": "Ao vivo",
                "rel_hi": "Havaí (HST)",
                "rel_br": "Brasília",
                "tab_fotos": "Fotos",
                "tab_mapa": "Mapa",
                "h_alertas": f"Avisos ativos do parque nacional ({len(alertas)})",
                "h_mapa": "Mapa: de onde sai a lava, avisos e estacionamentos",
                "leg_erup": "Bocas da erupção (Halemaʻumaʻu)",
                "leg_cam": "Câmeras ao vivo do USGS e o que elas olham",
                "mp_cume": "Cume do Kīlauea",
                "mp_coc": "Fim da Chain of Craters",
                "mp_kahuku": "Kahuku",
                "mp_gmaps": "Abrir no Google Maps",
                "leg_danger": "Perigo",
                "leg_caution": "Atenção",
                "leg_closure": "Fechamento",
                "leg_estac": "Estacionamento",
                "leg_mirante": "Mirante da erupção",
                "h_aviso": ("Último aviso do HVO (tradução automática do inglês)"
                            if aviso_pt else "Último aviso do HVO (original em inglês)"),
                "h_live": "Transmissões ao vivo",
                "live_nota": ("Players verificados a cada 5 minutos. Se um deles parar, "
                              "a próxima verificação busca outra transmissão no ar."),
                "live_vazio": "Nenhuma transmissão confirmada agora.",
                "h_maislinks": "Mais links",
                "h_fotos": "Fotos do episódio atual (USGS)",
                "h_galeria": "Episódios anteriores, uma foto de cada",
                "galeria_nota": ("Episódios sem artigo de fotos na cronologia do USGS "
                                 "não aparecem aqui."),
                "fotos_credito": "Fotos: USGS / Hawaiian Volcano Observatory, domínio público.",
                "fotos_vazio": "Sem fotos disponíveis no momento.",
                "h_hist": "Mudanças de nível registradas por este monitor",
                "hist_empty": "Nenhuma mudança registrada ainda",
                "hist_nota": "Horários do histórico em hora do Havaí (HST)",
                "fl1": "Em erupção agora?",
                "fl2": "Parque nacional: dá para visitar?",
                "fl3": "Erupção atual",
                "fl4": "Último episódio",
                "fl5": "Próximo episódio (previsão do HVO)",
                "rodape": (f"Verificado a cada 5 minutos. Última checagem: {fmt_hora(agora_utc, 'pt')}. "
                           "Dados: USGS Hawaiian Volcano Observatory (domínio público). Este site não é oficial."),
            },
            "html": {"live": live_pt, "fonte": fonte_pt, "aviso": aviso_pt_html,
                     "fv1": f1_pt, "fv2": f2_pt, "fv3": f3_pt,
                     "fv4": f4_pt, "fv5": f5_pt,
                     "alertas": alertas_html_pt, "alertas_fonte": alertas_fonte_pt,
                     "mapa_fonte": mapa_fonte_pt},
        },
        "en": {
            "title": "Live Kilauea",
            "text": {
                "status": NIVEL_EN.get(cor, cor or "?"),
                "linha_codigo": f"Aviation color code {cor}, alert level {nivel}",
                "linha_aviso": f"USGS notice from {fmt_hora(quando, 'en') if quando else '-'}",
                "linha_atualizacao": f"Page updated {fmt_hora(agora_utc, 'en')}",
                "tab_status": "Status",
                "tab_live": "Live",
                "rel_hi": "Hawaii (HST)",
                "rel_br": "Brasilia",
                "tab_fotos": "Photos",
                "tab_mapa": "Map",
                "h_alertas": f"Active national park alerts ({len(alertas)})",
                "h_mapa": "Map: where the lava comes from, alerts and parking",
                "leg_erup": "Eruption vents (Halemaʻumaʻu)",
                "leg_cam": "USGS live cameras and what they look at",
                "mp_cume": "Kīlauea summit",
                "mp_coc": "End of Chain of Craters",
                "mp_kahuku": "Kahuku",
                "mp_gmaps": "Open in Google Maps",
                "leg_danger": "Danger",
                "leg_caution": "Caution",
                "leg_closure": "Closure",
                "leg_estac": "Parking",
                "leg_mirante": "Eruption viewpoint",
                "h_aviso": "Latest HVO notice",
                "h_live": "Live streams",
                "live_nota": ("Players are checked every 5 minutes. If one goes offline, "
                              "the next check looks for another stream on air."),
                "live_vazio": "No stream confirmed right now.",
                "h_maislinks": "More links",
                "h_fotos": "Current episode photos (USGS)",
                "h_galeria": "Previous episodes, one photo each",
                "galeria_nota": ("Episodes without their own photo article in the USGS "
                                 "chronology are not listed here."),
                "fotos_credito": "Photos: USGS / Hawaiian Volcano Observatory, public domain.",
                "fotos_vazio": "No photos available right now.",
                "h_hist": "Alert changes recorded by this monitor",
                "hist_empty": "No changes recorded yet",
                "hist_nota": "History times are Hawaii time (HST)",
                "fl1": "Erupting right now?",
                "fl2": "National park: can I visit?",
                "fl3": "Current eruption",
                "fl4": "Latest episode",
                "fl5": "Next episode (HVO forecast)",
                "rodape": (f"Checked every 5 minutes. Last check: {fmt_hora(agora_utc, 'en')}. "
                           "Data: USGS Hawaiian Volcano Observatory (public domain). This site is not official."),
            },
            "html": {"live": live_en, "fonte": fonte_en, "aviso": aviso_en,
                     "fv1": f1_en, "fv2": f2_en, "fv3": f3_en,
                     "fv4": f4_en, "fv5": f5_en,
                     "alertas": alertas_html_en, "alertas_fonte": alertas_fonte_en,
                     "mapa_fonte": mapa_fonte_en},
        },
    }
    for k, v in caps.items():
        i18n["pt"]["text"][k] = v["pt"]
        i18n["en"]["text"][k] = v["en"]
    for k, v in gcaps.items():
        i18n["pt"]["text"][k] = v["pt"]
        i18n["en"]["text"][k] = v["en"]
    for k, v in lcaps.items():
        i18n["pt"]["text"][k] = v["pt"]
        i18n["en"]["text"][k] = v["en"]

    js = """
let curLang = 'pt';
const I18N = __I18N__;
function setLang(l) {
  try { localStorage.setItem('kilauea_lang', l); } catch (e) {}
  document.documentElement.lang = (l === 'pt') ? 'pt-BR' : 'en';
  document.title = I18N[l].title;
  curLang = l;
  try { tick(); } catch (e) {}
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
  if (t === 'mapa') {
    initMapa();
    if (mapa) setTimeout(() => mapa.invalidateSize(), 60);
  }
  try { sessionStorage.setItem('kilauea_tab', t); } catch (e) {}
}

// --- mapa dos avisos do parque e estacionamentos (Leaflet, criado ao abrir a aba)
// (declarado ANTES do setTab inicial: se a aba salva for 'mapa', initMapa ja roda aqui)
const MAPA_DADOS = __MAPA__;
const CORES_CAT = { danger: '#ff4a2e', caution: '#e0a400', closure: '#8f9bb0', info: '#4aa3ff' };
const CAT_NOME = {
  pt: { danger: 'Perigo', caution: 'Atenção', closure: 'Fechamento', info: 'Informação' },
  en: { danger: 'Danger', caution: 'Caution', closure: 'Closure', info: 'Info' }
};
let mapa = null;
function escT(s) { const e = document.createElement('span'); e.textContent = s || ''; return e.innerHTML; }
function popAlerta(a) {
  const pt = curLang === 'pt';
  const g = 'https://www.google.com/maps/search/?api=1&query=' + a.lat + ',' + a.lng;
  let h = '<div class="pop"><p><span class="cat cat-' + a.cat + '">' + CAT_NOME[curLang][a.cat] +
          '</span> <strong>' + escT(pt ? a.t_pt : a.t) + '</strong></p>' +
          '<p>' + escT(pt ? a.d_pt : a.d) + '</p>';
  const loc = pt ? a.l_pt : a.l;
  if (loc) h += '<p class="pop-loc">' + escT(loc) + '</p>';
  h += '<p><a href="' + g + '" target="_blank" rel="noopener">Google Maps</a>';
  if (a.url) h += ' &middot; <a href="' + a.url + '" target="_blank" rel="noopener">' +
                  (pt ? 'Detalhes' : 'Details') + '</a>';
  return h + '</p></div>';
}
function popEstac(p) {
  const pt = curLang === 'pt';
  const g = 'https://www.google.com/maps/dir/?api=1&destination=' + p.lat + ',' + p.lng;
  let h = '<div class="pop"><p><span class="cat cat-estac">P</span> <strong>' + escT(p.n) + '</strong></p>';
  if (p.v) {
    h += '<p>' + p.v + (pt ? ' vagas' : ' stalls');
    if (p.o) h += pt ? (', ' + p.o + ' para veículos grandes') : (', ' + p.o + ' oversized');
    h += '</p>';
  }
  const obs = pt ? p.obs_pt : p.obs;
  if (obs) h += '<p class="pop-loc">' + escT(obs) + '</p>';
  if (p.hilo) h += '<p class="pop-loc">' + (pt
    ? 'De carro: Hilo ~' + p.hilo + ', Kona ~' + p.kona
    : 'By car: Hilo ~' + p.hilo + ', Kona ~' + p.kona) + '</p>';
  return h + '<p><a href="' + g + '" target="_blank" rel="noopener">' +
         (pt ? 'Como chegar (Google Maps)' : 'Directions (Google Maps)') + '</a></p></div>';
}
function popMirante(m) {
  const pt = curLang === 'pt';
  const g = 'https://www.google.com/maps/search/?api=1&query=' + m.lat + ',' + m.lng;
  let h = '<div class="pop"><p><span class="cat cat-mirante">&#9733;</span> <strong>' +
          escT(m.n) + '</strong></p>' +
          '<p class="pop-loc">' + (pt ? 'Mirante oficial da erupção (NPS)' : 'Official eruption viewpoint (NPS)') + '</p>' +
          '<p>' + escT(pt ? m.d_pt : m.d) + '</p>';
  return h + '<p><a href="' + g + '" target="_blank" rel="noopener">Google Maps</a> &middot; ' +
         '<a href="' + m.url + '" target="_blank" rel="noopener">' +
         (pt ? 'Detalhes' : 'Details') + '</a></p></div>';
}
function popErupcao(E) {
  const pt = curLang === 'pt';
  const g = 'https://www.google.com/maps/search/?api=1&query=' + E.lat + ',' + E.lng;
  return '<div class="pop"><p><span class="cat cat-erup">&#9650;</span> <strong>' +
         escT(pt ? E.t_pt : E.t) + '</strong></p><p>' + escT(pt ? E.d_pt : E.d) + '</p>' +
         '<p><a href="' + g + '" target="_blank" rel="noopener">Google Maps</a></p></div>';
}
function popCamera(c) {
  const pt = curLang === 'pt';
  let h = '<div class="pop"><p><span class="cat cat-cam">&#9679;</span> <strong>USGS ' +
          escT(c.n) + '</strong></p><p>' + escT(pt ? c.d_pt : c.d) + '</p>' +
          '<p class="pop-loc">' + (pt
            ? 'Posição aproximada: o USGS informa só o setor da borda. A câmera é '
              + 'pan-tilt-zoom, então o enquadramento muda conforme a atividade.'
            : 'Approximate position: USGS only states the rim sector. It is a '
              + 'pan-tilt-zoom camera, so the framing changes with activity.') + '</p>';
  if (c.ativa) h += '<p><a href="#" onclick="return verLive()">' +
                    (pt ? 'Ver esta transmissão ao vivo' : 'Watch this stream live') + '</a></p>';
  return h + '</div>';
}
// funcao propria: evita aspas aninhadas dentro do onclick (ja quebrou o script uma vez)
function verLive() {
  setTab('live');
  const p = document.querySelector('[data-pane="live"]');
  if (p) p.scrollIntoView();
  return false;
}
function initMapa() {
  if (mapa || typeof L === 'undefined') return;
  const el = document.getElementById('mapa');
  if (!el) return;
  mapa = L.map('mapa', { scrollWheelZoom: false });
  const sat = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    { attribution: 'Esri, Maxar, Earthstar Geographics', maxZoom: 18 });
  const ruas = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    { attribution: '&copy; OpenStreetMap', maxZoom: 19 });
  sat.addTo(mapa);
  L.control.layers({ 'Satélite': sat, 'Mapa': ruas }).addTo(mapa);
  const bounds = [];
  for (const m of MAPA_DADOS.mirantes || []) {
    L.marker([m.lat, m.lng], { icon: L.divIcon({ className: 'mv-ico', html: '&#9733;', iconSize: [24, 24], iconAnchor: [12, 12] }), zIndexOffset: 500 })
      .addTo(mapa).bindPopup(() => popMirante(m));
    bounds.push([m.lat, m.lng]);
  }
  for (const p of MAPA_DADOS.estac) {
    L.marker([p.lat, p.lng], { icon: L.divIcon({ className: 'pk-ico', html: 'P', iconSize: [22, 22], iconAnchor: [11, 11] }) })
      .addTo(mapa).bindPopup(() => popEstac(p));
    if (!p.longe) bounds.push([p.lat, p.lng]);
  }
  for (const a of MAPA_DADOS.alertas) {
    L.circleMarker([a.lat, a.lng], { radius: 9, color: '#fff', weight: 2,
      fillColor: CORES_CAT[a.cat] || CORES_CAT.info, fillOpacity: .95 })
      .addTo(mapa).bindPopup(() => popAlerta(a));
    if (!a.longe) bounds.push([a.lat, a.lng]);
  }
  // A fonte da erupcao entra por ULTIMO para ficar por cima de tudo: sem isso
  // o mapa mostra so avisos e estacionamentos e ninguem descobre de onde sai a lava.
  const E = MAPA_DADOS.erupcao;
  if (E) {
    L.circle([E.blat, E.blng], { radius: E.raio, color: '#ff7043', weight: 2,
      dashArray: '7 7', fillColor: '#ff5722', fillOpacity: .25 })
      .addTo(mapa).bindPopup(() => popErupcao(E));
    L.marker([E.lat, E.lng], { zIndexOffset: 1000, icon: L.divIcon({
      className: 'er-ico', html: '&#9650;', iconSize: [30, 30], iconAnchor: [15, 15] }) })
      .addTo(mapa).bindPopup(() => popErupcao(E));
    bounds.push([E.lat, E.lng], [E.blat, E.blng]);
    // cada camera do USGS e a linha ate as bocas (direcao geral do olhar)
    for (const c of MAPA_DADOS.cameras || []) {
      L.polyline([[c.lat, c.lng], [E.blat, E.blng]], { color: '#4fc3f7', weight: 2,
        opacity: c.ativa ? .75 : .35, dashArray: '4 8' }).addTo(mapa);
      L.marker([c.lat, c.lng], { zIndexOffset: 800, icon: L.divIcon({
        className: 'cam-ico' + (c.ativa ? '' : ' cam-off'), html: c.n,
        iconSize: [46, 22], iconAnchor: [23, 11] }) })
        .addTo(mapa).bindPopup(() => popCamera(c));
      bounds.push([c.lat, c.lng]);
    }
  }
  // o container pode estar sem tamanho no primeiro load (aba salva = mapa,
  // janela oculta...): espera ter largura real antes do fitBounds, senao
  // o enquadramento trava no zoom maximo
  const ajusta = () => {
    mapa.invalidateSize();
    if (!mapa.getSize().x) { setTimeout(ajusta, 300); return; }
    if (bounds.length) mapa.fitBounds(bounds, { padding: [30, 30] });
    else mapa.setView([19.4157, -155.2753], 12);
  };
  ajusta();
}
function vaiMapa(o) {
  if (!mapa) return;
  if (o === 'cume') mapa.flyTo([19.4140, -155.2700], 14);
  else if (o === 'coc') mapa.flyTo([19.2950, -155.0986], 14);
  else if (o === 'kahuku') mapa.flyTo([19.0690, -155.6778], 12);
}

let lang = 'pt';
try { lang = localStorage.getItem('kilauea_lang') || 'pt'; } catch (e) {}
setLang(lang);
let aba = 'status';
try { aba = sessionStorage.getItem('kilauea_tab') || 'status'; } catch (e) {}
setTab(aba);

// --- lightbox: clique na foto abre em tamanho grande (variante full_width do S3)
const LB = document.getElementById('lightbox');
const lbImg = LB.querySelector('img');
const lbCap = LB.querySelector('.lb-cap');
let lbLista = [], lbIdx = 0;
function lbAbre(i) {
  lbLista = [...document.querySelectorAll('.grid figure img')];
  if (!lbLista.length) return;
  lbIdx = (i + lbLista.length) % lbLista.length;
  const el = lbLista[lbIdx];
  lbImg.onerror = () => { lbImg.onerror = null; lbImg.src = el.src; };
  lbImg.src = el.src.replace('half_width', 'full_width');
  lbImg.alt = el.alt;
  const fc = el.closest('figure').querySelector('figcaption');
  lbCap.textContent = fc ? fc.textContent : '';
  LB.classList.add('on');
}
function lbFecha() { LB.classList.remove('on'); lbImg.removeAttribute('src'); }
document.addEventListener('click', e => {
  const img = e.target.closest('.grid figure img');
  if (img) {
    lbLista = [...document.querySelectorAll('.grid figure img')];
    lbAbre(lbLista.indexOf(img));
  }
});
LB.addEventListener('click', e => {
  if (e.target.classList.contains('lb-prev')) { lbAbre(lbIdx - 1); return; }
  if (e.target.classList.contains('lb-next')) { lbAbre(lbIdx + 1); return; }
  if (e.target !== lbImg) lbFecha();
});
document.addEventListener('keydown', e => {
  if (!LB.classList.contains('on')) return;
  if (e.key === 'Escape') lbFecha();
  else if (e.key === 'ArrowLeft') lbAbre(lbIdx - 1);
  else if (e.key === 'ArrowRight') lbAbre(lbIdx + 1);
});

// --- relogios ao vivo (HST e Brasilia) com dia da semana
function tick() {
  const agora = new Date();
  const loc = curLang === 'pt' ? 'pt-BR' : 'en-US';
  for (const [tz, id] of [['Pacific/Honolulu', 'hst'], ['America/Sao_Paulo', 'brt']]) {
    const h = new Intl.DateTimeFormat(loc, { timeZone: tz, hour: '2-digit', minute: '2-digit',
                                             second: '2-digit', hour12: false }).format(agora);
    const d = new Intl.DateTimeFormat(loc, { timeZone: tz, weekday: 'long', day: 'numeric',
                                             month: 'long', year: 'numeric' }).format(agora);
    document.getElementById('rh-' + id).textContent = h;
    document.getElementById('rd-' + id).textContent = d;
  }
}
setInterval(tick, 1000);
tick();

// --- modo claro / escuro (escuro e o padrao; escolha fica no navegador)
function aplicaTema(tm) {
  if (tm === 'light') document.documentElement.setAttribute('data-theme', 'light');
  else document.documentElement.removeAttribute('data-theme');
  try { localStorage.setItem('kilauea_tema', tm); } catch (e) {}
}
function alternaTema() {
  aplicaTema(document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light');
}
let tema = 'dark';
try { tema = localStorage.getItem('kilauea_tema') || 'dark'; } catch (e) {}
aplicaTema(tema);
""".replace("__I18N__", json.dumps(i18n, ensure_ascii=False).replace("</", "<\\/")) \
   .replace("__MAPA__", json.dumps(mapa_dados, ensure_ascii=False).replace("</", "<\\/"))

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="300">
<title>Live Kilauea</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%F0%9F%8C%8B%3C/text%3E%3C/svg%3E">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root {{
  --bg: #14110d; --texto: #e9e2d9; --card: #201b15; --borda: #2c251d;
  --mudo: #8d8073; --rotulo: #a39482; --sub: #bdafa0; --link: #ffab72; --marca: #ffb27d;
  --topo-a: #211a13; --topo-b: #14110d; --vidro: rgba(20,17,13,.92);
  --caixa-rel: rgba(255,255,255,.05); --caixa-rel-borda: rgba(255,255,255,.12);
  --r-data: #c9bba9; --sombra-img: rgba(0,0,0,.45);
}}
[data-theme="light"] {{
  --bg: #f7f3ee; --texto: #2b2622; --card: #fffdfa; --borda: #e7ded2;
  --mudo: #98897a; --rotulo: #8a7b6c; --sub: #6b6157; --link: #b3541e; --marca: #b3541e;
  --topo-a: #fbf7f1; --topo-b: #f3ede4; --vidro: rgba(251,247,241,.92);
  --caixa-rel: rgba(0,0,0,.04); --caixa-rel-borda: rgba(0,0,0,.14);
  --r-data: #6b6157; --sombra-img: rgba(60,40,20,.18);
}}
body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0;
        background: var(--bg); color: var(--texto); transition: background .3s, color .3s; }}
.topo {{ background: linear-gradient(180deg, var(--topo-a), var(--topo-b)); border-top: 4px solid {fundo};
         padding: 14px 16px 20px; text-align: center; }}
.topo-linha {{ display: flex; justify-content: space-between; align-items: center;
               max-width: 820px; margin: 0 auto; }}
.brand {{ font-weight: 800; letter-spacing: 4px; font-size: .92em; color: var(--marca); }}
.langs {{ line-height: 0; display: flex; align-items: center; }}
.flag, .tema-btn {{ background: none; border: 1px solid var(--caixa-rel-borda); border-radius: 4px;
         padding: 2px 3px; margin-left: 6px; cursor: pointer; line-height: 0; opacity: .55; }}
.flag.active {{ opacity: 1; border-color: var(--marca); }}
.tema-btn {{ opacity: .8; color: var(--marca); }}
.flag svg, .tema-btn svg {{ display: block; }}
html[data-theme="light"] .ic-sol {{ display: none; }}
html:not([data-theme="light"]) .ic-lua {{ display: none; }}
.relogios {{ display: flex; gap: 12px; justify-content: center; margin: 18px auto 6px; max-width: 540px; }}
.relogio {{ flex: 1; background: var(--caixa-rel); border: 1px solid var(--caixa-rel-borda);
            border-radius: 12px; padding: 10px 8px 12px; }}
.r-label {{ font-size: .7em; text-transform: uppercase; letter-spacing: 1.6px; color: var(--rotulo); }}
.r-hora {{ font-size: 1.6em; font-weight: 700; font-variant-numeric: tabular-nums; margin: 3px 0 1px; }}
.r-data {{ font-size: .8em; color: var(--r-data); }}
.badge {{ display: inline-block; background: {fundo}; color: #fff; margin: 18px 0 8px; padding: 10px 30px;
          border-radius: 999px; font-size: 1.4em; letter-spacing: .3px; box-shadow: 0 0 28px {fundo}55; }}
.sub {{ margin: 3px 0; color: var(--sub); font-size: .92em; }}
.atualizacao {{ font-size: .8em; color: var(--mudo); margin-top: 7px; }}
.tabs {{ display: flex; justify-content: center; gap: 8px; padding: 10px; position: sticky; top: 0; z-index: 5;
         background: var(--vidro); -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px);
         border-bottom: 1px solid var(--borda); }}
.tab-btn {{ background: none; border: 0; border-radius: 999px; font-size: 1em;
            padding: 8px 20px; cursor: pointer; color: var(--rotulo); }}
.tab-btn.on {{ background: {fundo}; color: #fff; font-weight: 600; }}
.wrap {{ max-width: 780px; margin: 0 auto; padding: 18px 16px 26px; }}
.pane {{ display: none; }}
.pane.on {{ display: block; }}
.facts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(290px, 1fr)); gap: 12px; margin: 4px 0 18px; }}
.fact {{ background: var(--card); border: 1px solid var(--borda); border-left: 4px solid {fundo};
         border-radius: 14px; padding: 13px 15px; }}
.fact-wide {{ grid-column: 1 / -1; }}
.fact-wide .f-val {{ font-weight: 400; }}
.fact-wide .f-val a {{ font-weight: 600; }}
.f-label {{ font-size: .74em; text-transform: uppercase; letter-spacing: .6px; color: var(--mudo); }}
.f-val {{ margin-top: 3px; font-size: .98em; font-weight: 600; line-height: 1.4; }}
.f-val a {{ font-weight: 400; }}
.dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 7px; }}
.dot-live {{ background: #ff4a2e; box-shadow: 0 0 0 3px rgba(255,74,46,.25); }}
.dot-pause {{ background: #e0a400; box-shadow: 0 0 0 3px rgba(224,164,0,.22); }}
.dot-off {{ background: #37b45c; box-shadow: 0 0 0 3px rgba(55,180,92,.22); }}
.card {{ background: var(--card); border: 1px solid var(--borda); border-radius: 14px;
         padding: 18px 20px; margin: 14px 0; }}
.card h2 {{ margin: 0 0 10px; font-size: 1em; color: var(--rotulo); text-transform: uppercase;
            letter-spacing: .6px; font-weight: 600; }}
.card p {{ line-height: 1.6; }}
table {{ border-collapse: collapse; width: 100%; }}
td {{ padding: 7px 8px; border-bottom: 1px solid var(--borda); font-size: .95em; }}
a {{ color: var(--link); }}
.mono {{ font-size: .85em; color: var(--mudo); }}
.video {{ position: relative; padding-top: 56.25%; margin: 6px 0 20px; }}
.video iframe {{ position: absolute; inset: 0; width: 100%; height: 100%; border: 0; border-radius: 12px;
                 box-shadow: 0 4px 16px var(--sombra-img); }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }}
figure {{ margin: 0; }}
figure img {{ width: 100%; border-radius: 10px; display: block; box-shadow: 0 3px 12px var(--sombra-img);
              cursor: zoom-in; }}
figcaption {{ margin-top: 5px; }}
.lightbox {{ position: fixed; inset: 0; background: rgba(8,6,4,.95); display: none;
             flex-direction: column; align-items: center; justify-content: center; z-index: 50; }}
.lightbox.on {{ display: flex; }}
.lightbox img {{ max-width: 94vw; max-height: 84vh; border-radius: 8px;
                 box-shadow: 0 6px 40px rgba(0,0,0,.7); cursor: zoom-out; }}
.lb-cap {{ color: #eadfd3; margin-top: 12px; font-size: .95em; text-align: center;
           padding: 0 20px; max-width: 90vw; }}
.lb-btn {{ position: absolute; top: 50%; transform: translateY(-50%); border: 0; cursor: pointer;
           background: rgba(255,255,255,.14); color: #fff; font-size: 1.7em; line-height: 1;
           width: 48px; height: 48px; border-radius: 50%; }}
.lb-btn:hover {{ background: rgba(255,255,255,.28); }}
.lb-prev {{ left: 14px; }}
.lb-next {{ right: 14px; }}
.lb-x {{ position: absolute; top: 10px; right: 16px; background: none; border: 0; color: #fff;
         font-size: 2em; cursor: pointer; opacity: .8; }}
.cat {{ display: inline-block; color: #fff; border-radius: 5px; font-size: .72em; font-weight: 700;
        padding: 2px 8px; text-transform: uppercase; letter-spacing: .5px; margin-right: 6px;
        vertical-align: 1px; }}
.cat-danger {{ background: #c0392b; }}
.cat-caution {{ background: #b8860b; }}
.cat-closure {{ background: #6b7686; }}
.cat-info {{ background: #3a7bbf; }}
.cat-estac {{ background: #2e6fdb; border-radius: 50%; padding: 2px 7px; }}
.alerta {{ border-bottom: 1px solid var(--borda); padding: 4px 0 10px; }}
.alerta:last-child {{ border-bottom: 0; padding-bottom: 0; }}
.alerta p {{ margin: 6px 0; line-height: 1.5; }}
#mapa {{ height: 62vh; min-height: 380px; border-radius: 12px; z-index: 1;
         box-shadow: 0 3px 12px var(--sombra-img); }}
.map-atalhos {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 10px; }}
.map-atalhos button, .map-atalhos a {{ background: var(--caixa-rel); border: 1px solid var(--caixa-rel-borda);
         color: var(--texto); border-radius: 999px; padding: 6px 14px; font-size: .85em;
         cursor: pointer; text-decoration: none; }}
.map-atalhos a {{ color: var(--link); border-color: var(--link); }}
.legenda {{ display: flex; flex-wrap: wrap; gap: 14px; margin-top: 10px; font-size: .85em; color: var(--mudo); }}
.legenda span {{ display: inline-flex; align-items: center; gap: 6px; }}
.ldot {{ width: 12px; height: 12px; border-radius: 50%; border: 2px solid #fff;
         box-shadow: 0 0 3px rgba(0,0,0,.4); display: inline-block; }}
.pk-ico {{ background: #2e6fdb; color: #fff; border-radius: 50%; border: 2px solid #fff;
           font: 700 12px/18px -apple-system, Segoe UI, sans-serif; text-align: center;
           box-shadow: 0 1px 4px rgba(0,0,0,.5); }}
.mv-ico {{ background: #8e44ad; color: #ffd76a; border-radius: 50%; border: 2px solid #fff;
           font: 700 14px/20px -apple-system, Segoe UI, sans-serif; text-align: center;
           box-shadow: 0 1px 4px rgba(0,0,0,.5); }}
.cat-mirante {{ background: #8e44ad; }}
.cat-erup {{ background: #ff5722; border-radius: 50%; padding: 2px 7px; }}
.cat-cam {{ background: #0288d1; border-radius: 50%; padding: 2px 7px; }}
.cam-ico {{ background: #0288d1; color: #fff; border: 2px solid #fff; border-radius: 11px;
            text-align: center; font-size: 11px; line-height: 18px; font-weight: 700;
            letter-spacing: .3px; box-shadow: 0 2px 6px rgba(0,0,0,.5); }}
.cam-ico.cam-off {{ background: #62727b; opacity: .75; }}
.ldot-cam {{ background: #0288d1; }}
.er-ico {{ background: #ff5722; color: #fff; border-radius: 50%; border: 3px solid #fff;
           text-align: center; font-size: 15px; line-height: 24px; font-weight: 700;
           box-shadow: 0 0 0 4px rgba(255,87,34,.35), 0 2px 8px rgba(0,0,0,.5); }}
.ldot-erup {{ background: #ff5722; color: #fff; text-align: center; font-size: 9px;
              line-height: 12px; font-style: normal; }}
.pop p {{ margin: 5px 0; }}
.pop-loc {{ color: #666; font-size: .85em; }}
.leaflet-popup-content {{ font-size: .95em; line-height: 1.45; }}
</style>
</head>
<body>
<header class="topo">
<div class="topo-linha">
<div class="brand">LIVE KILAUEA</div>
<div class="langs">
<button class="tema-btn" aria-label="Tema claro ou escuro" onclick="alternaTema()"><svg class="ic-sol" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1"/></svg><svg class="ic-lua" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/></svg></button>
<button class="flag" data-lang="en" title="English" aria-label="English" onclick="setLang('en')">{FLAG_HI}</button>
<button class="flag active" data-lang="pt" title="Portugues" aria-label="Portugues" onclick="setLang('pt')">{FLAG_BR}</button>
</div>
</div>
<div class="relogios">
<div class="relogio"><div class="r-label" data-i18n="rel_hi"></div><div class="r-hora" id="rh-hst">--:--</div><div class="r-data" id="rd-hst"></div></div>
<div class="relogio"><div class="r-label" data-i18n="rel_br"></div><div class="r-hora" id="rh-brt">--:--</div><div class="r-data" id="rd-brt"></div></div>
</div>
<h1 class="badge" data-i18n="status"></h1>
<p class="sub" data-i18n="linha_codigo"></p>
<p class="sub" data-i18n="linha_aviso"></p>
<p class="sub atualizacao" data-i18n="linha_atualizacao"></p>
</header>
<div class="tabs">
<button class="tab-btn on" data-tab="status" data-i18n="tab_status" onclick="setTab('status')"></button>
<button class="tab-btn" data-tab="live" data-i18n="tab_live" onclick="setTab('live')"></button>
<button class="tab-btn" data-tab="fotos" data-i18n="tab_fotos" onclick="setTab('fotos')"></button>
<button class="tab-btn" data-tab="mapa" data-i18n="tab_mapa" onclick="setTab('mapa')"></button>
</div>
<div class="wrap">

<div class="pane on" data-pane="status">
<div class="facts">
<div class="fact"><div class="f-label" data-i18n="fl1"></div><div class="f-val" data-i18n-html="fv1"></div></div>
<div class="fact"><div class="f-label" data-i18n="fl3"></div><div class="f-val" data-i18n-html="fv3"></div></div>
<div class="fact fact-wide"><div class="f-label" data-i18n="fl2"></div><div class="f-val" data-i18n-html="fv2"></div></div>
<div class="fact"><div class="f-label" data-i18n="fl4"></div><div class="f-val" data-i18n-html="fv4"></div></div>
<div class="fact"><div class="f-label" data-i18n="fl5"></div><div class="f-val" data-i18n-html="fv5"></div></div>
</div>
<div class="card"><h2 data-i18n="h_aviso"></h2><div data-i18n-html="aviso"></div>
<p class="mono" data-i18n-html="fonte"></p></div>
<div class="card"><h2 data-i18n="h_alertas"></h2><div data-i18n-html="alertas"></div>
<p class="mono" data-i18n-html="alertas_fonte"></p></div>
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
<div class="card"><h2 data-i18n="h_galeria"></h2>
<div class="grid">{galeria_html}</div>
<p class="mono" data-i18n="galeria_nota"></p></div>
</div>

<div class="pane" data-pane="mapa">
<div class="card"><h2 data-i18n="h_mapa"></h2>
<div class="map-atalhos">
<button onclick="vaiMapa('cume')" data-i18n="mp_cume"></button>
<button onclick="vaiMapa('coc')" data-i18n="mp_coc"></button>
<button onclick="vaiMapa('kahuku')" data-i18n="mp_kahuku"></button>
<a href="https://www.google.com/maps/search/?api=1&amp;query=Hawai%CA%BBi+Volcanoes+National+Park" target="_blank" rel="noopener" data-i18n="mp_gmaps"></a>
</div>
<div id="mapa"></div>
<div class="legenda">
<span><i class="ldot ldot-erup">&#9650;</i><span data-i18n="leg_erup"></span></span>
<span><i class="ldot ldot-cam"></i><span data-i18n="leg_cam"></span></span>
<span><i class="ldot" style="background:#8e44ad"></i><span data-i18n="leg_mirante"></span></span>
<span><i class="ldot" style="background:#ff4a2e"></i><span data-i18n="leg_danger"></span></span>
<span><i class="ldot" style="background:#e0a400"></i><span data-i18n="leg_caution"></span></span>
<span><i class="ldot" style="background:#8f9bb0"></i><span data-i18n="leg_closure"></span></span>
<span><i class="ldot" style="background:#2e6fdb"></i><span data-i18n="leg_estac"></span></span>
</div>
<p class="mono" data-i18n-html="mapa_fonte"></p></div>
</div>

<p class="mono" data-i18n="rodape"></p>
</div>
<div class="lightbox" id="lightbox">
<button class="lb-x" aria-label="Fechar">&times;</button>
<button class="lb-btn lb-prev" aria-label="Anterior">&#8249;</button>
<img alt="">
<div class="lb-cap"></div>
<button class="lb-btn lb-next" aria-label="Proxima">&#8250;</button>
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

    # ultimo episodio: procura no aviso INTEIRO (sinopse + resumo) e persiste,
    # porque avisos mais velhos deixam de citar as datas
    texto_aviso = sinopse + " " + re.sub(r"<[^>]+>", " ", resumo_html or "")
    ano_aviso = (atual.get("sent_utc") or "2026")[:4]
    info_ep = extrai_ultimo_ep(texto_aviso, ano_aviso)
    if info_ep and info_ep.get("ep"):
        antigo = midia.get("ultimo_ep") or {}
        if info_ep["ep"] > antigo.get("ep", 0):
            midia["ultimo_ep"] = info_ep
        elif info_ep["ep"] == antigo.get("ep"):
            midia["ultimo_ep"] = {**antigo, **info_ep}
    print(f"ultimo episodio: {midia.get('ultimo_ep') or 'desconhecido'}")

    primeira_vez = not prev
    if primeira_vez:
        notifica(
            "Monitor do Kilauea ativado",
            f"Estado atual: {atual['color_code']}/{atual['alert_level']}.\n\n"
            f"{sinopse}"[:800],
            "low", "white_check_mark",
        )
    else:
        decisao = decide_push(prev, atual, sinopse)
        if decisao:
            titulo, corpo, prio, tags = decisao
            notifica(titulo, corpo[:1500], prio, tags, click=LINK_WEBCAMS)
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

    # avisos ativos do parque nacional (fechamentos, perigos, atencao)
    cache_alertas = {}
    if ALERTAS_CACHE.exists():
        try:
            cache_alertas = json.loads(ALERTAS_CACHE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            cache_alertas = {}
    alertas_api = alertas_nps(cache_alertas)
    ALERTAS_CACHE.write_text(
        json.dumps({"alertas": alertas_api}, ensure_ascii=False, indent=2), encoding="utf-8")
    alertas = alertas_api + AVISOS_FIXOS
    print(f"alertas do parque: {len(alertas_api)} da API + {len(AVISOS_FIXOS)} fixos "
          f"({[a['cat'] for a in alertas]})")

    # galeria dos episodios anteriores (backfill + episodios novos conforme saem)
    galeria = []
    if GALERIA_FILE.exists():
        try:
            galeria = json.loads(GALERIA_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            galeria = []
    if fotos.get("ep") and fotos.get("itens"):
        conhecidos = {g["ep"] for g in galeria}
        if fotos["ep"] not in conhecidos:
            galeria.append({"ep": fotos["ep"], "data": fotos.get("data", ""),
                            "src": fotos["itens"][0]["src"],
                            "cap_en": fotos["itens"][0].get("cap_en", ""),
                            "slug": fotos.get("slug", "")})
            galeria.sort(key=lambda g: -g["ep"])
            print(f"galeria: episodio {fotos['ep']} adicionado")
    GALERIA_FILE.write_text(json.dumps(galeria, ensure_ascii=False, indent=2),
                            encoding="utf-8")

    STATE_FILE.write_text(json.dumps(atual, indent=2), encoding="utf-8")
    HISTORY_FILE.write_text(json.dumps(historico, indent=2), encoding="utf-8")
    MIDIA_CACHE.write_text(
        json.dumps({"lives": lives, "lives_link": lives_link, "fotos": fotos,
                    "ultimo_ep": midia.get("ultimo_ep")},
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
              "prev_en": prev_en, "prev_pt": _t(prev_en),
              "ult": midia.get("ultimo_ep") or {}}
    pagina = gera_pagina(atual, sinopse, resumo_html, historico, agora_utc,
                         aviso_pt, lives, lives_link, fotos, frases, galeria, alertas)
    upload_pa(pagina)
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
