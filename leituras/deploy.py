#!/usr/bin/env python3
"""Publica o site /biblioteca/ no PythonAnywhere (roda no GitHub Actions).

1. Confere o web app e os mapeamentos de arquivos estaticos (para nao expor
   os dados do site como arquivo estatico).
2. Sobe o codigo para /home/<user>/biblioteca_app/estante/ (os dados ficam em
   /home/<user>/biblioteca_app/dados/ e nunca sao tocados pelo deploy).
3. Na primeira vez, acrescenta ao arquivo WSGI do web app um bloco que monta
   o site em /biblioteca (o resto do site continua igual). Guarda uma copia do
   WSGI original antes.
4. Recarrega o web app e testa. Se /biblioteca/ nao responder ou o resto do
   site piorar, restaura o WSGI original, recarrega e falha.

Os logs deste repositorio sao publicos: nada de conteudo de arquivos nos prints.
Variaveis: PA_TOKEN (obrigatoria), PA_USER (default rafaelcortopassi).
"""
import os
import sys
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

TOKEN = os.environ.get("PA_TOKEN", "")
USER = os.environ.get("PA_USER", "rafaelcortopassi")
API = "https://www.pythonanywhere.com/api/v0/user/" + USER
DOMINIO = f"{USER}.pythonanywhere.com"
BASE = f"/home/{USER}/biblioteca_app"
WSGI = f"/var/www/{DOMINIO.replace('.', '_')}_wsgi.py"
PREFIXO = "/biblioteca"
INICIO, FIM = "# >>> biblioteca (site de leituras; gerado por leituras/deploy.py)", "# <<< biblioteca"
BLOCO = f"""
{INICIO}
try:  # um erro aqui nunca pode derrubar o resto do site
    import sys as _bib_sys
    if {BASE!r} not in _bib_sys.path:
        _bib_sys.path.insert(0, {BASE!r})
    from estante.web import montar as _bib_montar
    application = _bib_montar(application, {PREFIXO!r})
except Exception:
    import traceback as _bib_tb
    _bib_tb.print_exc()
{FIM}
"""


def api(metodo, caminho, corpo=None, tipo=None, url=None):
    req = Request(url or API + caminho, data=corpo, method=metodo,
                  headers={"Authorization": f"Token {TOKEN}", **({"Content-Type": tipo} if tipo else {})})
    for tent in range(4):
        try:
            with urlopen(req, timeout=90) as r:
                return r.status, r.read()
        except HTTPError as e:
            if e.code < 500 or tent == 3:
                return e.code, e.read()
        except Exception as e:  # noqa: BLE001
            if tent == 3:
                raise
            print(f"  rede falhou ({e}); tentando de novo")
        time.sleep(5 * (tent + 1))


def ler(caminho):
    st, corpo = api("GET", f"/files/path{caminho}")
    return corpo.decode("utf-8") if st == 200 else None


def escrever(caminho, conteudo):
    if isinstance(conteudo, str):
        conteudo = conteudo.encode("utf-8")
    b = "----bib" + uuid.uuid4().hex
    corpo = (f'--{b}\r\nContent-Disposition: form-data; name="content"; filename="x"\r\n'
             f"Content-Type: application/octet-stream\r\n\r\n").encode() + conteudo + f"\r\n--{b}--\r\n".encode()
    st, _ = api("POST", f"/files/path{caminho}", corpo, f"multipart/form-data; boundary={b}")
    if st not in (200, 201):
        sys.exit(f"ERRO: upload de {caminho} falhou (HTTP {st})")


def recarregar():
    st, _ = api("POST", f"/webapps/{DOMINIO}/reload/")
    print(f"reload do web app: HTTP {st}")
    time.sleep(8)
    return st == 200


def status_site(caminho):
    """Status HTTP publico (sem autenticacao) e um trecho do corpo."""
    try:
        req = Request(f"https://{DOMINIO}{caminho}", headers={"User-Agent": "biblioteca-deploy"})
        with urlopen(req, timeout=60) as r:
            return r.status, r.read(4000).decode("utf-8", "replace")
    except HTTPError as e:
        return e.code, ""
    except Exception:  # noqa: BLE001
        return 0, ""


def main():
    if not TOKEN:
        sys.exit("ERRO: PA_TOKEN nao definido")

    # 1. web app e mapeamentos estaticos
    st, corpo = api("GET", "/webapps/")
    if st != 200:
        sys.exit(f"ERRO: nao consegui listar os web apps (HTTP {st})")
    import json
    apps = {a["domain_name"]: a for a in json.loads(corpo)}
    if DOMINIO not in apps:
        sys.exit(f"ERRO: web app {DOMINIO} nao encontrado (existem: {', '.join(apps) or 'nenhum'})")
    print(f"web app {DOMINIO}: python {apps[DOMINIO].get('python_version')}")
    st, corpo = api("GET", f"/webapps/{DOMINIO}/static_files/")
    estaticos = json.loads(corpo) if st == 200 else []
    for m in estaticos:
        caminho = m.get("path", "").rstrip("/") + "/"
        if (BASE + "/").startswith(caminho):
            sys.exit("ERRO: um mapeamento de arquivos estaticos cobre a pasta do app; "
                     "os dados ficariam publicos. Abortando sem mudar nada.")
        if m.get("url", "").rstrip("/") == PREFIXO:
            sys.exit(f"ERRO: ja existe um mapeamento estatico em {PREFIXO}/. Abortando sem mudar nada.")
    print(f"mapeamentos estaticos conferidos ({len(estaticos)}): nenhum conflito")

    # 2. codigo
    pasta = Path(__file__).resolve().parent / "estante"
    for arq in sorted(pasta.glob("*.py")):
        escrever(f"{BASE}/estante/{arq.name}", arq.read_bytes())
        print(f"enviado estante/{arq.name}")

    # 3. WSGI
    original = ler(WSGI)
    if original is None:
        sys.exit(f"ERRO: nao consegui ler {WSGI}")
    if "application" not in original:
        sys.exit("ERRO: o WSGI atual nao define 'application'. Abortando sem mudar nada.")
    if INICIO in original and FIM in original:
        a, b = original.index(INICIO), original.index(FIM) + len(FIM)
        novo = original[:a].rstrip("\n") + "\n" + BLOCO.strip("\n") + "\n" + original[b:].lstrip("\n")
    else:
        novo = original.rstrip("\n") + "\n" + BLOCO
    antes_raiz, _ = status_site("/")
    print(f"site principal antes: HTTP {antes_raiz}")
    mudou_wsgi = novo != original
    if mudou_wsgi:
        escrever(f"{BASE}/wsgi_backup_{time.strftime('%Y%m%d-%H%M%S')}.py", original)
        escrever(WSGI, novo)
        print("WSGI atualizado (copia do original guardada em biblioteca_app/)")
    else:
        print("WSGI ja estava com o bloco da biblioteca")

    # 4. recarrega e testa
    recarregar()
    ok = False
    for _ in range(6):
        st_bib, corpo_bib = status_site(PREFIXO + "/login")
        ok = st_bib == 200 and "Biblioteca" in corpo_bib
        if ok:
            break
        time.sleep(10)
    depois_raiz, _ = status_site("/")
    print(f"/biblioteca/login: HTTP {st_bib}; site principal depois: HTTP {depois_raiz}")
    piorou = depois_raiz >= 500 and antes_raiz < 500
    if ok and not piorou:
        print(f"OK: https://{DOMINIO}{PREFIXO}/")
        return
    if mudou_wsgi:
        print("Falhou: restaurando o WSGI original")
        escrever(WSGI, original)
        recarregar()
    sys.exit("ERRO: o site da biblioteca nao respondeu como esperado (veja o log de erros do web app)")


if __name__ == "__main__":
    main()
