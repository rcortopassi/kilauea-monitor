"""Inspeciona como o site no PythonAnywhere serve /calculadoras/.

Roda no GitHub Actions (unico lugar com o PA_TOKEN). Imprime apenas
informacoes ja publicas (config de rotas estaticas e HTML de paginas
publicas) - nada de codigo-fonte de app ou segredo.
"""
import json
import os
import sys
from urllib.request import Request, urlopen

PA_API = "https://www.pythonanywhere.com"
PA_USER = os.environ.get("PA_USER", "rafaelcortopassi")
PA_TOKEN = os.environ["PA_TOKEN"]
HEAD = {"Authorization": f"Token {PA_TOKEN}"}


def get(url):
    with urlopen(Request(url, headers=HEAD), timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def main():
    print("== webapps ==")
    apps = json.loads(get(f"{PA_API}/api/v0/user/{PA_USER}/webapps/"))
    for app in apps:
        print(json.dumps({k: app.get(k) for k in ("domain_name", "source_directory", "working_directory", "python_version")}, indent=2))
        dom = app["domain_name"]
        try:
            sf = get(f"{PA_API}/api/v0/user/{PA_USER}/webapps/{dom}/static_files/")
            print("static_files:", sf)
        except Exception as e:  # noqa: BLE001
            print("static_files erro:", e)

    print("\n== ls /home/%s/calculadoras/ ==" % PA_USER)
    try:
        print(get(f"{PA_API}/api/v0/user/{PA_USER}/files/tree/?path=/home/{PA_USER}/calculadoras"))
    except Exception as e:  # noqa: BLE001
        print("erro:", e)

    print("\n== index.html de /calculadoras/ (pagina publica) ==")
    for cand in (f"/home/{PA_USER}/calculadoras/index.html",):
        try:
            print(get(f"{PA_API}/api/v0/user/{PA_USER}/files/path{cand}"))
        except Exception as e:  # noqa: BLE001
            print(cand, "erro:", e)

    print("\n== outras paginas html em /calculadoras/ ==")
    try:
        tree = json.loads(get(f"{PA_API}/api/v0/user/{PA_USER}/files/tree/?path=/home/{PA_USER}/calculadoras"))
        for p in tree:
            if p.endswith(".html") and not p.endswith("index.html"):
                print(f"\n---- {p} (primeiros 6000 chars) ----")
                print(get(f"{PA_API}/api/v0/user/{PA_USER}/files/path{p}")[:6000])
    except Exception as e:  # noqa: BLE001
        print("erro:", e)


if __name__ == "__main__":
    sys.exit(main())
