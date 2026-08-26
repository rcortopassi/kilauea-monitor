"""Publica os arquivos de calculadoras/ em /home/<user>/calculadoras/ no
PythonAnywhere, via API de arquivos (mesmo mecanismo do monitor do Kilauea).
"""
import glob
import os
import sys
import time
import uuid
from urllib.request import Request, urlopen

PA_API = "https://www.pythonanywhere.com"
PA_USER = os.environ.get("PA_USER", "rafaelcortopassi")
PA_TOKEN = os.environ["PA_TOKEN"]


def upload(local, nome):
    dest = f"/home/{PA_USER}/calculadoras/{nome}"
    url = f"{PA_API}/api/v0/user/{PA_USER}/files/path{dest}"
    with open(local, "rb") as f:
        data = f.read()
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
                print(f"publicado ({r.getcode()}): {dest}")
                return
        except Exception as e:  # noqa: BLE001
            if tent < 3:
                print(f"tentativa {tent} falhou ({e}); repetindo")
                time.sleep(5 * tent)
            else:
                raise


def main():
    arquivos = sorted(glob.glob("calculadoras/*.html"))
    if not arquivos:
        print("nada a publicar")
        return 0
    for a in arquivos:
        upload(a, os.path.basename(a))
    return 0


if __name__ == "__main__":
    sys.exit(main())
