# Monitor do Kilauea

Verifica o status do vulcao Kilauea (Big Island, Havai) a cada 5 minutos e:

- manda push urgente via ntfy.sh quando o alerta sobe para ORANGE/RED
  (episodio de fonte de lava comecando);
- publica uma pagina de status em https://rafaelcortopassi.pythonanywhere.com/kilauea/

Fonte dos dados: API publica HANS do USGS (Hawaiian Volcano Observatory).
Roda inteiramente no GitHub Actions; nenhuma maquina local envolvida.

## Secrets necessarios (Settings > Secrets and variables > Actions)

- `NTFY_TOPIC` - topico do ntfy.sh para os pushes
- `PA_TOKEN` - token da API do PythonAnywhere

## Rodar na mao

```
NTFY_TOPIC=... PA_TOKEN=... python3 monitor.py
```

O estado fica em `state/state.json` e o historico de mudancas de nivel em
`state/history.json`, commitados pelo proprio workflow.
