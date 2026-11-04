"""Leitura da agenda (endereco secreto iCal do Google Agenda) e calculo do tempo livre.

Somente stdlib. Suporta o que o Google Agenda exporta no dia a dia:
DTSTART/DTEND com TZID, UTC ou data inteira; DURATION; RRULE (DAILY, WEEKLY,
MONTHLY, YEARLY com INTERVAL, COUNT, UNTIL, BYDAY, BYMONTHDAY); EXDATE;
RECURRENCE-ID (ocorrencias editadas); TRANSP:TRANSPARENT e STATUS:CANCELLED.
"""
import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from urllib.request import Request, urlopen

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/Sao_Paulo")
except Exception:  # noqa: BLE001  (python sem tzdata)
    ZoneInfo = None
    TZ = timezone(timedelta(hours=-3))

DIAS_SEMANA = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def _tz(nome):
    if nome and ZoneInfo is not None:
        try:
            return ZoneInfo(nome)
        except Exception:  # noqa: BLE001
            pass
    return TZ


def _linhas(texto):
    """Desdobra as linhas continuadas do iCal (RFC 5545 3.1)."""
    out = []
    for ln in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if ln[:1] in (" ", "\t") and out:
            out[-1] += ln[1:]
        else:
            out.append(ln)
    return out


def _prop(linha):
    """'DTSTART;TZID=America/Sao_Paulo:20261104T090000' -> (nome, params, valor)."""
    m = re.match(r"^([A-Za-z0-9-]+)((?:;[^:]*)?):(.*)$", linha)
    if not m:
        return None, {}, ""
    params = {}
    for p in m.group(2).split(";")[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.upper()] = v.strip('"')
    return m.group(1).upper(), params, m.group(3)


def _dt(valor, params):
    """Converte valor iCal em (datetime aware, dia_inteiro)."""
    valor = valor.strip()
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", valor):
        d = datetime.strptime(valor[:8], "%Y%m%d")
        return d.replace(tzinfo=TZ), True
    if valor.endswith("Z"):
        d = datetime.strptime(valor[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        return d.astimezone(TZ), False
    d = datetime.strptime(valor[:15], "%Y%m%dT%H%M%S")
    return d.replace(tzinfo=_tz(params.get("TZID"))).astimezone(TZ), False


def _duracao(valor):
    m = re.fullmatch(r"(-)?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", valor.strip())
    if not m:
        return timedelta(0)
    s, w, d, h, mi, se = m.groups()
    td = timedelta(weeks=int(w or 0), days=int(d or 0), hours=int(h or 0),
                   minutes=int(mi or 0), seconds=int(se or 0))
    return -td if s else td


def parse(texto):
    """Lista de eventos 'crus' (dicts) a partir do texto iCal."""
    eventos, atual = [], None
    for ln in _linhas(texto):
        if ln == "BEGIN:VEVENT":
            atual = {"exdates": []}
            continue
        if ln == "END:VEVENT":
            if atual is not None and "inicio" in atual:
                eventos.append(atual)
            atual = None
            continue
        if atual is None:
            continue
        nome, params, valor = _prop(ln)
        try:
            if nome == "DTSTART":
                atual["inicio"], atual["dia_inteiro"] = _dt(valor, params)
            elif nome == "DTEND":
                atual["fim"], _ = _dt(valor, params)
            elif nome == "DURATION":
                atual["duracao"] = _duracao(valor)
            elif nome == "RRULE":
                atual["rrule"] = dict(p.split("=", 1) for p in valor.split(";") if "=" in p)
            elif nome == "EXDATE":
                for v in valor.split(","):
                    atual["exdates"].append(_dt(v, params)[0])
            elif nome == "RECURRENCE-ID":
                atual["recid"], _ = _dt(valor, params)
            elif nome == "UID":
                atual["uid"] = valor
            elif nome == "SUMMARY":
                atual["titulo"] = valor.replace("\\,", ",").replace("\\;", ";").replace("\\n", " ")
            elif nome == "TRANSP":
                atual["livre"] = valor.strip().upper() == "TRANSPARENT"
            elif nome == "STATUS":
                atual["cancelado"] = valor.strip().upper() == "CANCELLED"
        except ValueError:
            continue
    for ev in eventos:
        if "fim" not in ev:
            ev["fim"] = ev["inicio"] + ev.get("duracao", timedelta(days=1) if ev["dia_inteiro"] else timedelta(0))
    return eventos


def _nth_weekday(ano, mes, wd, n):
    """n-esimo dia da semana wd (0=seg) do mes; n<0 conta do fim."""
    if n > 0:
        d = date(ano, mes, 1)
        d += timedelta(days=(wd - d.weekday()) % 7 + 7 * (n - 1))
        return d if d.month == mes else None
    prox = date(ano + (mes == 12), mes % 12 + 1, 1)
    d = prox - timedelta(days=1)
    d -= timedelta(days=(d.weekday() - wd) % 7 + 7 * (-n - 1))
    return d if d.month == mes else None


def _ocorrencias(ev, ini, fim):
    """Inicios das ocorrencias de ev que podem cair em [ini, fim)."""
    dt0 = ev["inicio"]
    rr = ev.get("rrule")
    if not rr:
        return [dt0]
    freq = rr.get("FREQ", "")
    intervalo = max(1, int(rr.get("INTERVAL", "1") or 1))
    count = int(rr["COUNT"]) if rr.get("COUNT", "").isdigit() else None
    until = None
    if rr.get("UNTIL"):
        try:
            until, inteiro = _dt(rr["UNTIL"], {})
            if inteiro:
                until += timedelta(days=1)
        except ValueError:
            until = None
    byday = [b for b in rr.get("BYDAY", "").split(",") if b]
    bymday = [int(x) for x in rr.get("BYMONTHDAY", "").split(",") if x.lstrip("-").isdigit()]
    hora = dt0.timetz()
    out, n = [], 0
    limite = fim if until is None else min(fim, until + timedelta(seconds=1))

    def junta(d):
        return datetime.combine(d, hora.replace(tzinfo=None)).replace(tzinfo=dt0.tzinfo)

    if freq == "DAILY":
        d = dt0
        while d < limite:
            n += 1
            if count and n > count:
                break
            if d + (ev["fim"] - ev["inicio"]) >= ini:
                out.append(d)
            d = junta(d.date() + timedelta(days=intervalo))
    elif freq == "WEEKLY":
        dias = sorted({DIAS_SEMANA.index(b[-2:]) for b in byday if b[-2:] in DIAS_SEMANA}) or [dt0.weekday()]
        semana = dt0.date() - timedelta(days=dt0.weekday())
        while True:
            parou = False
            for wd in dias:
                d = junta(semana + timedelta(days=wd))
                if d < dt0:
                    continue
                if d >= limite:
                    parou = True
                    break
                n += 1
                if count and n > count:
                    parou = True
                    break
                if d + (ev["fim"] - ev["inicio"]) >= ini:
                    out.append(d)
            if parou:
                break
            semana += timedelta(weeks=intervalo)
            if junta(semana) >= limite:
                break
    elif freq in ("MONTHLY", "YEARLY"):
        ano, mes = dt0.year, dt0.month
        passo = intervalo if freq == "MONTHLY" else 12 * intervalo
        for _ in range(2400):
            datas = []
            if freq == "YEARLY" and not byday and not bymday:
                mes = dt0.month
            if byday:
                for b in byday:
                    m = re.fullmatch(r"([+-]?\d+)?(MO|TU|WE|TH|FR|SA|SU)", b)
                    if m:
                        d = _nth_weekday(ano, mes, DIAS_SEMANA.index(m.group(2)), int(m.group(1) or 1))
                        if d:
                            datas.append(d)
            else:
                for md in (bymday or [dt0.day]):
                    try:
                        if md < 0:
                            prox = date(ano + (mes == 12), mes % 12 + 1, 1)
                            datas.append(prox + timedelta(days=md))
                        else:
                            datas.append(date(ano, mes, md))
                    except ValueError:
                        pass
            parou = False
            for d0 in sorted(datas):
                d = junta(d0)
                if d < dt0:
                    continue
                if d >= limite:
                    parou = True
                    break
                n += 1
                if count and n > count:
                    parou = True
                    break
                if d + (ev["fim"] - ev["inicio"]) >= ini:
                    out.append(d)
            if parou:
                break
            mes += passo
            while mes > 12:
                mes -= 12
                ano += 1
            if date(ano, mes, 1) > limite.date():
                break
    else:
        out = [dt0]
    return out


def expandir(eventos, ini, fim):
    """Ocorrencias concretas (inicio, fim, titulo, dia_inteiro) dentro de [ini, fim)."""
    editadas = {}
    for ev in eventos:
        if "recid" in ev:
            editadas[(ev.get("uid"), ev["recid"])] = ev
    out = []
    for ev in eventos:
        dur = ev["fim"] - ev["inicio"]
        if "recid" in ev:
            insts = [ev["inicio"]]
        else:
            ex = set(ev["exdates"])
            insts = [d for d in _ocorrencias(ev, ini, fim)
                     if d not in ex and (ev.get("uid"), d) not in editadas]
        if ev.get("cancelado") or ev.get("livre"):
            continue
        for d in insts:
            if d < fim and d + dur > ini:
                out.append({"inicio": d, "fim": d + dur, "titulo": ev.get("titulo", "(sem título)"),
                            "dia_inteiro": ev.get("dia_inteiro", False)})
    out.sort(key=lambda e: e["inicio"])
    return out


# ----------------------------------------------------------------------------
# Download com cache em disco

def baixar(url, pasta_cache, validade_s=1800):
    """Texto iCal da agenda (com cache). Retorna (texto|None, erro|None)."""
    if not url:
        return None, None
    cache = os.path.join(pasta_cache, "agenda_cache.json")
    try:
        with open(cache, encoding="utf-8") as f:
            c = json.load(f)
        if c.get("url") == url and time.time() - c.get("quando", 0) < validade_s:
            return c["texto"], None
    except Exception:  # noqa: BLE001
        c = None
    try:
        req = Request(url, headers={"User-Agent": "biblioteca-leituras/1.0"})
        with urlopen(req, timeout=20) as r:
            texto = r.read().decode("utf-8", "replace")
        if "BEGIN:VCALENDAR" not in texto:
            raise ValueError("o endereço não devolveu uma agenda iCal")
        tmp = cache + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"url": url, "quando": time.time(), "texto": texto}, f)
        os.replace(tmp, cache)
        return texto, None
    except Exception as e:  # noqa: BLE001
        # se a rede falhar, usa o cache antigo (mesmo vencido) em vez de nada
        if c and c.get("url") == url:
            return c["texto"], f"agenda não atualizada agora ({e}); usando a última cópia"
        return None, f"não consegui ler a agenda: {e}"


# ----------------------------------------------------------------------------
# Tempo livre do dia -> minutos de leitura sugeridos

def _hm(s, padrao):
    try:
        h, m = s.split(":")
        return int(h), int(m)
    except Exception:  # noqa: BLE001
        return padrao


def analisar_dia(dia, ocorrencias, cfg, agora=None):
    """Para um dia: compromissos, horas ocupadas, minutos sugeridos e horario sugerido."""
    h0, m0 = _hm(cfg.get("janela_inicio", "06:00"), (6, 0))
    h1, m1 = _hm(cfg.get("janela_fim", "23:00"), (23, 0))
    hp, mp = _hm(cfg.get("horario_preferido", "21:00"), (21, 0))
    jan_ini = datetime(dia.year, dia.month, dia.day, h0, m0, tzinfo=TZ)
    jan_fim = datetime(dia.year, dia.month, dia.day, h1, m1, tzinfo=TZ)
    preferido = datetime(dia.year, dia.month, dia.day, hp, mp, tzinfo=TZ)

    do_dia = [o for o in ocorrencias if o["inicio"] < jan_fim + timedelta(hours=1)
              and o["fim"] > jan_ini - timedelta(hours=1)]
    compromissos = [o for o in do_dia if not o["dia_inteiro"]]
    inteiros = [o for o in do_dia if o["dia_inteiro"]
                and o["inicio"].date() <= dia < o["fim"].date()]

    # intervalos ocupados dentro da janela (mesclados)
    ocup = sorted((max(o["inicio"], jan_ini), min(o["fim"], jan_fim)) for o in compromissos
                  if o["fim"] > jan_ini and o["inicio"] < jan_fim)
    mesclado = []
    for a, b in ocup:
        if mesclado and a <= mesclado[-1][1]:
            mesclado[-1] = (mesclado[-1][0], max(mesclado[-1][1], b))
        else:
            mesclado.append((a, b))
    ocupado_min = sum((b - a).total_seconds() for a, b in mesclado) / 60

    # quanto mais cheio o dia, menos leitura (sempre entre 15 e 60 min)
    if ocupado_min <= 60 * float(cfg.get("limite_60", 2)):
        minutos = 60
    elif ocupado_min <= 60 * float(cfg.get("limite_45", 4)):
        minutos = 45
    elif ocupado_min <= 60 * float(cfg.get("limite_30", 7)):
        minutos = 30
    else:
        minutos = 15

    # brechas livres (a partir de agora, se for hoje)
    comeco = jan_ini
    if agora is not None and agora.date() == dia:
        comeco = max(jan_ini, agora + timedelta(minutes=5))
        comeco = comeco.replace(second=0, microsecond=0)
        comeco += timedelta(minutes=(-comeco.minute) % 5)
    brechas, cursor = [], comeco
    for a, b in mesclado:
        if a > cursor:
            brechas.append((cursor, a))
        cursor = max(cursor, b)
    if jan_fim > cursor:
        brechas.append((cursor, jan_fim))
    brechas = [(a, b) for a, b in brechas if (b - a) >= timedelta(minutes=15)]

    maior = max(((b - a).total_seconds() / 60 for a, b in brechas), default=0)
    if brechas and maior < minutos:
        minutos = max(15, int(maior // 15) * 15)

    # horario: a brecha que comporta a leitura mais perto do horario preferido
    horario = None
    dur = timedelta(minutes=minutos)
    melhor = None
    for a, b in brechas:
        if b - a < dur:
            continue
        cand = min(max(preferido, a), b - dur)
        dist = abs((cand - preferido).total_seconds())
        if melhor is None or dist < melhor:
            melhor, horario = dist, cand

    return {
        "dia": dia,
        "compromissos": compromissos,
        "dia_inteiro": inteiros,
        "ocupado_min": int(ocupado_min),
        "minutos": minutos,
        "horario": horario,
        "sem_brecha": not brechas,
    }
