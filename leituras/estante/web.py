"""Site /biblioteca/: plano de leitura diario integrado com a agenda.

App WSGI puro (somente stdlib), montado dentro do web app ja existente no
PythonAnywhere por `montar(application, "/biblioteca")`.
"""
import base64
import hashlib
import hmac
import html
import os
import secrets
import sys
import time
import traceback
from datetime import date, datetime, timedelta, timezone
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, quote, urlencode

from . import agenda, catalogo, plano
from .agenda import TZ

SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
SEMANA_C = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]
MESES_C = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
TIPO_NOME = {"L": "Literatura e história", "P": "Ideias"}
COOKIE = "biblioteca_s"


def esc(s):
    return html.escape("" if s is None else str(s), quote=True)


def fdata(d, ano=True):
    if not d:
        return "—"
    return f"{d.day} {MESES_C[d.month - 1]}" + (f" {d.year}" if ano else "")


def fdata_longa(d):
    return f"{SEMANA[d.weekday()]}, {d.day} de {MESES[d.month - 1]}"


def fprazo(hoje, d):
    if not d:
        return "—"
    dias = (d - hoje).days
    if dias <= 0:
        return "hoje"
    if dias < 14:
        return f"{dias} dias"
    if dias < 60:
        return f"{round(dias / 7)} semanas"
    if dias < 730:
        return f"{round(dias / 30.4)} meses"
    return f"{dias / 365.25:.1f} anos".replace(".", ",")


def montar(app_original, prefixo="/biblioteca", pasta_dados=None):
    """Envolve o web app existente: tudo sob `prefixo` vai para a biblioteca."""
    if pasta_dados is None:
        pasta_dados = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dados")
    bib = App(pasta_dados)
    prefixo = prefixo.rstrip("/")

    def application(environ, start_response):
        caminho = environ.get("PATH_INFO", "") or "/"
        if caminho == prefixo or caminho.startswith(prefixo + "/"):
            environ = dict(environ)
            environ["SCRIPT_NAME"] = environ.get("SCRIPT_NAME", "").rstrip("/") + prefixo
            environ["PATH_INFO"] = caminho[len(prefixo):]
            return bib(environ, start_response)
        return app_original(environ, start_response)

    return application


# ----------------------------------------------------------------------------

class Req:
    def __init__(self, environ):
        self.environ = environ
        self.method = environ.get("REQUEST_METHOD", "GET").upper()
        self.base = environ.get("SCRIPT_NAME", "").rstrip("/")
        self.path = environ.get("PATH_INFO", "") or ""
        q = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True)
        self.query = {k: v[-1] for k, v in q.items()}
        self.form = {}
        if self.method == "POST":
            try:
                n = int(environ.get("CONTENT_LENGTH") or 0)
            except ValueError:
                n = 0
            corpo = environ["wsgi.input"].read(min(n, 1_000_000)).decode("utf-8", "replace") if n else ""
            self.form = {k: v[-1] for k, v in parse_qs(corpo, keep_blank_values=True).items()}
        self.cookies = {}
        if environ.get("HTTP_COOKIE"):
            c = SimpleCookie()
            try:
                c.load(environ["HTTP_COOKIE"])
                self.cookies = {k: m.value for k, m in c.items()}
            except Exception:  # noqa: BLE001
                pass

    def url(self, caminho="/", **params):
        u = self.base + caminho
        if params:
            u += "?" + urlencode({k: v for k, v in params.items() if v is not None})
        return u

    def absoluto(self, caminho):
        env = self.environ
        esquema = env.get("HTTP_X_FORWARDED_PROTO") or env.get("wsgi.url_scheme", "https")
        host = env.get("HTTP_HOST") or env.get("SERVER_NAME", "localhost")
        return f"{esquema}://{host}{self.base}{caminho}"


class Resp:
    def __init__(self, corpo="", status="200 OK", tipo="text/html; charset=utf-8", headers=None):
        self.corpo = corpo.encode("utf-8") if isinstance(corpo, str) else corpo
        self.status = status
        self.headers = [("Content-Type", tipo), ("Cache-Control", "no-store")] + (headers or [])


def redirecionar(url, headers=None):
    return Resp("", "303 See Other", headers=[("Location", url)] + (headers or []))


# ----------------------------------------------------------------------------

class App:
    def __init__(self, pasta_dados):
        self.pasta = pasta_dados

    def __call__(self, environ, start_response):
        try:
            req = Req(environ)
            resp = self.rotear(req)
        except Exception:  # noqa: BLE001
            traceback.print_exc(file=sys.stderr)
            resp = Resp("<h1>Erro interno</h1><p>Algo deu errado. Tente de novo.</p>",
                        "500 Internal Server Error")
        start_response(resp.status, resp.headers)
        return [resp.corpo]

    # --- autenticacao -------------------------------------------------------
    def _assinatura(self, est, exp):
        return hmac.new(est.d["segredo"].encode(), str(exp).encode(), hashlib.sha256).hexdigest()

    def logado(self, req, est):
        v = req.cookies.get(COOKIE, "")
        if "." not in v:
            return False
        exp, sig = v.split(".", 1)
        if not exp.isdigit() or int(exp) < time.time():
            return False
        return hmac.compare_digest(sig, self._assinatura(est, exp))

    def cookie_login(self, req, est):
        exp = int(time.time()) + 180 * 86400
        return ("Set-Cookie", f"{COOKIE}={exp}.{self._assinatura(est, exp)}; Path={req.base or '/'}; "
                              f"Max-Age={180 * 86400}; HttpOnly; Secure; SameSite=Lax")

    @staticmethod
    def _hash(senha, salt):
        return hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(salt), 200_000).hex()

    def definir_senha(self, est, senha):
        salt = secrets.token_hex(16)
        est.d["senha"] = {"salt": salt, "hash": self._hash(senha, salt)}

    def senha_ok(self, est, senha):
        s = est.d.get("senha")
        return bool(s) and hmac.compare_digest(self._hash(senha, s["salt"]), s["hash"])

    # --- roteamento ---------------------------------------------------------
    def rotear(self, req):
        est = plano.Estado(self.pasta)
        p = req.path.rstrip("/") or "/"

        if p == "/favicon.svg":
            return Resp(FAVICON_SVG, tipo="image/svg+xml", headers=[("Cache-Control", "public, max-age=604800")])
        if p == "/apple-touch-icon.png":
            return Resp(base64.b64decode(ICONE_180_PNG), tipo="image/png",
                        headers=[("Cache-Control", "public, max-age=604800")])
        if p == "/agenda.ics":
            if not hmac.compare_digest(req.query.get("k", ""), est.d["feed_token"]):
                return Resp("chave inválida", "403 Forbidden", "text/plain; charset=utf-8")
            return Resp(self.feed_ics(req, est), tipo="text/calendar; charset=utf-8")

        if not est.d.get("senha"):
            if p == "/setup" and req.method == "POST":
                s1, s2 = req.form.get("senha", ""), req.form.get("senha2", "")
                if len(s1) < 6 or s1 != s2:
                    return Resp(self.pagina_setup(req, "As senhas precisam ser iguais e ter 6+ caracteres."))
                self.definir_senha(est, s1)
                est.salvar()
                return redirecionar(req.url("/"), [self.cookie_login(req, est)])
            return Resp(self.pagina_setup(req))

        if p == "/login":
            if req.method == "POST":
                if self.senha_ok(est, req.form.get("senha", "")):
                    return redirecionar(req.url("/"), [self.cookie_login(req, est)])
                time.sleep(1)
                return Resp(self.pagina_login(req, "Senha incorreta."))
            return Resp(self.pagina_login(req))

        if not self.logado(req, est):
            return redirecionar(req.url("/login"))

        if p == "/sair":
            return redirecionar(req.url("/login"), [("Set-Cookie", f"{COOKIE}=; Path={req.base or '/'}; Max-Age=0")])

        rotas_get = {"/": self.pagina_hoje, "/livros": self.pagina_livros,
                     "/previsao": self.pagina_previsao, "/config": self.pagina_config}
        rotas_post = {"/registrar": self.post_registrar, "/dia": self.post_dia,
                      "/minutos": self.post_minutos, "/livro": self.post_livro,
                      "/config": self.post_config}
        if req.method == "POST" and p in rotas_post:
            return rotas_post[p](req, est)
        if p in rotas_get:
            return Resp(rotas_get[p](req, est))
        return Resp(self.layout(req, "Não encontrado", "<p>Página não encontrada.</p>"), "404 Not Found")

    # --- agenda -------------------------------------------------------------
    def ocorrencias(self, est, ini, fim):
        """(ocorrencias, erro, configurada)"""
        url = est.d["config"].get("ical_url", "").strip()
        if not url:
            return [], None, False
        texto, erro = agenda.baixar(url, self.pasta)
        if texto is None:
            return [], erro, True
        try:
            evs = agenda.parse(texto)
            return agenda.expandir(evs, ini, fim), erro, True
        except Exception as e:  # noqa: BLE001
            traceback.print_exc(file=sys.stderr)
            return [], f"erro ao interpretar a agenda: {e}", True

    def analisar(self, est, dias, agora):
        ini = datetime.combine(dias[0], datetime.min.time()).replace(tzinfo=TZ)
        fim = datetime.combine(dias[-1] + timedelta(days=1), datetime.min.time()).replace(tzinfo=TZ)
        ocs, erro, configurada = self.ocorrencias(est, ini, fim)
        res = {}
        for d in dias:
            a = agenda.analisar_dia(d, ocs, est.d["config"], agora)
            if not configurada or (erro and not ocs):
                a["minutos"] = int(est.d["config"].get("min_sem_agenda", 30))
                a["fonte"] = "padrao"
            else:
                a["fonte"] = "agenda"
            res[d] = a
        return res, erro, configurada

    # --- plano do dia -------------------------------------------------------
    def plano_de_hoje(self, est, hoje, analise):
        """Le (ou cria) o plano de hoje; refaz a divisao se os livros mudaram."""
        reg = est.d["dias"].setdefault(hoje.isoformat(), {})
        pl = reg.get("plano")
        ativos = est.lendo()
        ids_ativos = {b["id"] for b in ativos}
        mudou = False
        if not pl:
            pl = {"minutos": analise["minutos"], "fonte": analise["fonte"],
                  "horario": analise["horario"].strftime("%H:%M") if analise["horario"] else None}
            mudou = True
        if pl.get("fonte") != "manual" and reg.get("feito") is None:
            novo_min = analise["minutos"]
            if novo_min != pl["minutos"] or pl.get("fonte") != analise["fonte"]:
                pl["minutos"], pl["fonte"] = novo_min, analise["fonte"]
                pl["horario"] = analise["horario"].strftime("%H:%M") if analise["horario"] else None
                mudou = True
        blocos = {int(k): v for k, v in (pl.get("blocos") or {}).items()}
        partes = {int(k): v for k, v in (pl.get("partes") or {}).items()}
        feitas = {b["id"]: b["feitas"] for b in ativos}
        desatualizado = any(min(v) < feitas.get(k, 0) for k, v in partes.items() if v)
        if (mudou or not blocos or not set(blocos) <= ids_ativos or desatualizado
                or pl.get("base_min") != pl["minutos"] or pl.get("v") != 2) and reg.get("feito") is None:
            blocos, partes = plano.planejar(ativos, pl["minutos"], est.minutos_por_livro(hoje), est.ritmo)
            pl["base_min"], pl["v"] = pl["minutos"], 2
            mudou = True
        pl["blocos"] = {str(k): v for k, v in blocos.items()}
        pl["partes"] = {str(k): v for k, v in partes.items()}
        reg["plano"] = pl
        if mudou:
            est.salvar()
        return pl, blocos, partes

    def previsao_base(self, est, hoje):
        media, n, real = est.media_minutos(hoje)
        inicio = hoje + timedelta(days=1) if (est.dia(hoje) or {}).get("feito") else hoje
        return plano.simular(est, media, inicio), media, n, real

    # --- layout -------------------------------------------------------------
    def layout(self, req, titulo, corpo, aba=None, msg=None):
        abas = [("/", "Hoje"), ("/livros", "Livros"), ("/previsao", "Previsão"), ("/config", "Ajustes")]
        nav = "".join(f'<a href="{req.url(u)}" class="{"on" if aba == u else ""}">{n}</a>' for u, n in abas)
        aviso = f'<div class="msg">{esc(msg)}</div>' if msg else ""
        return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(titulo)} · Biblioteca</title>
<link rel="icon" type="image/svg+xml" href="{req.url('/favicon.svg')}">
<link rel="apple-touch-icon" href="{req.url('/apple-touch-icon.png')}">
<meta name="theme-color" content="#1f3a5f">
<style>{CSS}</style></head><body>
<header><a class="marca" href="{req.url('/')}">📚 Biblioteca</a>{'<nav>' + nav + '</nav>' if aba else ''}</header>
<main>{aviso}{corpo}</main></body></html>"""

    def pagina_setup(self, req, erro=None):
        corpo = f"""<section class="card estreito"><h1>Primeiro acesso</h1>
<p>Crie a senha do seu site de leituras. Ela será pedida em cada aparelho novo.</p>
{f'<p class="erro">{esc(erro)}</p>' if erro else ''}
<form method="post" action="{req.url('/setup')}">
<label>Senha<input type="password" name="senha" autocomplete="new-password" required></label>
<label>Repita a senha<input type="password" name="senha2" autocomplete="new-password" required></label>
<button class="prim">Criar senha e entrar</button></form></section>"""
        return self.layout(req, "Primeiro acesso", corpo)

    def pagina_login(self, req, erro=None):
        corpo = f"""<section class="card estreito"><h1>Entrar</h1>
{f'<p class="erro">{esc(erro)}</p>' if erro else ''}
<form method="post" action="{req.url('/login')}">
<label>Senha<input type="password" name="senha" autocomplete="current-password" autofocus required></label>
<button class="prim">Entrar</button></form></section>"""
        return self.layout(req, "Entrar", corpo)

    # --- HOJE ---------------------------------------------------------------
    def pagina_hoje(self, req, est):
        agora = datetime.now(TZ)
        hoje = agora.date()
        dias = [hoje + timedelta(days=i) for i in range(8)]
        analise, erro_ag, ag_config = self.analisar(est, dias, agora)
        a_hoje = analise[hoje]
        pl, blocos, partes_hoje = self.plano_de_hoje(est, hoje, a_hoje)
        reg = est.dia(hoje) or {}
        prev, media, n_hist, real = self.previsao_base(est, hoje)

        # cabecalho / cadencia
        seq = est.sequencia(hoje)
        ult30 = sum(1 for i in range(30) if (est.dia(hoje - timedelta(days=i)) or {}).get("feito"))
        fonte = {"agenda": f"pela sua agenda ({a_hoje['ocupado_min'] // 60}h{a_hoje['ocupado_min'] % 60:02d} de compromissos)",
                 "padrao": "valor padrão (agenda não conectada)" if not ag_config else "valor padrão (agenda indisponível)",
                 "manual": "escolhido por você"}.get(pl.get("fonte"), "")
        horario = ""
        if pl.get("horario"):
            h = datetime.strptime(pl["horario"], "%H:%M")
            horario = f'{pl["horario"]}–{(h + timedelta(minutes=pl["minutos"])).strftime("%H:%M")}'

        botoes_min = "".join(
            f'<button name="m" value="{m}" class="chip{" on" if pl["minutos"] == m else ""}">{m} min</button>'
            for m in (15, 30, 45, 60))
        if pl.get("fonte") == "manual":
            botoes_min += '<button name="m" value="auto" class="chip">automático</button>'

        # livros do dia + formulario de registro
        linhas = []
        for b in est.lendo():
            m = blocos.get(b["id"], 0)
            pct = min(100, round(100 * b["pagina"] / b["paginas"])) if b["paginas"] else 0
            fim = prev.get(b["id"], {}).get("fim")
            feito_m = (reg.get("sessoes") or {}).get(str(b["id"]))
            val_min = feito_m if feito_m is not None else m
            if b["partes"]:
                idxs = partes_hoje.get(b["id"], [])
                tam = plano.tamanhos(b)
                hoje_txt = "".join(
                    f'<li><b>{esc(b["partes"][i]["t"])}</b> <span>≈ {plano.minutos_parte(b, i, est.ritmo(b["tipo"]))} min'
                    f' · {round(tam[i])} p.</span></li>' for i in idxs if i < len(b["partes"]))
                prox_txt = (f'<ul class="partes">{hoje_txt}</ul>' if hoje_txt else "")
                n = len(b["partes"])
                progresso = f'{b["feitas"]} de {n} partes lidas'
                padrao = (max(idxs) + 1) if idxs else b["feitas"]
                if reg.get("feito") is True:
                    padrao = b["feitas"]
                opcoes = [f'<option value="{b["feitas"]}"{" selected" if padrao == b["feitas"] else ""}>'
                          f'não avancei{" (parei antes de " + esc(b["partes"][b["feitas"]]["t"]) + ")" if b["feitas"] < n else ""}</option>']
                for i in range(b["feitas"], n):
                    opcoes.append(f'<option value="{i + 1}"{" selected" if padrao == i + 1 else ""}>até o fim de {esc(b["partes"][i]["t"])}</option>')
                campo_avanco = f'<label>terminei<select name="u_{b["id"]}">{"".join(opcoes)}</select></label>'
            else:
                prox_txt = ""
                progresso = f'p. {b["pagina"]} de {b["paginas"]}'
                campo_avanco = (f'<label>parei na página<input type="number" name="p_{b["id"]}" placeholder="{b["pagina"]}" '
                                f'min="0" max="{b["paginas"] * 2}"></label>')
            sem_sumario = ("" if b["partes"] else
                           f'<div class="dica">Sem sumário: lendo em blocos de 15 min. '
                           f'<a href="{req.url("/livros", f="lendo")}#l{b["id"]}">Colar o sumário</a> para ler por capítulos.</div>')
            linhas.append(f"""<div class="livro{' fora' if not m else ''}">
<div class="lv-top"><div><div class="lv-tit">{esc(b['titulo'])}</div>
<div class="lv-aut">{esc(b['autor'])}{' · ' if b['autor'] else ''}{TIPO_NOME[b['tipo']]}{' · CESG' if b['cesg'] else ''}</div></div>
<div class="lv-min">{f'{m}<small> min</small>' if m else '<small>hoje não</small>'}</div></div>
<div class="barra"><span style="width:{pct}%"></span></div>
<div class="lv-info">{progresso} · {pct}% · termina ≈ {fdata(fim)} ({fprazo(hoje, fim)})</div>
{prox_txt}{sem_sumario}
<div class="lv-form"><label>min lidos<input type="number" name="m_{b['id']}" value="{val_min}" min="0" max="600" step="5"></label>
{campo_avanco}</div>
</div>""")
        if not linhas:
            linhas.append(f'<p>Nenhum livro em andamento. <a href="{req.url("/livros", f="fila")}">Escolha o próximo</a>.</p>')

        if reg.get("feito") is True:
            estado_dia = f'<div class="ok">✅ Leitura de hoje registrada: {reg.get("minutos", 0)} min.</div>'
            botoes = ('<button name="feito" value="1" class="sec">Atualizar registro</button>'
                      '<button name="feito" value="limpar" class="link">desfazer</button>')
        elif reg.get("feito") is False:
            estado_dia = '<div class="nao">Hoje marcado como <b>não li</b>.</div>'
            botoes = ('<button name="feito" value="1" class="prim">✅ Li hoje</button>'
                      '<button name="feito" value="limpar" class="link">desfazer</button>')
        else:
            estado_dia = ""
            botoes = ('<button name="feito" value="1" class="prim">✅ Li hoje</button>'
                      '<button name="feito" value="0" class="sec">❌ Não li hoje</button>')

        compromissos = "".join(
            f'<li><b>{o["inicio"].strftime("%H:%M")}–{o["fim"].strftime("%H:%M")}</b> {esc(o["titulo"])}</li>'
            for o in a_hoje["compromissos"]) + "".join(
            f'<li><b>dia todo</b> {esc(o["titulo"])}</li>' for o in a_hoje["dia_inteiro"])
        if ag_config:
            bloco_agenda = (f'<details><summary>Agenda de hoje ({len(a_hoje["compromissos"])} compromissos)</summary>'
                            f'<ul class="ag">{compromissos or "<li>Nada marcado.</li>"}</ul></details>')
        else:
            bloco_agenda = f'<p class="dica">Conecte sua agenda em <a href="{req.url("/config")}">Ajustes</a> para o tempo do dia se ajustar aos seus compromissos.</p>'
        if erro_ag:
            bloco_agenda += f'<p class="erro">{esc(erro_ag)}</p>'

        proximos = "".join(
            f'<li><span>{SEMANA_C[d.weekday()]} {d.day}</span><b>{analise[d]["minutos"]} min</b>'
            f'<span>{analise[d]["horario"].strftime("%H:%M") if analise[d]["horario"] else "—"}</span></li>'
            for d in dias[1:])

        corpo = f"""
<section class="card destaque">
<div class="data">{fdata_longa(hoje)}</div>
<div class="meta"><span class="grande">{pl['minutos']} min</span>
{f'<span class="hora">sugestão: {horario}</span>' if horario else ''}</div>
<div class="fonte">{esc(fonte)}</div>
<form method="post" action="{req.url('/minutos')}" class="chips">{botoes_min}</form>
<div class="cad"><span>🔥 <b>{seq}</b> {'dia seguido' if seq == 1 else 'dias seguidos'}</span>
<span><b>{ult30}</b>/30 dias</span><span>média <b>{media:.0f}</b> min/dia</span></div>
</section>
<section class="card"><h2>Leitura de hoje</h2>{estado_dia}
<form method="post" action="{req.url('/registrar')}">{''.join(linhas)}
<div class="acoes">{botoes}</div></form>
<p class="dica">O plano nunca para no meio de um canto ou capítulo: a primeira leitura do dia entra inteira, mesmo que passe um pouco do tempo. Informe até onde leu e os minutos, para o site aprender seu ritmo. Ao terminar a última parte, o livro é marcado como lido e o próximo da fila começa sozinho.</p>
</section>
<section class="card"><h2>Cadência</h2>{self.mapa(req, est, hoje)}</section>
<section class="card"><h2>Próximos dias</h2><ul class="prox">{proximos}</ul>{bloco_agenda}</section>
"""
        return self.layout(req, "Hoje", corpo, "/", req.query.get("msg"))

    def mapa(self, req, est, hoje, semanas=15):
        ini = hoje - timedelta(days=hoje.weekday()) - timedelta(weeks=semanas - 1)
        cols = []
        for w in range(semanas):
            cel = []
            for wd in range(7):
                d = ini + timedelta(days=7 * w + wd)
                if d > hoje:
                    cel.append('<i class="vazio"></i>')
                    continue
                reg = est.dia(d) or {}
                if reg.get("feito"):
                    m = int(reg.get("minutos", 0))
                    cls = "n4" if m >= 60 else "n3" if m >= 45 else "n2" if m >= 30 else "n1"
                    tit = f"{fdata(d)}: {m} min"
                elif reg.get("feito") is False:
                    cls, tit = "nao", f"{fdata(d)}: não li"
                else:
                    cls, tit = "sem", f"{fdata(d)}: sem registro"
                if d == hoje:
                    cls += " hoje"
                cel.append(f'<button name="d" value="{d.isoformat()}" class="{cls}" title="{tit} (toque para alternar)"></button>')
            cols.append(f'<div class="col">{"".join(cel)}</div>')
        legenda = ('<div class="legenda"><span><i class="sem"></i>sem registro</span><span><i class="nao"></i>não li</span>'
                   '<span><i class="n1"></i>15</span><span><i class="n2"></i>30</span><span><i class="n3"></i>45</span>'
                   '<span><i class="n4"></i>60+ min</span></div>')
        return (f'<form method="post" action="{req.url("/dia")}" class="mapa">{"".join(cols)}</form>{legenda}'
                '<p class="dica">Toque num dia para alternar: sem registro → li (15 min) → não li.</p>')

    # --- acoes do dia -------------------------------------------------------
    def post_minutos(self, req, est):
        agora = datetime.now(TZ)
        hoje = agora.date()
        reg = est.d["dias"].setdefault(hoje.isoformat(), {})
        pl = reg.setdefault("plano", {})
        m = req.form.get("m", "")
        if m == "auto":
            pl.clear()
        elif m.isdigit() and 15 <= int(m) <= 240:
            pl["minutos"] = int(m)
            pl["fonte"] = "manual"
            a = self.analisar(est, [hoje], agora)[0][hoje]
            cfg = dict(est.d["config"])
            # recalcula o horario para a nova duracao
            if a["horario"] is not None:
                a2 = agenda.analisar_dia(hoje, a["compromissos"], cfg, agora)
                pl["horario"] = a2["horario"].strftime("%H:%M") if a2["horario"] else pl.get("horario")
            bl, pt = plano.planejar(est.lendo(), pl["minutos"], est.minutos_por_livro(hoje), est.ritmo)
            pl["blocos"] = {str(k): v for k, v in bl.items()}
            pl["partes"] = {str(k): v for k, v in pt.items()}
            pl["base_min"], pl["v"] = pl["minutos"], 2
        est.salvar()
        return redirecionar(req.url("/"))

    def post_registrar(self, req, est):
        hoje = plano.hoje_local()
        reg = est.d["dias"].setdefault(hoje.isoformat(), {})
        acao = req.form.get("feito")
        msgs = []
        if acao == "limpar":
            for k in ("feito", "minutos", "sessoes"):
                reg.pop(k, None)
        elif acao == "0":
            reg.update({"feito": False, "minutos": 0, "sessoes": {}})
        elif acao == "1":
            sessoes, total = {}, 0
            for b in est.lendo():
                try:
                    m = int(req.form.get(f"m_{b['id']}", "0") or 0)
                except ValueError:
                    m = 0
                m = max(0, min(600, m))
                un = req.form.get(f"u_{b['id']}", "").strip()
                if b["partes"] and un.isdigit():
                    nf = max(0, min(int(un), len(b["partes"])))
                    if nf > b["feitas"]:
                        est.calibrar(b["tipo"], plano.pagina_apos(b, nf) - plano.pagina_apos(b, b["feitas"]), m)
                    est._u(b["id"])["feitas"] = nf
                    if nf >= len(b["partes"]):
                        novos = est.concluir(b["id"], hoje)
                        msgs.append(f"🎉 “{b['titulo']}” concluído!")
                        for nb in novos or []:
                            msgs.append(f"Começando “{nb['titulo']}”.")
                pg = req.form.get(f"p_{b['id']}", "").strip()
                if pg.isdigit() and not b["partes"]:
                    nova = int(pg)
                    if nova > b["pagina"]:
                        est.calibrar(b["tipo"], nova - b["pagina"], m)
                    est._u(b["id"])["pagina"] = min(nova, b["paginas"])
                    if nova >= b["paginas"]:
                        novos = est.concluir(b["id"], hoje)
                        msgs.append(f"🎉 “{b['titulo']}” concluído!")
                        for nb in novos or []:
                            msgs.append(f"Começando “{nb['titulo']}”.")
                if m:
                    sessoes[str(b["id"])] = m
                    total += m
            if total < 15:
                msgs.append("Registrado (lembrete: a meta mínima é 15 min).")
            reg.update({"feito": True, "minutos": total, "sessoes": sessoes})
        est.salvar()
        return redirecionar(req.url("/", msg=" ".join(msgs) or None))

    def post_dia(self, req, est):
        hoje = plano.hoje_local()
        try:
            d = date.fromisoformat(req.form.get("d", ""))
        except ValueError:
            return redirecionar(req.url("/"))
        if d > hoje:
            return redirecionar(req.url("/"))
        reg = est.d["dias"].setdefault(d.isoformat(), {})
        if reg.get("feito") is None:
            reg.update({"feito": True, "minutos": 15, "sessoes": {}})
        elif reg.get("feito"):
            reg.update({"feito": False, "minutos": 0, "sessoes": {}})
        else:
            for k in ("feito", "minutos", "sessoes"):
                reg.pop(k, None)
        est.salvar()
        return redirecionar(req.url("/"))

    # --- LIVROS -------------------------------------------------------------
    def pagina_livros(self, req, est):
        hoje = plano.hoje_local()
        prev, *_ = self.previsao_base(est, hoje)
        f = req.query.get("f", "todos")
        fase = req.query.get("fase", "")
        filtros = [("todos", "Todos"), ("lendo", "Lendo"), ("fila", "Na fila"), ("lido", "Lidos"),
                   ("L", "Literatura/história"), ("P", "Ideias"), ("cesg", "CESG")]
        chips = "".join(f'<a class="chip{" on" if f == k else ""}" href="{req.url("/livros", f=k, fase=fase or None)}">{n}</a>'
                        for k, n in filtros)
        fases = '<option value="">todas as fases</option>' + "".join(
            f'<option value="{k}"{" selected" if str(k) == fase else ""}>{esc(v)}</option>' for k, v in catalogo.FASES.items())

        def passa(b):
            if fase and str(b["fase"]) != fase:
                return False
            return (f == "todos" or (f in ("lendo", "fila", "lido") and b["status"] == f)
                    or (f in ("L", "P") and b["tipo"] == f and not b["paralela"]) or (f == "cesg" and b["cesg"]))

        grupos = {}
        for b in est.todos():
            if passa(b):
                grupos.setdefault(b["fase"], []).append(b)
        blocos = []
        for fz, livros in sorted(grupos.items()):
            ids = [b["id"] for b in catalogo.carregar() if b["fase"] == fz]
            fim_fase = plano.fim_de(prev, ids) if fz != 9 else None
            itens = "".join(self.item_livro(req, b, prev.get(b["id"], {}), hoje) for b in livros)
            extra = f' <small>· termina ≈ {fdata(fim_fase)}</small>' if fim_fase else ""
            if fz == 9:
                extra = ' <small>· leitura diária à parte, fora da previsão</small>'
            blocos.append(f'<h2 class="fase">{esc(catalogo.FASES[fz])}{extra}</h2><div class="lista">{itens}</div>')
        corpo = f"""<section class="card"><div class="chips">{chips}</div>
<form class="filtro" method="get" action="{req.url('/livros')}"><input type="hidden" name="f" value="{esc(f)}">
<select name="fase" onchange="this.form.submit()">{fases}</select></form></section>
{''.join(blocos) or '<p>Nenhum livro com esse filtro.</p>'}"""
        return self.layout(req, "Livros", corpo, "/livros", req.query.get("msg"))

    def item_livro(self, req, b, pv, hoje):
        st = {"lendo": "📖 lendo", "fila": "na fila", "lido": "✅ lido"}[b["status"]]
        pct = min(100, round(100 * b["pagina"] / b["paginas"])) if b["paginas"] else 0
        if b["status"] == "lido":
            quando = f"lido em {fdata(date.fromisoformat(b['fim']))}" if b.get("fim") else "lido"
        elif b["paralela"]:
            quando = "leitura paralela"
        elif b["status"] == "lendo":
            quando = f"{pct}% · termina ≈ {fdata(pv.get('fim'))}"
        else:
            quando = f"≈ {fdata(pv.get('inicio'))} → {fdata(pv.get('fim'))}"
        num = f"{b['id']}." if not b["paralela"] else "•"
        voltar = req.url("/livros", f=req.query.get("f"), fase=req.query.get("fase") or None)
        acoes = []
        if b["status"] != "lendo":
            acoes.append('<button name="acao" value="comecar" class="sec">Começar agora</button>')
        if b["status"] != "lido":
            acoes.append('<button name="acao" value="lido" class="sec">Marcar como lido</button>')
        if b["status"] != "fila":
            acoes.append('<button name="acao" value="fila" class="link">voltar para a fila</button>')
        peso = "".join(f'<option value="{v}"{" selected" if b["peso"] == v else ""}>{n}</option>'
                       for v, n in ((1, "normal"), (2, "alta"), (3, "máxima")))
        n = len(b["partes"])
        if n:
            opc = "".join(f'<option value="{i}"{" selected" if b["feitas"] == i else ""}>'
                          f'{"nenhuma ainda" if i == 0 else "até o fim de " + esc(b["partes"][i - 1]["t"])}</option>'
                          for i in range(n + 1))
            campo_pos = f'<label class="largo">já li<select name="feitas">{opc}</select></label>'
        else:
            campo_pos = f'<label>página atual<input type="number" name="pagina" value="{b["pagina"]}" min="0" max="5000"></label>'
        if b["sumario_proprio"]:
            texto_sum = "\n".join(f'{p["t"]} ... {p["pg"]}' if isinstance(p.get("pg"), int) else p["t"] for p in b["partes"])
        else:
            texto_sum = ""
        origem = ("sumário colado por você" if b["sumario_proprio"] else
                  f"divisão padrão ({n} partes)" if n else "sem sumário: o plano usa blocos de 15 min")
        bloco_sum = f"""<label class="inteiro">Sumário <small>({origem})</small>
<textarea name="sumario" rows="{6 if texto_sum else 3}" placeholder="Cole o sumário: uma parte por linha, com a página inicial no fim. Ex.:&#10;Capítulo 1 — O começo ..... 13&#10;Capítulo 2 — O meio ...... 41&#10;(apague tudo para voltar à divisão padrão)">{esc(texto_sum)}</textarea></label>
<input type="hidden" name="sumario_antes" value="{esc(texto_sum)}">"""
        return f"""<details class="item {b['status']}" id="l{b['id']}"><summary>
<span class="num">{num}</span><span class="tt"><b>{esc(b['titulo'])}</b><small>{esc(b['autor'])}</small></span>
<span class="tag t{b['tipo']}">{b['tipo']}</span><span class="st">{st}<small>{quando}</small></span></summary>
<form method="post" action="{req.url('/livro')}" class="edit">
<input type="hidden" name="id" value="{b['id']}"><input type="hidden" name="volta" value="{esc(voltar)}">
<label>páginas<input type="number" name="paginas" value="{b['paginas']}" min="1" max="5000"></label>
{campo_pos}
<label>prioridade<select name="peso">{peso}</select></label>
{bloco_sum}
<button name="acao" value="salvar" class="prim">Salvar</button>{''.join(acoes)}
</form></details>"""

    def post_livro(self, req, est):
        hoje = plano.hoje_local()
        try:
            bid = int(req.form.get("id", ""))
        except ValueError:
            return redirecionar(req.url("/livros"))
        if bid not in est.por_id:
            return redirecionar(req.url("/livros"))
        volta = req.form.get("volta") or req.url("/livros")
        if not volta.startswith(req.base + "/"):
            volta = req.url("/livros")
        acao = req.form.get("acao")
        u = est._u(bid)
        b = est.info(bid)
        msg = None
        if acao == "salvar":
            if req.form.get("paginas", "").isdigit() and int(req.form["paginas"]) > 0:
                n = int(req.form["paginas"])
                if n != est.por_id[bid]["paginas"]:
                    u["paginas"] = n
                else:
                    u.pop("paginas", None)
            if req.form.get("sumario", "").strip() != req.form.get("sumario_antes", "").strip():
                novas = plano.ler_sumario(req.form.get("sumario", ""))
                if novas:
                    u["partes"] = novas
                else:
                    u.pop("partes", None)
                u["feitas"] = 0
                b = est.info(bid)
            elif req.form.get("feitas", "").isdigit() and b["partes"]:
                u["feitas"] = max(0, min(int(req.form["feitas"]), len(b["partes"])))
            if req.form.get("pagina", "").isdigit() and not est.info(bid)["partes"]:
                u["pagina"] = int(req.form["pagina"])
            if req.form.get("peso", "") in ("1", "2", "3"):
                u["peso"] = int(req.form["peso"])
            msg = "Salvo."
        elif acao == "comecar":
            est.comecar(bid, hoje)
            msg = f"Começando “{b['titulo']}”."
        elif acao == "lido":
            novos = est.concluir(bid, hoje)
            msg = f"“{b['titulo']}” marcado como lido." + "".join(f" Começando “{n['titulo']}”." for n in novos or [])
        elif acao == "fila":
            est.voltar_fila(bid)
            msg = f"“{b['titulo']}” voltou para a fila."
        est.salvar()
        sep = "&" if "?" in volta else "?"
        return redirecionar(volta + (sep + urlencode({"msg": msg}) if msg else ""))

    # --- PREVISAO -----------------------------------------------------------
    def pagina_previsao(self, req, est):
        hoje = plano.hoje_local()
        prev, media, n_hist, real = self.previsao_base(est, hoje)
        todos = [b for b in est.todos() if not b["paralela"]]

        def linha(nome, livros):
            ids = [b["id"] for b in livros]
            lidos = sum(1 for b in livros if b["status"] == "lido")
            pags = sum(b["paginas"] for b in livros)
            feitas = sum(b["paginas"] if b["status"] == "lido" else b["pagina"] for b in livros)
            pct = round(100 * feitas / pags) if pags else 0
            fim = plano.fim_de(prev, ids)
            return (f'<tr><td>{esc(nome)}<div class="barra fina"><span style="width:{pct}%"></span></div></td>'
                    f'<td class="n">{lidos}/{len(livros)}</td><td class="n">{pct}%</td>'
                    f'<td class="n"><b>{fdata(fim)}</b><small>{fprazo(hoje, fim)}</small></td></tr>')

        lendo = [b for b in todos if b["status"] == "lendo"]
        linhas_lendo = "".join(linha(b["titulo"], [b]) for b in lendo)
        linhas_fase = "".join(linha(catalogo.FASES[f], [b for b in todos if b["fase"] == f]) for f in range(1, 8))
        linhas_tipo = (linha("Literatura e história", [b for b in todos if b["tipo"] == "L"])
                       + linha("Ideias (filosofia, teologia, espiritualidade)", [b for b in todos if b["tipo"] == "P"])
                       + linha("Leituras do CESG", [b for b in todos if b["cesg"]]))
        linha_total = linha("Estante inteira", todos)

        cenarios = []
        ids_todos = [b["id"] for b in todos]
        ids_cesg = [b["id"] for b in todos if b["cesg"]]
        inicio = hoje + timedelta(days=1) if (est.dia(hoje) or {}).get("feito") else hoje
        for m in (15, 30, 45, 60):
            s = plano.simular(est, m, inicio)
            ft, fc = plano.fim_de(s, ids_todos), plano.fim_de(s, ids_cesg)
            cenarios.append(f'<tr><td><b>{m} min/dia</b></td><td class="n">{fdata(fc)}<small>{fprazo(hoje, fc)}</small></td>'
                            f'<td class="n">{fdata(ft)}<small>{fprazo(hoje, ft)}</small></td></tr>')
        restante = sum(b["paginas"] - (b["paginas"] if b["status"] == "lido" else b["pagina"]) for b in todos)
        restante_fmt = f"{restante:,}".replace(",", ".")
        base = (f"sua média real dos últimos {n_hist} dias" if real
                else f"valor inicial de {media:.0f} min/dia (a média real entra quando houver 7 dias de registro)")

        corpo = f"""
<section class="card"><h2>Como a previsão é feita</h2>
<p>Ritmo de <b>{media:.0f} min/dia</b> ({base}); leitura de <b>{est.ritmo('L') * 60:.0f} páginas/hora</b> em literatura e história
e <b>{est.ritmo('P') * 60:.0f} páginas/hora</b> em livros de ideias. O ritmo se ajusta conforme você registra a página onde parou.
Até {est.d['config']['max_simultaneos']} livros ao mesmo tempo, sempre com pelo menos um de literatura ou história;
quando um termina, entra o próximo da ordem. Faltam ≈ {restante_fmt} páginas.</p>
<p class="dica">Os números de páginas são estimativas: corrija em <a href="{req.url('/livros')}">Livros</a> para afinar a previsão.</p></section>
<section class="card"><h2>Em andamento</h2><table>{CAB}{linhas_lendo or '<tr><td colspan=4>Nenhum.</td></tr>'}</table></section>
<section class="card"><h2>Por fase</h2><table>{CAB}{linhas_fase}</table></section>
<section class="card"><h2>Por tipo</h2><table>{CAB}{linhas_tipo}{linha_total}</table></section>
<section class="card"><h2>E se eu ler…</h2><table><tr><th></th><th class="n">CESG</th><th class="n">Estante inteira</th></tr>{''.join(cenarios)}</table>
<p class="dica">As leituras paralelas (Bíblia, Falar com Deus, Imitação de Cristo…) ficam fora da conta.</p></section>
"""
        return self.layout(req, "Previsão", corpo, "/previsao")

    # --- AJUSTES ------------------------------------------------------------
    def pagina_config(self, req, est):
        c = est.d["config"]
        feed = req.absoluto(f"/agenda.ics?k={quote(est.d['feed_token'])}")
        agora = datetime.now(TZ)
        teste = ""
        if c.get("ical_url"):
            ini = datetime.combine(agora.date(), datetime.min.time()).replace(tzinfo=TZ)
            ocs, erro, _ = self.ocorrencias(est, ini, ini + timedelta(days=7))
            teste = (f'<p class="erro">{esc(erro)}</p>' if erro and not ocs else
                     f'<p class="ok">Agenda conectada: {len(ocs)} compromissos nos próximos 7 dias.</p>')

        def campo(nome, rotulo, tipo="text", extra=""):
            return f'<label>{rotulo}<input type="{tipo}" name="{nome}" value="{esc(c.get(nome, ""))}" {extra}></label>'

        corpo = f"""
<form method="post" action="{req.url('/config')}">
<section class="card"><h2>Sua agenda → tempo de leitura</h2>
<p>No Google Agenda (computador): <b>Configurações → sua agenda → Integrar agenda → Endereço secreto no formato iCal</b>. Copie e cole aqui.
O site lê seus compromissos e sugere 15 a 60 min por dia e o melhor horário livre.</p>
{campo('ical_url', 'Endereço secreto iCal', 'url', 'placeholder="https://calendar.google.com/calendar/ical/.../basic.ics"')}
{teste}
<div class="grade">{campo('janela_inicio', 'Ler a partir de', 'time')}{campo('janela_fim', 'Até', 'time')}
{campo('horario_preferido', 'Horário preferido', 'time')}</div>
<p class="dica">Regra: até {c['limite_60']}h de compromissos no dia → 60 min; até {c['limite_45']}h → 45; até {c['limite_30']}h → 30; acima → 15 min.
Se não houver um intervalo livre grande o bastante, o tempo diminui.</p>
<div class="grade">{campo('limite_60', '60 min se ≤ (h)', 'number', 'step="0.5" min="0"')}
{campo('limite_45', '45 min se ≤ (h)', 'number', 'step="0.5" min="0"')}{campo('limite_30', '30 min se ≤ (h)', 'number', 'step="0.5" min="0"')}</div>
{campo('min_sem_agenda', 'Minutos por dia sem agenda', 'number', 'min="15" max="60" step="15"')}
</section>
<section class="card"><h2>Leitura → sua agenda</h2>
<p>Para ver os blocos de leitura dentro do Google Agenda: <b>Outras agendas → + → Do URL</b> e cole o endereço abaixo
(o Google atualiza agendas assinadas algumas vezes por dia).</p>
<input readonly class="copiar" value="{esc(feed)}" onclick="this.select()">
</section>
<section class="card"><h2>Ritmo e previsão</h2>
<div class="grade">{campo('ritmo_L', 'Literatura (pág/min)', 'number', 'step="0.05" min="0.1" max="3"')}
{campo('ritmo_P', 'Ideias (pág/min)', 'number', 'step="0.05" min="0.1" max="3"')}
{campo('max_simultaneos', 'Livros ao mesmo tempo', 'number', 'min="1" max="6"')}
{campo('min_previsao', 'Min/dia inicial da previsão', 'number', 'min="5" max="240"')}</div>
<p class="dica">O ritmo se ajusta sozinho quando você informa a página onde parou.</p>
</section>
<section class="card"><h2>Senha</h2>
<label>Nova senha (deixe em branco para manter)<input type="password" name="nova_senha" autocomplete="new-password"></label>
</section>
<div class="acoes"><button class="prim">Salvar ajustes</button><a class="link" href="{req.url('/sair')}">sair</a></div>
</form>"""
        return self.layout(req, "Ajustes", corpo, "/config", req.query.get("msg"))

    def post_config(self, req, est):
        c = est.d["config"]
        f = req.form
        url = f.get("ical_url", "").strip()
        if url and not url.startswith("https://"):
            return redirecionar(req.url("/config", msg="O endereço da agenda precisa começar com https://"))
        if url != c.get("ical_url"):
            try:
                os.remove(os.path.join(self.pasta, "agenda_cache.json"))
            except OSError:
                pass
        c["ical_url"] = url
        for k in ("janela_inicio", "janela_fim", "horario_preferido"):
            v = f.get(k, "")
            if len(v) >= 4 and ":" in v:
                c[k] = v[:5]
        for k, lo, hi in (("limite_60", 0, 24), ("limite_45", 0, 24), ("limite_30", 0, 24),
                          ("ritmo_L", 0.1, 3), ("ritmo_P", 0.1, 3)):
            try:
                c[k] = max(lo, min(hi, float(f.get(k, c[k]))))
            except ValueError:
                pass
        for k, lo, hi in (("min_sem_agenda", 15, 60), ("max_simultaneos", 1, 6), ("min_previsao", 5, 240)):
            try:
                c[k] = max(lo, min(hi, int(float(f.get(k, c[k])))))
            except ValueError:
                pass
        msg = "Ajustes salvos."
        if f.get("nova_senha"):
            if len(f["nova_senha"]) < 6:
                msg = "Ajustes salvos; a senha nova precisa de 6+ caracteres (não foi trocada)."
            else:
                self.definir_senha(est, f["nova_senha"])
                msg = "Ajustes salvos e senha trocada."
        # replaneja hoje se ainda nao foi registrado
        reg = est.d["dias"].get(plano.hoje_local().isoformat(), {})
        if reg.get("feito") is None and reg.get("plano", {}).get("fonte") != "manual":
            reg.pop("plano", None)
        est.salvar()
        return redirecionar(req.url("/config", msg=msg))

    # --- feed iCal para o Google Agenda --------------------------------------
    def feed_ics(self, req, est):
        agora = datetime.now(TZ)
        hoje = agora.date()
        dias = [hoje + timedelta(days=i) for i in range(14)]
        analise, _, _ = self.analisar(est, dias, None)
        historico = est.minutos_por_livro(hoje)
        ativos = est.lendo()
        feitas = {b["id"]: b["feitas"] for b in ativos}
        nomes = {b["id"]: b["titulo"] for b in est.todos()}
        stamp = agora.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//biblioteca//leituras//PT",
               "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Leituras",
               "X-WR-TIMEZONE:America/Sao_Paulo", "REFRESH-INTERVAL;VALUE=DURATION:PT6H"]

        def txt(s):
            return s.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")

        for d in dias:
            reg = est.dia(d) or {}
            if d == hoje and reg.get("plano"):
                pl = reg["plano"]
                minutos = pl.get("minutos", analise[d]["minutos"])
                blocos = {int(k): v for k, v in (pl.get("blocos") or {}).items()}
                partes = {int(k): v for k, v in (pl.get("partes") or {}).items()}
                hora = pl.get("horario")
                inicio = (datetime.combine(d, datetime.strptime(hora, "%H:%M").time()).replace(tzinfo=TZ)
                          if hora else analise[d]["horario"])
                minutos = sum(blocos.values()) or minutos
            else:
                minutos = analise[d]["minutos"]
                ativos_d = [dict(b, feitas=feitas[b["id"]]) for b in ativos]
                blocos, partes = plano.planejar(ativos_d, minutos, historico, est.ritmo)
                minutos = sum(blocos.values()) or minutos
                inicio = analise[d]["horario"]
            for k, v in blocos.items():
                historico[k] = historico.get(k, 0) + v
            for k, v in partes.items():
                if v:
                    feitas[k] = max(feitas.get(k, 0), max(v) + 1)
            por_id = {b["id"]: b for b in ativos}
            if inicio is None:
                h, m = (est.d["config"].get("horario_preferido", "21:00") + ":00").split(":")[:2]
                inicio = datetime(d.year, d.month, d.day, int(h), int(m), tzinfo=TZ)
            fim = inicio + timedelta(minutes=minutos)
            linhas_desc = []
            for k, v in sorted(blocos.items(), key=lambda kv: -kv[1]):
                nomes_p = [por_id[k]["partes"][i]["t"] for i in partes.get(k, [])
                           if k in por_id and i < len(por_id[k]["partes"])]
                linhas_desc.append(f"{v}' {nomes.get(k, '?')}" + (f" ({', '.join(nomes_p)})" if nomes_p else ""))
            status = " ✅" if reg.get("feito") else ""
            out += ["BEGIN:VEVENT", f"UID:{d.isoformat()}@biblioteca-leituras", f"DTSTAMP:{stamp}",
                    f"DTSTART;TZID=America/Sao_Paulo:{inicio.strftime('%Y%m%dT%H%M%S')}",
                    f"DTEND;TZID=America/Sao_Paulo:{fim.strftime('%Y%m%dT%H%M%S')}",
                    f"SUMMARY:{txt(f'📖 Leitura {minutos} min{status}')}",
                    f"DESCRIPTION:{txt(chr(10).join(linhas_desc) + chr(10) + chr(10) + req.absoluto('/'))}",
                    "TRANSP:TRANSPARENT", "END:VEVENT"]
        out.append("END:VCALENDAR")
        return "\r\n".join(out) + "\r\n"


# icone: livro aberto creme com marcador dourado sobre azul-marinho
FAVICON_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#1f3a5f"/><path d="M32 19C26 15 18 14 10 15v32c8-1 16 0 22 4z" fill="#f6ecd6"/><path d="M32 19c6-4 14-5 22-4v32c-8-1-16 0-22 4z" fill="#e6d3ad"/><path d="M41 15.6V30l3.5-3 3.5 3V15.2" fill="#e3a83b"/></svg>'
ICONE_180_PNG = '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'

CAB = '<tr><th></th><th class="n">lidos</th><th class="n">páginas</th><th class="n">término</th></tr>'

CSS = """
:root{--bg:#f6f1e7;--card:#fffdf8;--tx:#2b2620;--sub:#7a6f62;--li:#e7dfd0;--ac:#8a2d22;--ac2:#b65a3c;
--ok:#2f6b3a;--n1:#cfe3c8;--n2:#9cc98f;--n3:#5fa35a;--n4:#2f6b3a;--nao:#e9b8ad;--sem:#e9e3d6}
@media (prefers-color-scheme:dark){:root{--bg:#1b1916;--card:#25221e;--tx:#ece5d8;--sub:#a59a8a;--li:#3a352e;
--ac:#e0866f;--ac2:#c96f55;--ok:#8fd19a;--n1:#2e4a2c;--n2:#3f6e3a;--n3:#58994f;--n4:#7cc76f;--nao:#6e3a31;--sem:#33302a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:16px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--li);padding:10px 16px;display:flex;
align-items:center;gap:12px;flex-wrap:wrap}
.marca{font:600 19px Georgia,serif;color:var(--tx);text-decoration:none;margin-right:auto}
nav{display:flex;gap:4px}nav a{color:var(--sub);text-decoration:none;padding:6px 10px;border-radius:8px;font-size:15px}
nav a.on{background:var(--card);color:var(--ac);font-weight:600;box-shadow:0 1px 2px #0001}
main{max-width:760px;margin:0 auto;padding:14px 16px 60px}
.card{background:var(--card);border:1px solid var(--li);border-radius:14px;padding:16px;margin:0 0 14px}
.estreito{max-width:380px;margin:40px auto}
h1,h2{font-family:Georgia,serif;font-weight:600}h1{font-size:24px;margin:0 0 10px}h2{font-size:19px;margin:0 0 10px}
h2.fase{margin:22px 4px 8px;font-size:18px}h2 small{font:13px system-ui;color:var(--sub)}
.destaque .data{color:var(--sub)}.destaque .data::first-letter{text-transform:uppercase}
.meta{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin:2px 0}
.grande{font:700 44px Georgia,serif;color:var(--ac)}.hora{font-size:17px}
.fonte{color:var(--sub);font-size:14px}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}
.chip{border:1px solid var(--li);background:transparent;color:var(--tx);border-radius:99px;padding:5px 12px;font-size:14px;
cursor:pointer;text-decoration:none}.chip.on{background:var(--ac);border-color:var(--ac);color:#fff}
.cad{display:flex;gap:16px;flex-wrap:wrap;color:var(--sub);font-size:14px;border-top:1px solid var(--li);padding-top:10px;margin-top:6px}
.cad b{color:var(--tx)}
.livro{border-top:1px solid var(--li);padding:12px 0}.livro.fora{opacity:.6}
.lv-top{display:flex;justify-content:space-between;gap:10px}.lv-tit{font-weight:600}
.lv-aut,.lv-info{color:var(--sub);font-size:13px}.lv-min{font:700 22px Georgia,serif;color:var(--ac);white-space:nowrap}
.lv-min small{font-size:13px;font-weight:400}
.barra{height:6px;background:var(--li);border-radius:9px;overflow:hidden;margin:8px 0 4px}
.barra span{display:block;height:100%;background:var(--ac2)}.barra.fina{height:4px;margin:5px 0 0}
.lv-form{display:flex;gap:10px;margin-top:8px}.lv-form label{flex:1;font-size:12px;color:var(--sub)}
label{display:block;font-size:14px;color:var(--sub);margin:8px 0}
input,select{display:block;width:100%;margin-top:3px;padding:9px 10px;border:1px solid var(--li);border-radius:9px;
background:var(--bg);color:var(--tx);font:inherit;font-size:16px}
.copiar{font-size:13px}
.grade{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:0 12px}
button{font:inherit;cursor:pointer}
.prim,.sec{border-radius:10px;padding:10px 16px;font-weight:600;border:1px solid var(--ac)}
.prim{background:var(--ac);color:#fff}.sec{background:transparent;color:var(--ac)}
.link{background:none;border:none;color:var(--sub);text-decoration:underline;padding:8px}
.acoes{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:12px}
.dica{color:var(--sub);font-size:13px;margin:10px 0 0}
.msg{background:var(--card);border:1px solid var(--ac2);border-radius:12px;padding:10px 14px;margin-bottom:14px}
.ok{color:var(--ok);font-weight:600;margin:4px 0 8px}.nao{color:var(--ac);margin:4px 0 8px}.erro{color:#c0392b}
.mapa{display:flex;gap:3px;overflow-x:auto;padding-bottom:4px}.col{display:grid;grid-template-rows:repeat(7,1fr);gap:3px}
.mapa button,.mapa i,.legenda i{width:18px;height:18px;border-radius:4px;border:none;padding:0;display:block;background:var(--sem)}
.mapa i.vazio{background:transparent}
.n1{background:var(--n1)!important}.n2{background:var(--n2)!important}.n3{background:var(--n3)!important}
.n4{background:var(--n4)!important}.mapa .nao,.legenda .nao{background:var(--nao)!important}
.mapa .hoje{outline:2px solid var(--ac);outline-offset:1px}
.legenda{display:flex;gap:10px;flex-wrap:wrap;font-size:12px;color:var(--sub);margin-top:8px}
.legenda span{display:flex;align-items:center;gap:4px}.legenda i{width:12px;height:12px}
.prox{list-style:none;padding:0;margin:0 0 8px}.prox li{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--li)}
.prox li span:first-child{width:70px;color:var(--sub)}
.ag{padding-left:18px;font-size:14px}details summary{cursor:pointer;color:var(--sub);font-size:14px}
.lista{background:var(--card);border:1px solid var(--li);border-radius:14px;overflow:hidden}
.item{border-bottom:1px solid var(--li)}.item:last-child{border-bottom:none}
.item summary{display:flex;align-items:center;gap:10px;padding:10px 12px;list-style:none;color:var(--tx);font-size:15px}
.item summary::-webkit-details-marker{display:none}
.item .num{color:var(--sub);font-size:13px;width:34px;flex:none;text-align:right}
.item .tt{flex:1;min-width:0}.item .tt b{font-weight:500;display:block}.item .tt small{color:var(--sub)}
.item .st{font-size:13px;text-align:right;flex:none;max-width:42%}.item .st small{display:block;color:var(--sub)}
.item.lido .tt b{color:var(--sub)}.item.lendo{background:color-mix(in srgb,var(--ac2) 9%,transparent)}
.tag{font-size:11px;border-radius:5px;padding:1px 5px;flex:none;border:1px solid var(--li);color:var(--sub)}
.edit{padding:4px 12px 14px 56px;display:flex;flex-wrap:wrap;gap:8px;align-items:flex-end}
.edit label{width:110px;margin:0}.edit label.largo{width:auto;min-width:200px}.edit label.inteiro{width:100%}.edit label.check{width:100%;display:flex;gap:8px;align-items:center}.edit label.check input{width:auto;display:inline;margin:0}textarea{display:block;width:100%;margin-top:3px;padding:9px 10px;border:1px solid var(--li);border-radius:9px;background:var(--bg);color:var(--tx);font:14px/1.4 ui-monospace,monospace}.partes{list-style:none;padding:0;margin:8px 0 0}.partes li{padding:3px 0}.partes li span{color:var(--sub);font-size:13px}.filtro select{max-width:280px}
table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:8px 4px;border-bottom:1px solid var(--li);vertical-align:top}
th{color:var(--sub);font-weight:500;text-align:left}.n{text-align:right;white-space:nowrap}td small{display:block;color:var(--sub)}
@media (max-width:520px){.edit{padding-left:12px}.item .st{max-width:38%}.grande{font-size:38px}}
"""
