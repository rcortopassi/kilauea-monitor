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

    def _ler(self):
        try:
            with open(self.arquivo, encoding="utf-8") as f:
                d = json.load(f)
        except FileNotFoundError:
            d = self._novo()
        cfg = dict(CONFIG_PADRAO)
        cfg.update(d.get("config", {}))
        d["config"] = cfg
        d.setdefault("livros", {})
        d.setdefault("dias", {})
        return d

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
# Plano do dia: divide os minutos em blocos de 15 entre os livros em andamento

def dividir(ativos, minutos, historico):
    """Distribui blocos de 15 min pelos livros, compensando quem ficou para tras.

    Cada livro tem um peso (prioridade). Bloco a bloco, vai para o livro com o
    maior "deficit" = parte justa (pelo peso) - minutos ja recebidos.
    """
    if not ativos:
        return {}
    blocos = max(1, minutos // 15)
    W = sum(b["peso"] for b in ativos)
    rec = {b["id"]: historico.get(b["id"], 0) for b in ativos}
    plano = {b["id"]: 0 for b in ativos}
    for _ in range(blocos):
        total = sum(rec.values()) + 15
        melhor = max(ativos, key=lambda b: (b["peso"] / W * total - rec[b["id"]], b["peso"], -b["id"]))
        rec[melhor["id"]] += 15
        plano[melhor["id"]] += 15
    resto = minutos - blocos * 15
    if resto > 0:
        primeiro = max(plano, key=lambda k: plano[k])
        plano[primeiro] += resto
    return {k: v for k, v in plano.items() if v > 0}


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
