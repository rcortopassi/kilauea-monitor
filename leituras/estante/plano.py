"""Estado persistente, plano do dia e previsao de termino."""
import json
import os
import secrets
from datetime import date, datetime, timedelta

from . import catalogo

CONFIG_PADRAO = {
    "ical_url": "",
    "janela_inicio": "06:00",
    "janela_fim": "23:00",
    "horario_preferido": "21:00",
    "limite_60": 2,      # ate 2h de compromissos no dia -> 60 min de leitura
    "limite_45": 4,      # ate 4h -> 45 min
    "limite_30": 7,      # ate 7h -> 30 min; acima -> 15 min
    "min_sem_agenda": 30,
    "min_previsao": 30,  # usado na previsao enquanto nao ha 7 dias de historico
    "max_simultaneos": 3,
    "ritmo_L": 0.75,     # paginas por minuto (literatura/historia)
    "ritmo_P": 0.5,      # paginas por minuto (ideias)
}


def hoje_local():
    from .agenda import TZ
    return datetime.now(TZ).date()


# ----------------------------------------------------------------------------
# Persistencia

class Estado:
    def __init__(self, pasta):
        self.pasta = pasta
        os.makedirs(pasta, exist_ok=True)
        self.arquivo = os.path.join(pasta, "estado.json")
        self.cat = catalogo.carregar()
        self.por_id = {b["id"]: b for b in self.cat}
        self.d = self._ler()
        if self.d.pop("_migrou", False):
            self.salvar()

    def _ler(self):
        try:
            with open(self.arquivo, encoding="utf-8") as f:
                d = json.load(f)
        except FileNotFoundError:
            d = self._novo()
            d["migracoes"] = ["lendo_52_nao_56", "progresso_2026_11_11"]
        cfg = dict(CONFIG_PADRAO)
        cfg.update(d.get("config", {}))
        d["config"] = cfg
        d.setdefault("livros", {})
        d.setdefault("dias", {})
        self._migrar(d)
        return d

    @staticmethod
    def _migrar(d):
        """Correcoes pontuais nos dados ja gravados (cada uma roda uma vez so)."""
        feitas = d.setdefault("migracoes", [])
        if "lendo_52_nao_56" not in feitas:
            # o livro em andamento era "No Principio Deus Criou" (52), nao
            # "Deus Uno e Trino" (56): troca o status e move os minutos lidos
            lv = d["livros"]
            u56 = lv.get("56", {})
            if u56.get("status") == "lendo" and lv.get("52", {}).get("status") != "lido":
                u52 = lv.setdefault("52", {})
                u52["status"] = "lendo"
                u52["inicio"] = u56.get("inicio") or u52.get("inicio")
                u52["peso"] = u56.get("peso", 1)
                if u56.get("partes") and not u52.get("partes"):
                    u52["partes"], u52["feitas"] = u56.pop("partes"), u56.pop("feitas", 0)
                lv["56"] = {"status": "fila"}
                for reg in d["dias"].values():
                    for chave in ("sessoes",):
                        ses = reg.get(chave) or {}
                        if "56" in ses:
                            ses["52"] = ses.get("52", 0) + ses.pop("56")
                    pl = reg.get("plano") or {}
                    for chave in ("blocos", "partes"):
                        if "56" in (pl.get(chave) or {}):
                            pl.pop(chave, None)
                            pl.pop("base_min", None)
            feitas.append("lendo_52_nao_56")
            d["_migrou"] = True
        if "progresso_2026_11_11" not in feitas:
            # posicao informada pelo usuario: Odisseia ate o fim do Canto II;
            # Jardim das Aflicoes ate o fim do §14 (notas/prefacio + §1..§14)
            lv = d["livros"]
            for bid, n in (("0", 2), ("166", 14)):
                u = lv.setdefault(bid, {})
                if bid == "166" and u.get("partes"):
                    continue  # sumario proprio: indices diferentes, nao mexe
                if u.get("status") != "lido":
                    u["status"] = "lendo"
                    u["feitas"] = n
            # refaz o plano de hoje (se ainda nao registrado) com a nova posicao
            for reg in d["dias"].values():
                if reg.get("feito") is None and reg.get("plano"):
                    for k in ("blocos", "partes", "base_min"):
                        reg["plano"].pop(k, None)
            feitas.append("progresso_2026_11_11")
            d["_migrou"] = True

    def _novo(self):
        hoje = hoje_local().isoformat()
        livros = {str(i): {"status": "lendo", "peso": p, "inicio": hoje, "pagina": 0}
                  for i, p in catalogo.LENDO_INICIAL.items()}
        return {
            "versao": 1,
            "criado_em": hoje,
            "segredo": secrets.token_hex(32),
            "feed_token": secrets.token_urlsafe(18),
            "config": {},
            "livros": livros,
            "dias": {},
        }

    def salvar(self):
        tmp = self.arquivo + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.arquivo)

    # --- livros ------------------------------------------------------------
    def info(self, bid):
        """Livro do catalogo + estado do usuario mesclados."""
        b = dict(self.por_id[bid])
        u = self.d["livros"].get(str(bid), {})
        b["status"] = u.get("status", "fila")
        b["pagina"] = int(u.get("pagina", 0) or 0)
        if u.get("paginas"):
            b["paginas"] = int(u["paginas"])
        b["peso"] = int(u.get("peso", 1) or 1)
        b["inicio"] = u.get("inicio")
        b["fim"] = u.get("fim")
        if u.get("partes"):
            b["partes"] = [dict(p) for p in u["partes"]]
            b["sumario_proprio"] = True
        else:
            if bid in catalogo.PARTES_PG:
                b["partes"] = [{"t": t, "pg": pg} for t, pg in catalogo.PARTES_PG[bid]]
            else:
                b["partes"] = [{"t": t, "w": w} for t, w in catalogo.PARTES.get(bid, [])]
            b["sumario_proprio"] = False
        b["feitas"] = max(0, min(int(u.get("feitas", 0) or 0), len(b["partes"])))
        if b["partes"]:
            b["pagina"] = round(pagina_apos(b, b["feitas"]))
        return b

    def todos(self):
        return [self.info(b["id"]) for b in self.cat]

    def _u(self, bid):
        return self.d["livros"].setdefault(str(bid), {})

    def lendo(self):
        ativos = [b for b in self.todos() if b["status"] == "lendo" and not b["paralela"]]
        return sorted(ativos, key=lambda b: (-b["peso"], b["id"]))

    def comecar(self, bid, hoje):
        u = self._u(bid)
        u["status"] = "lendo"
        u.setdefault("inicio", hoje.isoformat())
        u.pop("fim", None)

    def concluir(self, bid, hoje, auto_proximo=True):
        u = self._u(bid)
        u["status"] = "lido"
        u["fim"] = hoje.isoformat()
        b = self.info(bid)
        u["pagina"] = b["paginas"]
        iniciado = None
        if auto_proximo and not b["paralela"]:
            iniciado = self.preencher_vagas(hoje)
        return iniciado

    def voltar_fila(self, bid):
        u = self._u(bid)
        u["status"] = "fila"
        u.pop("fim", None)

    def proximo_da_fila(self, ativos_tipos):
        fila = [b for b in self.todos() if b["status"] == "fila" and not b["paralela"]]
        if not fila:
            return None
        # mantem sempre ao menos um livro de literatura/historia em andamento
        if "L" not in ativos_tipos:
            for b in fila:
                if b["tipo"] == "L":
                    return b
        return fila[0]

    def preencher_vagas(self, hoje):
        iniciados = []
        maxs = int(self.d["config"].get("max_simultaneos", 3))
        while len(self.lendo()) < maxs:
            prox = self.proximo_da_fila([b["tipo"] for b in self.lendo()])
            if not prox:
                break
            self.comecar(prox["id"], hoje)
            iniciados.append(prox)
        return iniciados

    # --- ritmo -------------------------------------------------------------
    def ritmo(self, tipo):
        return float(self.d["config"].get(f"ritmo_{tipo}", CONFIG_PADRAO[f"ritmo_{tipo}"]))

    def calibrar(self, tipo, paginas, minutos):
        if paginas <= 0 or minutos < 10:
            return
        obs = max(0.1, min(3.0, paginas / minutos))
        atual = self.ritmo(tipo)
        self.d["config"][f"ritmo_{tipo}"] = round(0.7 * atual + 0.3 * obs, 3)

    # --- dias --------------------------------------------------------------
    def dia(self, d):
        return self.d["dias"].get(d.isoformat())

    def media_minutos(self, hoje, janela=28):
        """Media de minutos/dia nas ultimas semanas (dias sem registro contam 0)."""
        criado = date.fromisoformat(self.d.get("criado_em", hoje.isoformat()))
        dias = []
        for i in range(1, janela + 1):
            d = hoje - timedelta(days=i)
            if d < criado:
                break
            reg = self.dia(d) or {}
            dias.append(int(reg.get("minutos", 0)) if reg.get("feito") else 0)
        reg_hoje = self.dia(hoje) or {}
        if reg_hoje.get("feito"):
            dias.append(int(reg_hoje.get("minutos", 0)))
        if len(dias) < 7:
            return float(self.d["config"].get("min_previsao", 30)), len(dias), False
        return max(5.0, sum(dias) / len(dias)), len(dias), True

    def sequencia(self, hoje):
        """Dias seguidos com leitura (hoje conta se ja marcado; senao, a partir de ontem)."""
        n, d = 0, hoje
        if not (self.dia(hoje) or {}).get("feito"):
            d = hoje - timedelta(days=1)
        while (self.dia(d) or {}).get("feito"):
            n += 1
            d -= timedelta(days=1)
        return n

    def minutos_por_livro(self, hoje, janela=21):
        tot = {}
        for i in range(1, janela + 1):
            reg = self.dia(hoje - timedelta(days=i)) or {}
            if reg.get("feito"):
                for k, v in (reg.get("sessoes") or {}).items():
                    tot[int(k)] = tot.get(int(k), 0) + int(v)
        return tot


# ----------------------------------------------------------------------------
# Partes (cantos, capitulos)

def tamanhos(b):
    """Paginas de cada parte do livro (lista vazia se o livro nao tem sumario)."""
    partes = b.get("partes") or []
    if not partes:
        return []
    pgs = [p.get("pg") for p in partes]
    if all(isinstance(x, int) for x in pgs):
        out = [max(1, pgs[i + 1] - pgs[i]) for i in range(len(pgs) - 1)]
        out.append(max(1, b["paginas"] - pgs[-1] + 1))
        return out
    W = sum(float(p.get("w", 1) or 1) for p in partes)
    return [b["paginas"] * float(p.get("w", 1) or 1) / W for p in partes]


def pagina_apos(b, n):
    """Pagina em que o leitor esta depois de terminar as n primeiras partes."""
    partes = b.get("partes") or []
    if not partes:
        return b.get("pagina", 0)
    if n >= len(partes):
        return b["paginas"]
    pg0 = partes[0].get("pg")
    if isinstance(pg0, int) and all(isinstance(p.get("pg"), int) for p in partes):
        return partes[n]["pg"] - 1
    return sum(tamanhos(b)[:n])


def minutos_parte(b, idx, ritmo):
    """Minutos estimados para ler a parte idx (arredondado de 5 em 5, minimo 5)."""
    t = tamanhos(b)[idx] / max(0.05, ritmo)
    return max(5, int(5 * round(t / 5)))


def ler_sumario(texto):
    """Converte um sumario colado (uma parte por linha) em lista de partes.

    'Canto I ........ 13' -> {"t": "Canto I", "pg": 13}. Se nenhuma linha tiver
    numero de pagina no fim, as partes ficam com tamanho igual.
    """
    import re
    partes = []
    for ln in texto.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        m = re.match(r"^(.*?)(?:\s*(?:\.{2,}|…+|·|\||\t|_{2,})\s*|\s{2,}|\s+[-–—]\s+|,?\s+p\.\s*)(\d{1,4})\s*$", ln)
        if m and m.group(1).strip():
            partes.append({"t": m.group(1).strip(" .·…-—|\t")[:120], "pg": int(m.group(2))})
        else:
            partes.append({"t": ln[:120], "pg": None})
    if partes and all(isinstance(p["pg"], int) for p in partes):
        partes.sort(key=lambda p: p["pg"])
    elif partes:
        partes = [{"t": p["t"], "w": 1} for p in partes]
    return partes


# ----------------------------------------------------------------------------
# Plano do dia

def planejar(ativos, minutos, historico, ritmo):
    """Escolhe o que ler hoje respeitando partes inteiras.

    Livros com sumario recebem partes inteiras (cantos, capitulos): nunca se
    para no meio. Livros sem sumario recebem blocos de 15 min. A cada passo, a
    proxima leitura vai para o livro mais "atrasado" (parte justa pelo peso
    menos minutos ja recebidos nos ultimos dias), desde que caiba no tempo do
    dia (com folga de 15%). A primeira leitura do dia entra mesmo que passe do
    tempo, para nunca sobrar um dia sem nada.

    Retorna (blocos {id: minutos}, partes {id: [indices]}).
    """
    if not ativos:
        return {}, {}
    W = sum(b["peso"] for b in ativos)
    rec = {b["id"]: float(historico.get(b["id"], 0)) for b in ativos}
    prox = {b["id"]: b.get("feitas", 0) for b in ativos}
    blocos, partes = {}, {}
    total = 0
    limite = minutos * 1.15 + 2

    def proxima(b):
        if b.get("partes"):
            i = prox[b["id"]]
            if i >= len(b["partes"]):
                return None
            return minutos_parte(b, i, ritmo(b["tipo"]))
        return 15

    for _ in range(60):
        soma = sum(rec.values())
        ordem = sorted(ativos, key=lambda b: (-(b["peso"] / W * (soma + 15) - rec[b["id"]]), -b["peso"], b["id"]))
        escolha = None
        for b in ordem:
            dur = proxima(b)
            if dur is not None and (total == 0 or total + dur <= limite):
                escolha = (b, dur)
                break
        if not escolha:
            break
        b, dur = escolha
        bid = b["id"]
        blocos[bid] = blocos.get(bid, 0) + dur
        rec[bid] += dur
        total += dur
        if b.get("partes"):
            partes.setdefault(bid, []).append(prox[bid])
            prox[bid] += 1
        if total >= minutos:
            break
    return blocos, partes


def dividir(ativos, minutos, historico, ritmo=None):
    """Compatibilidade: so os minutos por livro."""
    return planejar(ativos, minutos, historico, ritmo or (lambda t: 0.75 if t == "L" else 0.5))[0]


# ----------------------------------------------------------------------------
# Previsao

def simular(est, min_dia, inicio, limite_anos=80):
    """Simula a leitura dia a dia e devolve {id: {"inicio": date, "fim": date}}.

    - min_dia minutos por dia, divididos entre os livros em andamento pelo peso;
    - quando um livro termina, entra o proximo da fila (mantendo ao menos um de
      literatura/historia em andamento), ate max_simultaneos;
    - paginas por minuto conforme o ritmo calibrado de cada tipo.
    """
    todos = [b for b in est.todos() if not b["paralela"]]
    out = {}
    for b in todos:
        if b["status"] == "lido":
            fim = date.fromisoformat(b["fim"]) if b.get("fim") else None
            ini = date.fromisoformat(b["inicio"]) if b.get("inicio") else fim
            out[b["id"]] = {"inicio": ini, "fim": fim, "lido": True}
    ativos = []
    for b in sorted([b for b in todos if b["status"] == "lendo"], key=lambda b: (-b["peso"], b["id"])):
        ativos.append({"id": b["id"], "tipo": b["tipo"], "peso": b["peso"],
                       "resta": max(0.0, b["paginas"] - b["pagina"])})
        out[b["id"]] = {"inicio": date.fromisoformat(b["inicio"]) if b.get("inicio") else inicio}
    fila = [b for b in todos if b["status"] == "fila"]
    maxs = int(est.d["config"].get("max_simultaneos", 3))
    rit = {"L": est.ritmo("L"), "P": est.ritmo("P")}
    min_dia = max(1.0, float(min_dia))

    def puxar(dia):
        while len(ativos) < maxs and fila:
            tipos = {a["tipo"] for a in ativos}
            idx = 0
            if "L" not in tipos:
                idx = next((i for i, b in enumerate(fila) if b["tipo"] == "L"), 0)
            b = fila.pop(idx)
            ativos.append({"id": b["id"], "tipo": b["tipo"], "peso": 1, "resta": float(b["paginas"])})
            out[b["id"]] = {"inicio": dia}

    dia = inicio
    puxar(dia)
    fim_limite = inicio + timedelta(days=365 * limite_anos)
    while ativos and dia < fim_limite:
        W = sum(a["peso"] for a in ativos)
        terminados = []
        for a in ativos:
            a["resta"] -= min_dia * a["peso"] / W * rit[a["tipo"]]
            if a["resta"] <= 0:
                terminados.append(a)
        for a in terminados:
            ativos.remove(a)
            out[a["id"]]["fim"] = dia
        dia += timedelta(days=1)
        if terminados:
            puxar(dia)
    return out


def fim_de(previsao, ids):
    fins = [previsao.get(i, {}).get("fim") for i in ids]
    if not fins or any(f is None for f in fins):
        return None
    return max(fins)
