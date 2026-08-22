# Radar de Ofertas Mercado Livre + Shopee + Amazon -> Telegram

Bot que monitora as paginas de ofertas do Mercado Livre, Shopee e Amazon,
extrai produtos com desconto, captura o link de afiliado de cada um
(Compartilhar no ML, portal de afiliados na Shopee, SiteStripe na Amazon)
e publica automaticamente num canal do Telegram. Ao iniciar, voce escolhe
qual(is) site(s) rodar (um, alguns ou todos).

Status: **em producao**, seletores dos 3 sites calibrados e validados
contra o site real. Ver [`SPEC.md`](SPEC.md) para a especificacao completa
(arquitetura, fluxo de dados, tratamento de erros, riscos).

**3 formas de rodar** (todas usam o mesmo motor por baixo — ver
`src/radar/scheduler.py`):

| Forma | Uso | Guia |
|---|---|---|
| `python main.py` | Linha de comando, loop continuo, pergunta qual(is) site(s) | secao 6 abaixo |
| `python gui.py` | Interface grafica desktop, mesmo loop | secao 6 abaixo |
| API HTTP (Java) | Disparar ciclos sob demanda, consultar produtos capturados, mandar mensagem avulsa | [API HTTP](#api-http-backend-java-opcional) abaixo |

Nas 3 formas, o pre-requisito e o mesmo: Chrome aberto manualmente com
debug port (secao 1).

## Como funciona

O script NAO abre nem loga um navegador sozinho. Ele se conecta a um Chrome
que voce ja abriu manualmente e ja esta logado, via Chrome DevTools
Protocol, nas contas dos sites que for rodar:

- **Mercado Livre**: conta com afiliacao ativa.
- **Shopee**: conta normal + login no portal de afiliados
  (`affiliate.shopee.com.br`), na mesma janela.
- **Amazon**: conta com Amazon Associates ativo (a barra SiteStripe, usada
  pra capturar o link de afiliado, so aparece nesse caso).

Se for rodar so alguns desses sites, so precisa estar logado nas contas
deles.

## 1. Abrir o Chrome com debug port

Feche todas as janelas do Chrome antes. Depois, no PowerShell:

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="C:\Users\INTEL\ChromeDebugProfile"
```

Na primeira vez, faca login manualmente nas contas dos sites que for usar
(ver secao acima) dentro dessa janela. Como o `--user-data-dir` e
persistente, o login fica salvo entre reinicializacoes — nas proximas
vezes so precisa abrir o Chrome com esse mesmo comando.

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
- `OFFERS_URL` / `SHOPEE_OFFERS_URL` / `AMAZON_OFFERS_URL`: (opcional) URL
  da pagina de ofertas de cada site, ja vem com um default sensato em
  `.env.example`.

## 4. Seletores (ja calibrados, so mexer se o site mudar)

`src/radar/selectors.py` ja esta calibrado contra o DOM real dos 3 sites
(ultima calibracao: ML 2026-08-18, Shopee e Amazon 2026-08-19). Se um
site mudar de layout e o bot comecar a extrair 0 ofertas ou nao achar o
link de afiliado, recalibre com o Chrome debug aberto, logado no site em
questao:

```powershell
python scripts/inspect_offers.py           # Mercado Livre
python scripts/inspect_shopee_offers.py    # Shopee
python scripts/inspect_amazon_offers.py    # Amazon
```

Cada script imprime quantos cards foram encontrados e os dados dos
primeiros produtos; passando um ID de produto como argumento (ver
docstring de cada script), testa tambem a resolucao do link de afiliado
daquele produto especifico. Se vier "NAO ENCONTRADO" ou contagem 0, abra o
DevTools do proprio Chrome (F12) na pagina de ofertas e no botao/fluxo de
afiliado do produto, inspecione os elementos reais e ajuste as constantes
em `selectors.py` (detalhes de cada seletor e por que ele existe estao
documentados em `SPEC.md`, secoes 6/6b/6c).

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

Janela com seletor de site (Mercado Livre / Shopee / Amazon / Todos),
botao Iniciar/Parar, campo de intervalo em horas (padrao 4h), contagem
regressiva ate a proxima verificacao e log ao vivo.

**Linha de comando**:

```powershell
python main.py
```

Pergunta qual(is) site(s) rodar (mesmas 4 opcoes da GUI) e roda em loop
continuo, checando a pagina de ofertas de cada site escolhido a cada
`CHECK_INTERVAL_SECONDS` (padrao 14400s = 4h), evitando repostar produtos ja
enviados (controle em `data/posted_products.db`, chave prefixada por site).
`Ctrl+C` encerra graciosamente.

## API HTTP (backend Java, opcional)

Alem de CLI e GUI, existe uma API REST (`backend/`, Spring Boot) que
controla o `main.py` como subprocesso — util pra disparar ciclos sob
demanda (em vez do loop fixo de `CHECK_INTERVAL_SECONDS`), escolher
sites/quantidade/canal por chamada, e consultar os produtos ja
capturados sem abrir o SQLite na mao.

```powershell
cd backend
mvn spring-boot:run
```

Abre `http://localhost:8080` (redireciona pro Swagger, com todos os
endpoints documentados e testaveis ali mesmo). Mesmo pre-requisito das
outras 2 formas: Chrome de debug aberto (secao 1).

Endpoints principais — detalhes completos em [`backend/README.md`](backend/README.md):

- `POST /api/radar/run` — dispara 1 ciclo (`main.py --once`) com
  `sites`/`quantity`/`channel` escolhidos na chamada.
- `GET /api/radar/status` / `POST /api/radar/stop` — acompanha ou
  interrompe a execucao atual.
- `GET /api/products/recent` / `GET /api/products/queue-stats` — le o
  que ja foi capturado (SQLite), sem rodar nada.
- `POST /api/telegram/message` — manda uma mensagem avulsa (nao ligada a
  oferta nenhuma) pro Telegram.

Essa API nao substitui `main.py`/`gui.py` nem muda o comportamento deles
— e so mais uma forma de disparar o mesmo motor (`scheduler`/`pipeline`)
de fora, via HTTP. `WHATSAPP` ja aparece como opcao de canal na API mas
retorna erro (ainda nao implementado no lado Python).

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
  config.py                     configuracao via .env
  browser.py                    conexao ao Chrome via CDP
  selectors.py                  seletores CSS (ajustar aqui se um site mudar)
  sites.py                      registry SiteConfig (ML/Shopee/Amazon)
  scraper/offers_page.py        listagem de ofertas do ML
  scraper/product_page.py       link de afiliado do ML via Compartilhar
  scraper/shopee_offers_page.py listagem de ofertas relampago da Shopee
  scraper/shopee_affiliate.py   link de afiliado via portal Shopee
  scraper/amazon_offers_page.py listagem das ofertas do dia da Amazon
  scraper/amazon_affiliate.py   link de afiliado via SiteStripe (Amazon)
  parsing.py                    parsing de preco/desconto/ID por site
  formatter.py                  template da mensagem do Telegram
  telegram_client.py            envio via Telegram Bot API
  dedup.py                      deduplicacao persistente (SQLite)
  queue_repo.py                 fila compartilhada entre sites (SQLite)
  pipeline.py                   descoberta + processamento da fila
  scheduler.py                  loop continuo com retry/backoff
scripts/inspect_offers.py          calibracao manual de seletores (ML)
scripts/inspect_shopee_offers.py   calibracao manual de seletores (Shopee)
scripts/inspect_amazon_offers.py   calibracao manual de seletores (Amazon)
backend/                           API HTTP (Spring Boot) que controla main.py como subprocesso — ver backend/README.md
SPEC.md                            especificacao completa do app (arquitetura, fluxo, riscos)
```

## Riscos e limitacoes

- **Anti-bot do Mercado Livre**: mesmo com sessao logada, o site pode ter
  rate limiting ou captcha. O bot usa jitter aleatorio entre acoes e nao roda
  headless, mas nao ha garantia contra bloqueio.
- **Anti-bot da Shopee e mais agressivo**: a 1a navegacao automatizada pra
  `flash_sale` pode ser redirecionada pra um captcha; resolver manualmente
  uma vez (janela visivel) libera a sessao pras chamadas seguintes (ver
  `SPEC.md`, secao 10).
- **Amazon depende de sessao Associates ativa**: a barra SiteStripe usada
  pra capturar o link de afiliado so aparece se a conta logada tiver Amazon
  Associates ativo.
- **Termos dos programas de afiliados**: revise as regras de cada programa
  (ML, Shopee, Amazon) antes de operar em escala — publicacao automatizada
  pode ter restricoes especificas (spam, disclosure de afiliacao, etc).
- **Seletores frageis**: qualquer redesign de uma pagina de ofertas ou do
  fluxo de captura de link de afiliado pode quebrar a extracao daquele
  site. Ajuste `selectors.py` quando isso acontecer (scripts de inspecao
  acima ajudam a recalibrar); o bot alerta via Telegram quando um site
  extrai 0 produtos.
- **Fallback de clipboard do SO**: usado por ML, Shopee e Amazon como
  ultimo recurso pra ler o link de afiliado; exige que a janela do Chrome
  esteja visivel (nao minimizada) na sessao do Windows.
