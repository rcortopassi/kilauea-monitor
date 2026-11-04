# Biblioteca — plano de leitura diário

Site em https://rafaelcortopassi.pythonanywhere.com/biblioteca/

- **Hoje**: quantos minutos ler (15 a 60, conforme a agenda do dia), o melhor
  horário livre, como dividir o tempo entre os livros em andamento, e os botões
  "Li hoje" / "Não li hoje".
- **Livros**: os 317 livros na ordem combinada, com as opções começar, marcar
  como lido, voltar para a fila, corrigir páginas e prioridade.
- **Previsão**: data prevista de término de cada livro, de cada fase, de cada
  tipo, do CESG e da estante inteira, mais cenários de 15/30/45/60 min por dia.
- **Ajustes**: endereço iCal secreto do Google Agenda (entrada), feed `.ics`
  para assinar no Google Agenda (saída), ritmo de leitura e senha.

## Como funciona

- Código: `estante/` (Python puro, sem dependências). Catálogo e páginas
  estimadas em `estante/catalogo.py`.
- Dados: `/home/rafaelcortopassi/biblioteca_app/dados/estado.json` no
  PythonAnywhere (o deploy nunca mexe nesse arquivo).
- Deploy: `.github/workflows/biblioteca-deploy.yml` roda `deploy.py` a cada push
  que altera `leituras/`. Na primeira vez, ele acrescenta ao WSGI do web app um
  bloco que monta o site em `/biblioteca` (com cópia de segurança do WSGI
  original e reversão automática se algo falhar).

## Rodar localmente

```
cd leituras
python3 -c "from wsgiref.simple_server import make_server; from estante.web import montar; \
make_server('127.0.0.1', 8000, montar(lambda e, s: [], '/biblioteca', 'dados')).serve_forever()"
```

e abra http://127.0.0.1:8000/biblioteca/ (o cookie de login é `Secure`; use um
navegador que aceite cookies seguros em localhost).
