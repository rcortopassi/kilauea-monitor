"""Espelha o conteudo de /home/<user>/calculadoras/ do PythonAnywhere no log,
para o site poder ser editado de forma consistente (estilo, navegacao etc.).
Roda no GitHub Actions (unico lugar com o PA_TOKEN). Imprime apenas arquivos
do site estatico publico - nada de codigo de app nem segredo.
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
    base = f"{PA_API}/api/v0/user/{PA_USER}/files"
    tree = json.loads(get(f"{base}/tree/?path=/home/{PA_USER}/calculadoras"))
    for p in tree:
        if p.endswith("/"):
            continue
        print(f"\n=====ARQUIVO===== {p}")
        try:
            print(get(f"{base}/path{p}"))
        except Exception as e:  # noqa: BLE001
            print("erro:", e)
        print(f"=====FIM===== {p}")


if __name__ == "__main__":
    sys.exit(main())
