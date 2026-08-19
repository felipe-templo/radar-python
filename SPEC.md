# Spec — Radar de Ofertas Mercado Livre -> Telegram

Status: **em producao**. Calibrado e validado contra o site real em
2026-08-18. Documento descreve o app como construido, nao como planejado.

## 1. Objetivo

Monitorar `https://www.mercadolivre.com.br/ofertas`, extrair produtos com
desconto, obter o link de afiliado de cada um (via botao "Compartilhar" da
propria conta afiliada do usuario) e publicar automaticamente um anuncio
formatado (nome, de/por, % off, link) num grupo/canal do Telegram, em loop
continuo, sem repetir produto ja postado.

## 2. Escopo e nao-escopo

Dentro do escopo:
- Leitura da pagina de ofertas e extracao de cards de produto.
- Captura de link de afiliado real (nao um link generico do produto).
- Formatacao e envio de mensagem para um unico destino Telegram.
- Deduplicacao persistente entre execucoes/reinicios.
- Alertas de erro para um chat Telegram de admin (opcional).

Fora do escopo (nao implementado):
- Login/autenticacao automatizada no Mercado Livre — a sessao logada e
  responsabilidade do usuario, mantida manualmente num Chrome externo.
- Publicacao em outros canais (WhatsApp, Instagram, etc).
- Interface web ou CLI interativa — e um processo de longa duracao (`main.py`),
  sem UI.
- Deteccao/tratamento de CAPTCHA — o bot so evita agir de forma robotica
  (jitter), nao resolve bloqueios ativos.

## 3. Arquitetura

```
Chrome (aberto manualmente, logado, --remote-debugging-port=9222)
        |
        | Chrome DevTools Protocol (playwright.connect_over_cdp)
        v
scheduler.run_forever()  <-- loop infinito, reconecta se o Chrome cair
        |
        v
pipeline.run_cycle()  <-- 1 execucao completa
        |
        +--> scraper.offers_page.list_offers()      -> list[RawOfferCard]
        |
        +--> (por produto novo e com desconto minimo)
        |       scraper.product_page.get_affiliate_link()  -> str
        |
        +--> formatter.build_message()               -> texto HTML
        |
        +--> telegram_client.TelegramClient.send_offer()  -> POST Telegram API
        |
        +--> dedup.DedupRepository.mark_posted()      -> grava no SQLite
```

Processo unico, sincrono, single-thread. Sem fila, sem workers paralelos —
volume de produtos por ciclo e baixo o suficiente (`MAX_PRODUCTS_PER_CYCLE`,
default 15) para nao justificar concorrencia, e paralelizar abas do mesmo
Chrome aumentaria o risco de deteccao anti-bot.

## 4. Componentes (arquivo -> responsabilidade)

| Arquivo | Responsabilidade |
|---|---|
| `main.py` | Entrypoint: carrega config, configura logging, chama `run_forever` |
| `src/radar/config.py` | Le `.env` -> `Settings` (dataclass imutavel) |
| `src/radar/browser.py` | Conecta a um Chrome ja aberto via CDP; concede permissao de clipboard |
| `src/radar/selectors.py` | Constantes de seletores CSS/testid, unico lugar a editar se o site mudar |
| `src/radar/scraper/offers_page.py` | Le a listagem de ofertas, faz scroll incremental, extrai `RawOfferCard` |
| `src/radar/scraper/product_page.py` | Abre pagina do produto, clica Compartilhar, extrai o link de afiliado |
| `src/radar/parsing.py` | Parsing de preco (`R$ 1.234,56` -> `Decimal`), % desconto, ID do produto |
| `src/radar/models.py` | `RawOfferCard` (dado cru do card) e `Product` (dado final, com afiliado) |
| `src/radar/formatter.py` | Monta o texto HTML da mensagem do Telegram |
| `src/radar/telegram_client.py` | `sendPhoto`/`sendMessage` via Telegram Bot API (HTTP puro, com retry) |
| `src/radar/dedup.py` | Repositorio SQLite: `is_posted(id)` / `mark_posted(product)` |
| `src/radar/pipeline.py` | Orquestra um ciclo: lista, filtra, resolve afiliado, formata, envia, marca |
| `src/radar/scheduler.py` | Loop infinito, reconexao ao Chrome, backoff, alertas |
| `src/radar/exceptions.py` | `ChromeNotConnectableError`, `AffiliateLinkNotFoundError` |
| `scripts/inspect_offers.py` | Script manual pra recalibrar `selectors.py` quando o site mudar |

## 5. Fluxo de dados por produto

1. `list_offers` navega ate a URL de ofertas, faz scroll ate carregar
   `MAX_PRODUCTS_PER_CYCLE` cards (ou estabilizar), extrai por card: nome,
   URL, imagem, preco original, preco com desconto, % desconto (calculado
   se nao vier explicito no card).
2. Para cada card, na ordem em que aparece na pagina:
   - extrai `product_id` (regex `MLB-?\d+` na URL) — se falhar, pula;
   - se `product_id` ja esta no SQLite (`dedup.is_posted`), pula;
   - se `discount_percent < MIN_DISCOUNT_PERCENT`, pula;
   - chama `get_affiliate_link` (ver secao 6) — se falhar, loga erro e pula
     (fica disponivel pra tentar de novo no proximo ciclo);
   - monta `Product`, formata mensagem, envia (ou loga, se `DRY_RUN=true`);
   - marca como postado no SQLite;
   - dorme 2-5s (jitter) antes do proximo produto.
3. Ciclo processa no maximo `MAX_PRODUCTS_PER_CYCLE` produtos novos por
   execucao — mesmo que a pagina tenha mais ofertas, o excedente fica pra
   proximos ciclos.

## 6. Captura do link de afiliado (ponto critico do sistema)

Calibrado contra o DOM real em 2026-08-18. Passos:

1. Abre o produto numa nova aba do mesmo `BrowserContext` (reaproveita a
   sessao logada).
2. `page.goto(url, wait_until="load")` + espera fixa de 1s — **necessario**
   porque o botao Compartilhar so responde a clique depois que o React
   hidrata a pagina; com `wait_until="domcontentloaded"` o clique acontece
   cedo demais e o popup as vezes nao abre ou abre com estado de uma
   sessao anterior (bug real encontrado e corrigido nesta build).
3. Clica no botao Compartilhar (`get_by_role("button", name=~"ompartilhar")`
   com fallback pro seletor CSS `SEL.SHARE_BUTTON`).
4. `wait_for_selector` num seletor combinado dos dois elementos possiveis
   do popup (nao usa `[data-tippy-root]` generico — a pagina pode ter
   outros tooltips soltos no DOM que geram falso positivo).
5. Tenta extrair o link em camadas, na ordem:
   - **Camada 1**: `<textarea data-testid="text-field__label_link">` —
     popup "Gerar link / ID de produto", link curto `meli.la/...`. Variante
     observada como a mais comum.
   - **Camada 2**: `href` do `<a data-testid="share-on-click_COPY_LINK">`
     — popup social simples (WhatsApp/Copiar link/X/Facebook/E-mail); o
     href ja vem com `matt_tool=...` (parametro de afiliado) embutido, sem
     precisar clicar nem ler clipboard.
   - **Camada 3** (ultimo recurso): clica em "Copiar" e le
     `navigator.clipboard.readText()` via `page.evaluate`.
   - **Camada 4** (ultimo recurso): le o clipboard do sistema operacional
     via `pyperclip` — exige que a janela do Chrome esteja visivel/nao
     minimizada.
6. Todo valor candidato passa por `_looks_like_affiliate_link()` (regex
   `meli\.la/|mercadolivre\.com(\.br)?/sec/|matt_word=|matt_tool=`) antes
   de ser aceito — evita postar um link sem parametro de afiliado (sem
   comissao) mesmo que alguma camada retorne algo inesperado.
7. A aba e sempre fechada no `finally`, mesmo em erro.

## 7. Deduplicacao

SQLite (`data/posted_products.db`), tabela `posted_products` com
`product_id TEXT PRIMARY KEY`. Escolhido em vez de JSON por atomicidade
(escrita corrompida em crash no meio de um `INSERT` nao acontece com
`INSERT OR REPLACE` + `commit`) e custo de consulta O(log n) indexado. Nao
ha expiracao — um produto postado uma vez nunca e repostado, mesmo que o
desconto mude.

## 8. Configuracao (`.env`)

| Variavel | Obrigatoria | Default | Efeito |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | sim | - | Token do bot (BotFather) |
| `TELEGRAM_CHAT_ID` | sim | - | Destino das ofertas (canal/grupo, bot precisa ser admin) |
| `TELEGRAM_ADMIN_CHAT_ID` | nao | - | Destino dos alertas de erro; sem isso, alertas sao descartados silenciosamente |
| `CHROME_DEBUG_URL` | nao | `http://localhost:9222` | Endpoint CDP do Chrome ja aberto |
| `OFFERS_URL` | nao | pagina de ofertas do ML | URL alvo do scraping |
| `CHECK_INTERVAL_SECONDS` | nao | `300` | Intervalo entre ciclos |
| `MAX_PRODUCTS_PER_CYCLE` | nao | `15` | Teto de produtos novos processados por ciclo |
| `MIN_DISCOUNT_PERCENT` | nao | `10` | Filtro minimo de desconto pra postar |
| `DB_PATH` | nao | `data/posted_products.db` | Caminho do SQLite de dedup |
| `LOG_LEVEL` | nao | `INFO` | Nivel de log |
| `DRY_RUN` | nao | `false` | Se `true`, loga a mensagem em vez de enviar (mas ainda marca como postado) |

## 9. Tratamento de erros

| Cenario | Comportamento |
|---|---|
| Chrome nao conectavel (browser inteiro caiu/fechou) | `ChromeNotConnectableError`; reconecta a cada ciclo; apos 5 falhas seguidas, alerta ao admin e espera 15min extra |
| Aba de listagem fechada sem o browser cair (`TargetClosedError`) | A aba de listagem e aberta e fechada a cada ciclo (nao reaproveitada) especificamente para este caso — ver secao 11, bug corrigido |
| 0 ofertas extraidas (seletor quebrado) | Loga warning + alerta ao admin; ciclo termina sem postar nada |
| Link de afiliado nao encontrado num produto | Loga erro, pula so aquele produto (nao marca como postado — tenta de novo no proximo ciclo), continua o ciclo |
| Erro inesperado no ciclo | Loga stack trace completo, alerta ao admin, ciclo seguinte tenta de novo apos `CHECK_INTERVAL_SECONDS` |
| Falha ao enviar `sendPhoto` (imagem invalida/expirada) | Fallback automatico pra `sendMessage` sem imagem |
| `Ctrl+C` | Encerra o loop e fecha a conexao Playwright de forma limpa |

## 10. Riscos conhecidos (nao mitigados)

- **Anti-bot do Mercado Livre**: jitter aleatorio entre acoes reduz o
  padrao robotico, mas nao ha garantia contra rate limiting/captcha em uso
  prolongado ou intervalos muito curtos.
- **Termos do Programa de Afiliados**: publicacao automatizada em massa
  pode infringir regras especificas do programa (spam, disclosure). Nao
  verificado contra os termos oficiais — responsabilidade do operador.
- **Fragilidade de seletores**: qualquer redesign do site (grid de ofertas
  ou popup de compartilhamento) quebra a extracao. Reajustar em
  `selectors.py` usando `scripts/inspect_offers.py`.
- **Dependencia de janela visivel**: a Camada 4 (clipboard do SO) so
  funciona com a janela do Chrome nao minimizada; as camadas 1 e 2 (as
  mais usadas na pratica) nao tem essa restricao.
- **Sem rotacao/expiracao de dedup**: a base de produtos postados cresce
  indefinidamente (irrelevante em volume — poucos KB por milhares de
  produtos).

## 11. Validacao realizada

- 16 testes unitarios (`pytest`) cobrindo `parsing`, `formatter`, `dedup`.
- Ciclo completo executado contra a pagina real de ofertas, em `DRY_RUN`,
  validando extracao de 6 produtos distintos com link de afiliado unico
  cada um (bug de reuso de link entre produtos identificado e corrigido
  nesse processo — ver secao 6, passo 2).
- Ciclo real em producao (`DRY_RUN=false`) postou 15 ofertas no grupo
  Telegram configurado, com envio confirmado (HTTP 200 + `message_id` de
  retorno da API).
- **Bug encontrado e corrigido em producao**: `scheduler.py` reaproveitava
  uma unica aba (`page`) de listagem entre ciclos, criada so na
  (re)conexao ao Chrome. Quando essa aba especifica foi fechada (o browser
  em si continuou de pe), o proximo ciclo falhou com
  `playwright.TargetClosedError` no `page.goto` — e o loop nao detectava
  isso, porque so verificava `browser.is_connected()`. Corrigido fazendo
  `pipeline.run_cycle` abrir e fechar sua propria aba de listagem a cada
  ciclo (`context.new_page()` / `page.close()` dentro do proprio ciclo),
  mesmo padrao ja usado pra paginas de produto — nenhuma aba fica aberta
  por mais que a duracao de um ciclo.
