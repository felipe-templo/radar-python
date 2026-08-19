# Radar de Ofertas Mercado Livre -> Telegram

Bot que monitora a pagina de ofertas do Mercado Livre, extrai produtos com
desconto, captura o link de afiliado via botao "Compartilhar" e publica
automaticamente num canal do Telegram.

Status: **em producao**, seletores calibrados e validados contra o site
real. Ver [`SPEC.md`](SPEC.md) para a especificacao completa (arquitetura,
fluxo de dados, tratamento de erros, riscos).

## Como funciona

O script NAO abre nem loga um navegador sozinho. Ele se conecta a um Chrome
que voce ja abriu manualmente e ja esta logado na sua conta Mercado Livre
(com afiliacao ativa), via Chrome DevTools Protocol.

## 1. Abrir o Chrome com debug port

Feche todas as janelas do Chrome antes. Depois, no PowerShell:

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="C:\Users\INTEL\ChromeDebugProfile"
```

Na primeira vez, faca login manualmente na sua conta Mercado Livre (afiliada)
dentro dessa janela. Como o `--user-data-dir` e persistente, o login fica
salvo entre reinicializacoes — nas proximas vezes so precisa abrir o Chrome
com esse mesmo comando.

Verifique se a debug port esta ativa acessando:
`http://localhost:9222/json/version`

Deixe essa janela do Chrome aberta enquanto o bot estiver rodando.

## 2. Instalar dependencias

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt   # opcional, para rodar os testes
```

Nota: Python 3.14 e muito recente. Se `pip install` falhar por falta de
wheel pre-compilada de alguma dependencia, use Python 3.11 ou 3.12 (via
`pyenv-win` ou instalador oficial) para criar o venv.

## 3. Configurar `.env`

```powershell
copy .env.example .env
```

Edite `.env` com:
- `TELEGRAM_BOT_TOKEN`: crie um bot com o [@BotFather](https://t.me/BotFather) no Telegram.
- `TELEGRAM_CHAT_ID`: ID do canal/grupo onde o bot vai postar (adicione o bot como admin do canal).
- `TELEGRAM_ADMIN_CHAT_ID`: (opcional) seu chat_id pessoal, para receber alertas de erro.

## 4. Seletores (ja calibrados, so mexer se o site mudar)

`src/radar/selectors.py` ja esta calibrado contra o DOM real do Mercado
Livre (ultima calibracao: 2026-08-18). Se o site mudar de layout e o bot
comecar a extrair 0 ofertas ou nao achar o link de afiliado, recalibre com
o Chrome debug aberto na pagina de ofertas:

```powershell
python scripts/inspect_offers.py
```

Isso imprime quantos cards foram encontrados e os dados do primeiro card.
Se vier "NAO ENCONTRADO" ou contagem 0, abra o DevTools do proprio Chrome
(F12) na pagina de ofertas e no botao "Compartilhar" de um produto, inspecione
os elementos reais e ajuste as constantes em `selectors.py` (detalhes de
cada seletor e por que ele existe estao documentados em `SPEC.md`, secao 6).

## 5. Testar sem postar de verdade

No `.env`, defina `DRY_RUN=true` e rode uma vez:

```powershell
python main.py
```

As mensagens que seriam enviadas aparecem no log (`logs/radar.log` e console)
em vez de irem pro Telegram. Quando estiver satisfeito, mude para `DRY_RUN=false`.

## 6. Rodar em producao

Duas formas, mesma logica por baixo:

**Interface grafica** (recomendado):

```powershell
python gui.py
```

Janela com botao Iniciar/Parar, campo de intervalo em horas (padrao 4h),
contagem regressiva ate a proxima verificacao e log ao vivo.

**Linha de comando**:

```powershell
python main.py
```

Roda em loop continuo, checando a pagina de ofertas a cada
`CHECK_INTERVAL_SECONDS` (padrao 14400s = 4h), evitando repostar produtos ja
enviados (controle em `data/posted_products.db`). `Ctrl+C` encerra
graciosamente.

## Aviso: Chrome aberto por este agente

Se o Claude abriu o Chrome de debug pra voce (via comando no terminal desta
sessao), o processo do Chrome pode morrer junto quando essa sessao/terminal
fechar (ex: `/exit`), mesmo com `disown`. Pra operacao continua de verdade,
abra o Chrome voce mesmo, num terminal proprio seu, com o comando da secao
1 — assim ele fica independente de qualquer sessao de agente.

## Operacao continua

O bot depende do Chrome de debug estar de pe o tempo todo. Se voce fechar
essa janela do Chrome (ou ela crashar), o bot detecta a queda, tenta
reconectar, e apos 5 tentativas manda um alerta pro `TELEGRAM_ADMIN_CHAT_ID`
— mas nao reabre o Chrome sozinho. Se isso acontecer, reabra com o comando
da secao 1 (o profile persistente mantem o login) e o bot volta a
funcionar no ciclo seguinte, sem precisar reiniciar `main.py`.

## Rodar os testes

```powershell
pytest
```

## Estrutura

```
src/radar/
  config.py           configuracao via .env
  browser.py           conexao ao Chrome via CDP
  selectors.py          seletores CSS (ajustar aqui se o site mudar)
  scraper/offers_page.py    extracao da listagem de ofertas
  scraper/product_page.py   captura do link de afiliado via Compartilhar
  parsing.py            parsing de preco/desconto/ID
  formatter.py           template da mensagem do Telegram
  telegram_client.py       envio via Telegram Bot API
  dedup.py               deduplicacao persistente (SQLite)
  pipeline.py             orquestra um ciclo completo
  scheduler.py            loop continuo com retry/backoff
scripts/inspect_offers.py  script de calibracao manual de seletores
SPEC.md                    especificacao completa do app (arquitetura, fluxo, riscos)
```

## Riscos e limitacoes

- **Anti-bot do Mercado Livre**: mesmo com sessao logada, o site pode ter
  rate limiting ou captcha. O bot usa jitter aleatorio entre acoes e nao roda
  headless, mas nao ha garantia contra bloqueio.
- **Termos do Programa de Afiliados do Mercado Livre**: revise as regras do
  programa antes de operar em escala — publicacao automatizada pode ter
  restricoes especificas (spam, disclosure de afiliacao, etc).
- **Seletores frageis**: qualquer redesign da pagina de ofertas ou do modal
  de compartilhamento pode quebrar a extracao. Ajuste `selectors.py` quando
  isso acontecer; o bot alerta via Telegram quando extrai 0 produtos.
- **Fallback de clipboard do SO**: exige que a janela do Chrome esteja
  visivel (nao minimizada) na sessao do Windows.
