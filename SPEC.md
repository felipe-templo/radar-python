# Spec — Radar de Ofertas Mercado Livre + Shopee -> Telegram

Status: **em producao**. ML calibrado e validado contra o site real em
2026-08-18; Shopee calibrado e validado contra o site real em 2026-08-19
(listagem + resolucao de link de afiliado testadas de ponta a ponta, ver
secao 6b e secao 11). Documento descreve o app como construido, nao como
planejado.

## 1. Objetivo

Monitorar as paginas de ofertas relampago do Mercado Livre
(`https://www.mercadolivre.com.br/ofertas`) e da Shopee
(`https://shopee.com.br/flash_sale`), extrair produtos com desconto, obter
o link de afiliado de cada um e publicar automaticamente um anuncio
formatado (nome, de/por, % off, link, origem) num grupo/canal do Telegram,
em loop continuo, sem repetir produto ja postado. Ao iniciar, o usuario
escolhe qual(is) site(s) rodar (Mercado Livre, Shopee, ou ambos).

## 2. Escopo e nao-escopo

Dentro do escopo:
- Leitura da pagina de ofertas (ML e Shopee) e extracao de cards de produto.
- Captura de link de afiliado real (nao um link generico do produto) — via
  botao "Compartilhar" na propria pagina do produto (ML) ou via portal de
  afiliados `affiliate.shopee.com.br` (Shopee, ver secao 6b).
- Escolha interativa, ao iniciar (CLI `main.py` ou GUI `gui.py`), de qual(is)
  site(s) rodar nesta execucao.
- Formatacao e envio de mensagem para um unico destino Telegram (mesmo canal
  para os dois sites, com indicacao de origem na mensagem).
- Deduplicacao persistente entre execucoes/reinicios, por site (chave
  `{site}:{product_id}`, sem colisao entre marketplaces).
- Alertas de erro para um chat Telegram de admin (opcional).

Fora do escopo (nao implementado):
- Login/autenticacao automatizada no Mercado Livre/Shopee — a sessao logada
  e responsabilidade do usuario, mantida manualmente num Chrome externo
  (inclusive login no portal de afiliados Shopee).
- Publicacao em outros canais (WhatsApp, Instagram, etc).
- Interface web — so CLI interativa (`main.py`) e GUI desktop (`gui.py`).
- Deteccao/tratamento de CAPTCHA — o bot so evita agir de forma robotica
  (jitter), nao resolve bloqueios ativos.

## 3. Arquitetura

```
Chrome (aberto manualmente, logado no ML e na Shopee/portal de afiliados,
        --remote-debugging-port=9222)
        |
        | Chrome DevTools Protocol (playwright.connect_over_cdp)
        v
main.py / gui.py  <-- pergunta ao usuario qual(is) site(s) rodar
        |
        v
scheduler.run_forever(settings, sites)  <-- loop infinito, reconecta se o Chrome cair
        |
        v
scheduler.run_all_sites(...)  <-- 1 ciclo completo
        |
        +--(1) DESCOBERTA, por site, isolada ------------------------------
        |       pipeline.discover_offers(..., site)
        |         site.list_offers()  -> list[RawOfferCard]
        |         (scraper.offers_page ou scraper.shopee_offers_page)
        |         -> enfileira novos em queue_repo.OfferQueue (SQLite)
        |       erro num site aqui NAO impede a descoberta dos demais
        |       (try/except por site, ver secao 3b)
        |
        +--(2) PROCESSAMENTO, fila unica intercalada entre sites ---------
                pipeline.process_queue(...)
                  queue.next_batch(N)  -> itens intercalados round-robin
                  por item: site.get_affiliate_link()  -> str
                    (scraper.product_page ou scraper.shopee_affiliate)
                  -> formatter.build_message()          -> texto HTML (com origem)
                  -> telegram_client.send_offer()        -> POST Telegram API
                  -> dedup.mark_posted() + queue.mark_done()
                erro num item so afeta aquele item (queue.mark_failed,
                tenta de novo em ciclos futuros ate MAX_ATTEMPTS) - o loop
                sempre segue pro proximo item do lote, que por causa do
                intercalamento normalmente ja e de outro site
```

`src/radar/sites.py` define o registry `SiteConfig` (ML e Shopee), usado por
`pipeline`/`scheduler`/`main.py`/`gui.py` pra nao depender de um site fixo.

Processo unico, sincrono, single-thread — sem workers paralelos, sem abas
simultaneas do mesmo Chrome (paralelizar aumentaria o risco de deteccao
anti-bot, ja confirmado agressivo na Shopee, ver secao 10). "Paralelismo"
aqui e so o intercalamento logico da fila (secao 3b), nao execucao
concorrente de verdade.

## 3b. Fila (`src/radar/queue_repo.py`) e isolamento entre sites

Adicionada em 2026-08-19 pra dois problemas reais observados: (1) uma
excecao nao tratada processando um produto de um site podia escapar e
pular o(s) site(s) seguinte(s) no mesmo ciclo; (2) descoberta e
processamento ficavam presos juntos — um site lento pra resolver link de
afiliado atrasava a descoberta do proximo ciclo inteiro, inclusive dos
outros sites.

Solucao: separar "descobrir" (`discover_offers`, rapido — so lista e
enfileira) de "processar" (`process_queue`, lento — resolve afiliado e
posta), com uma fila SQLite compartilhada entre todos os sites
(`offer_queue`, tabela no mesmo arquivo de `DB_PATH`).

- `OfferQueue.enqueue(site_key, product_id, raw)` — `INSERT OR IGNORE` com
  `UNIQUE(site_key, product_id)`, idempotente (chamar de novo pra um item
  ja enfileirado nao duplica).
- `OfferQueue.next_batch(limit)` — retorna ate `limit` itens `pending`,
  **intercalados round-robin entre sites** (`ROW_NUMBER() OVER (PARTITION
  BY site_key ORDER BY enqueued_at)`, depois `ORDER BY rn, site_key`): 1
  item de cada site por vez, na ordem em que foram descobertos. Se um site
  nao tem itens pendentes (ex.: falhou na descoberta), o lote e preenchido
  inteiro pelos demais — nao "reserva" espaco vazio.
- `process_queue` itera o lote com `try/except` **por item** (nao por
  site): erro num item chama `queue.mark_failed` (volta pra `pending`,
  tenta de novo em ciclos futuros, ate `MAX_ATTEMPTS=5` — depois vira
  `failed` terminal, sai da fila de pendentes) e o loop `continue` pro
  proximo item do lote. Como o lote ja veio intercalado, esse proximo item
  normalmente ja e de outro site — e exatamente o requisito de "se um site
  cair, o outro comeca logo em seguida", garantido pela ordem do lote, sem
  precisar de logica extra de prioridade.
- `discover_offers` tambem e isolado por site em `run_all_sites` (try/except
  por site, ver secao 4), entao um site cuja pagina de listagem quebrar
  nao impede a descoberta dos demais.
- `batch_size` por ciclo = `MAX_PRODUCTS_PER_CYCLE * numero de sites
  rodando` — mantem a mesma ordem de grandeza de throughput por site que
  o comportamento anterior (sem fila), mas agora sem cap na descoberta:
  ofertas descobertas em excesso ficam `pending` na fila persistente
  (sobrevive a reinicios) em vez de dependerem de re-scraping incidental
  no proximo ciclo.
- Validado em 2026-08-19: ciclo real (ML + Shopee, `DRY_RUN=true`) — ML
  descobriu 44 ofertas e enfileirou 39, Shopee zerou (lentidao de
  carregamento nesse teste, ver secao 10), lote de 6 itens processado sem
  nenhum bloquear os demais (todos do ML, ja que Shopee nao tinha itens
  pra intercalar), alerta enviado pro site zerado, ciclo concluido
  normalmente.

## 4. Componentes (arquivo -> responsabilidade)

| Arquivo | Responsabilidade |
|---|---|
| `main.py` | Entrypoint CLI: carrega config, pergunta qual(is) site(s) rodar, configura logging, chama `run_forever` |
| `gui.py` | Entrypoint GUI (customtkinter): mesmo loop, com seletor de site(s) e botao iniciar/parar |
| `src/radar/config.py` | Le `.env` -> `Settings` (dataclass imutavel) |
| `src/radar/browser.py` | Conecta a um Chrome ja aberto via CDP; concede permissao de clipboard (ML e Shopee) |
| `src/radar/sites.py` | Registry `SiteConfig` (ML e Shopee): agrupa listagem, resolucao de afiliado e extracao de ID por site |
| `src/radar/selectors.py` | Constantes de seletores CSS/testid, unico lugar a editar se um site mudar |
| `src/radar/scraper/offers_page.py` | Le a listagem de ofertas do ML, faz scroll incremental, extrai `RawOfferCard` |
| `src/radar/scraper/product_page.py` | Abre pagina do produto ML, clica Compartilhar, extrai o link de afiliado |
| `src/radar/scraper/shopee_offers_page.py` | Le a listagem de ofertas relampago da Shopee, extrai `RawOfferCard` |
| `src/radar/scraper/shopee_affiliate.py` | Abre o item no portal de afiliados Shopee, clica Obter link, extrai o link |
| `src/radar/parsing.py` | Parsing de preco (`R$ 1.234,56` -> `Decimal`), % desconto, ID do produto (ML e Shopee) |
| `src/radar/models.py` | `RawOfferCard` (dado cru do card) e `Product` (dado final, com afiliado e `source`) |
| `src/radar/formatter.py` | Monta o texto HTML da mensagem do Telegram, com emoji/rotulo por origem |
| `src/radar/telegram_client.py` | `sendPhoto`/`sendMessage` via Telegram Bot API (HTTP puro, com retry) |
| `src/radar/dedup.py` | Repositorio SQLite: `is_posted(key)` / `mark_posted(product, dedup_key, ...)` |
| `src/radar/queue_repo.py` | `OfferQueue`: fila SQLite compartilhada entre sites, intercalada round-robin (ver secao 3b) |
| `src/radar/pipeline.py` | `discover_offers` (lista+filtra+enfileira, por site) e `process_queue` (drena fila, resolve afiliado, formata, envia, marca) |
| `src/radar/scheduler.py` | `run_all_sites` (descoberta isolada por site + drena fila) dentro do loop infinito de `run_forever`, reconexao ao Chrome, backoff, alertas |
| `src/radar/exceptions.py` | `ChromeNotConnectableError`, `AffiliateLinkNotFoundError` |
| `scripts/inspect_offers.py` | Script manual pra recalibrar `selectors.py` (ML) quando o site mudar |
| `scripts/inspect_shopee_offers.py` | Script manual pra recalibrar `selectors.py` (Shopee) quando o site mudar |

## 5. Fluxo de dados por produto

Dividido em duas fases (ver secao 3b), chamadas por `scheduler.run_all_sites`:

**Fase 1 — descoberta (`pipeline.discover_offers`), uma vez por site, isolada:**

1. `site.list_offers` navega ate a URL de ofertas do site, faz scroll ate
   carregar `MAX_PRODUCTS_PER_CYCLE` cards (ou estabilizar), extrai por
   card: nome, URL, imagem, preco original, preco com desconto, % desconto
   (calculado se nao vier explicito no card).
2. Para cada card, na ordem em que aparece na pagina:
   - extrai `product_id` via `site.extract_product_id` (regex `MLB-?\d+`
     pro ML, `-i\.\d+\.(\d+)` pra Shopee) — se falhar, pula;
   - se `discount_percent < MIN_DISCOUNT_PERCENT`, pula;
   - monta a chave de dedup `f"{site.key}:{product_id}"` e, se ja esta no
     SQLite (`dedup.is_posted`), pula (chave prefixada evita colisao entre
     IDs de sites diferentes);
   - enfileira em `OfferQueue` (`INSERT OR IGNORE`, sem limite de
     quantidade — todo produto novo elegivel e enfileirado).
3. Erro nessa fase pra um site (ex.: pagina de listagem quebrou) e
   capturado por `run_all_sites`, alerta e admin e segue pros demais
   sites — nao impede a descoberta deles.

**Fase 2 — processamento (`pipeline.process_queue`), uma vez por ciclo,
lote unico intercalado entre todos os sites:**

1. `queue.next_batch(MAX_PRODUCTS_PER_CYCLE * numero_de_sites)` — busca o
   lote, intercalado round-robin entre sites (ver secao 3b).
2. Para cada item do lote, na ordem do lote:
   - re-checa `dedup.is_posted` (defensivo — evita reprocessar algo que
     ja foi postado por fora entre o enfileiramento e o processamento);
   - chama `site.get_affiliate_link` (ver secao 6/6b) — se falhar, loga
     erro, `queue.mark_failed` (volta pra `pending`, tenta de novo em
     ciclos futuros ate `MAX_ATTEMPTS`) e segue pro proximo item do lote
     (de qualquer site);
   - monta `Product` (com `source=site.key`), formata mensagem, envia (ou
     loga, se `DRY_RUN=true`);
   - marca como postado no SQLite (`dedup.mark_posted`) e `queue.mark_done`;
   - dorme 2-5s (jitter) antes do proximo item.
3. Itens que nao couberam no lote (excedente de qualquer site) ficam
   `pending` na fila persistente — processados nos proximos ciclos, sem
   depender de re-scraping incidental da listagem.

## 6. Captura do link de afiliado — Mercado Livre (ponto critico do sistema)

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

## 6b. Captura do link de afiliado — Shopee

Calibrado e validado de ponta a ponta contra o DOM real em 2026-08-19
(`scripts/inspect_shopee_offers.py` com um item_id real, ver secao 11).
Implementado em `src/radar/scraper/shopee_affiliate.py`. Passos:

1. Extrai `item_id` da URL do produto (`parsing.extract_shopee_item_id`,
   regex `-i\.\d+\.(\d+)`) — **confirmado real**: o `item_id` da URL do
   produto na listagem bate exatamente com o produto certo no portal de
   afiliados (`product_offer/{item_id}`), sem precisar de busca.
2. Abre `https://affiliate.shopee.com.br/offer/product_offer/{item_id}`
   numa nova aba do mesmo `BrowserContext` (reaproveita a sessao logada no
   portal de afiliados).
3. Clica no botao "Obter link" (`SEL.GET_LINK_BUTTON`, texto do botao),
   que abre um modal "Link de Oferta de Produto" (Ant Design).
4. **Camada 1** (unica necessaria na pratica): le o valor de
   `<textarea disabled class="ant-input">` (`SEL.LINK_MODAL_INPUT =
   "textarea.ant-input"`) — ja vem preenchido com o link curto no formato
   `https://s.shopee.com.br/XXXXXXXXX`. O `.input_value()` do Playwright
   funciona normalmente mesmo com o textarea `disabled` (nao `readonly`).
   Camadas 2-4 (href de "Copiar link", clipboard da pagina, clipboard do
   SO) ficam como fallback pra variantes de UI nao observadas.
5. Validado por `_looks_like_affiliate_link()` (regex
   `s\.shopee|shope\.ee|affiliate\.shopee|smtt=|utm_campaign=` —
   `s.shopee.com.br` e o dominio confirmado real do link curto gerado).
6. Se nada validar, `AffiliateLinkNotFoundError` — pipeline pula o
   produto (nao marca como postado, tenta de novo no proximo ciclo).
7. A aba e sempre fechada no `finally`, mesmo em erro.

## 7. Deduplicacao

SQLite (`data/posted_products.db`), tabela `posted_products` com
`product_id TEXT PRIMARY KEY` (na pratica, chave prefixada por site —
`"ml:MLB123..."` / `"shopee:18899..."` — pra nao colidir entre
marketplaces; ver `pipeline.process_queue`). Escolhido em vez de JSON por
atomicidade (escrita corrompida em crash no meio de um `INSERT` nao
acontece com `INSERT OR REPLACE` + `commit`) e custo de consulta O(log n)
indexado. Nao ha expiracao — um produto postado uma vez nunca e repostado,
mesmo que o desconto mude.

## 8. Configuracao (`.env`)

| Variavel | Obrigatoria | Default | Efeito |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | sim | - | Token do bot (BotFather) |
| `TELEGRAM_CHAT_ID` | sim | - | Destino das ofertas (canal/grupo, bot precisa ser admin) |
| `TELEGRAM_ADMIN_CHAT_ID` | nao | - | Destino dos alertas de erro; sem isso, alertas sao descartados silenciosamente |
| `CHROME_DEBUG_URL` | nao | `http://localhost:9222` | Endpoint CDP do Chrome ja aberto |
| `OFFERS_URL` | nao | pagina de ofertas do ML | URL alvo do scraping (ML) |
| `SHOPEE_OFFERS_URL` | nao | `https://shopee.com.br/flash_sale` | URL alvo do scraping (Shopee) |
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
| Erro/excecao inesperada na descoberta de um site (`discover_offers`) | Isolado por site em `run_all_sites` (try/except): loga stack trace, alerta ao admin nomeando o site, **demais sites continuam a descoberta normalmente no mesmo ciclo** |
| 0 ofertas extraidas de um site (seletor quebrado/lento) | Loga warning + alerta ao admin nomeando o site; esse site nao enfileira nada nesse ciclo, mas nao afeta os demais |
| Link de afiliado nao encontrado ou erro processando um item da fila | Isolado por item em `process_queue`: loga erro, `queue.mark_failed` (retry em ciclos futuros ate `MAX_ATTEMPTS=5`), **segue pro proximo item do lote (de qualquer site) no mesmo lote** — nao espera nem bloqueia |
| Erro inesperado fora do loop de itens (ex.: falha no proprio SQLite da fila) | Loga stack trace completo, alerta ao admin, ciclo seguinte tenta de novo apos `CHECK_INTERVAL_SECONDS` |
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
  `selectors.py` usando `scripts/inspect_offers.py` (ML) ou
  `scripts/inspect_shopee_offers.py` (Shopee). Risco maior na Shopee: o
  card da listagem usa classes CSS com hash de build ("BlBXvx", "J0nYy6"
  etc.) que trocam a cada deploy — por isso `OFFER_CARD` localiza o card
  pelo `aria-label` (texto de acessibilidade) em vez de classes, e
  nome/preco/desconto sao parseados do proprio texto do `aria-label`
  (`CARD_LABEL_PATTERN` em `shopee_offers_page.py`), nao de sub-elementos.
- **Anti-bot da Shopee e bem mais agressivo que o do ML**: a 1a navegacao
  automatizada pra `flash_sale` foi redirecionada pra um captcha
  (`shopee.com.br/verify/captcha?...&scene=crawler_item`) — a Shopee
  detecta o proprio Playwright/CDP como trafego de bot, nao e so
  rate-limit por IP. Resolvendo o captcha manualmente uma vez (janela do
  Chrome fica visivel, o usuario resolve na hora) a sessao fica liberada
  pras navegacoes seguintes automatizadas (nao foi preciso resolver de
  novo nos testes seguintes na mesma sessao) — mas se a Shopee reforcar a
  deteccao, esse desbloqueio manual pode passar a ser necessario com mais
  frequencia. Sem tratamento automatico de captcha (fora de escopo, ver
  secao 2).
- **Dependencia de janela visivel**: a Camada 4 (clipboard do SO) so
  funciona com a janela do Chrome nao minimizada; as camadas 1 e 2 (as
  mais usadas na pratica) nao tem essa restricao.
- **Sem rotacao/expiracao de dedup**: a base de produtos postados cresce
  indefinidamente (irrelevante em volume — poucos KB por milhares de
  produtos).

## 11. Validacao realizada

- Testes unitarios (`pytest`) cobrindo `parsing` (incluindo
  `extract_shopee_item_id`), `formatter` (incluindo mensagem com
  `source="shopee"`), `dedup` (incluindo chave prefixada por site).
- Ciclo ML completo executado contra a pagina real de ofertas, em
  `DRY_RUN`, validando extracao de 6 produtos distintos com link de
  afiliado unico cada um (bug de reuso de link entre produtos
  identificado e corrigido nesse processo — ver secao 6, passo 2).
- Ciclo real em producao (`DRY_RUN=false`) postou 15 ofertas no grupo
  Telegram configurado, com envio confirmado (HTTP 200 + `message_id` de
  retorno da API).
- **Shopee calibrado e validado em 2026-08-19** com
  `scripts/inspect_shopee_offers.py` contra o site real (Chrome com
  `--remote-debugging-port`, logado na Shopee e no portal de afiliados):
  - `list_offers` extraiu 27 ofertas reais de `shopee.com.br/flash_sale`
    (nome, `%` desconto, preco, URL do produto todos corretos).
  - `get_affiliate_link` resolveu o link de afiliado real de um item
    (`https://s.shopee.com.br/...`) de ponta a ponta: extrair item_id da
    URL -> abrir o portal -> clicar "Obter link" -> ler o link do modal.
  - **2 bugs encontrados e corrigidos nesse processo**: (1) `_load_cards`
    saia do loop de scroll na 1a iteracao porque comparava
    `count == previous_count` com os dois em 0 (cards ainda nao
    hidratados) — corrigido usando `previous_count = -1` como sentinel;
    (2) a lista de produtos da Shopee carrega de forma assincrona depois
    do banner/cabecalho, mais devagar e de forma mais variavel que a
    hidratacao inicial — trocado espera fixa por
    `page.wait_for_selector(SEL.OFFER_CARD, timeout=15000)`.
  - **Confirmado**: a Shopee redireciona a 1a navegacao automatizada pra
    um captcha anti-bot (`scene=crawler_item`) — resolvido manualmente
    uma vez na janela visivel do Chrome, sessao ficou liberada pras
    chamadas automatizadas seguintes (ver secao 10).
- **Bug encontrado e corrigido em producao**: `scheduler.py` reaproveitava
  uma unica aba (`page`) de listagem entre ciclos, criada so na
  (re)conexao ao Chrome. Quando essa aba especifica foi fechada (o browser
  em si continuou de pe), o proximo ciclo falhou com
  `playwright.TargetClosedError` no `page.goto` — e o loop nao detectava
  isso, porque so verificava `browser.is_connected()`. Corrigido fazendo
  `pipeline.discover_offers` abrir e fechar sua propria aba de listagem a
  cada ciclo (`context.new_page()` / `page.close()` dentro da propria
  chamada), mesmo padrao ja usado pra paginas de produto — nenhuma aba
  fica aberta por mais que a duracao de uma chamada.
- **Fila e isolamento entre sites adicionados em 2026-08-19** (ver secao
  3b), pra dois problemas reais: uma excecao nao tratada processando um
  produto de um site podia pular o(s) site(s) seguinte(s) no mesmo ciclo;
  e descoberta/processamento ficavam presos juntos, entao um site lento
  atrasava o ciclo inteiro (inclusive descoberta dos outros sites no
  proximo ciclo). Validado com testes unitarios (`tests/test_queue_repo.py`,
  `tests/test_pipeline.py`, `tests/test_scheduler.py`) e com ciclo real
  (ML + Shopee, `DRY_RUN=true`): Shopee zerou ofertas nesse ciclo
  (lentidao pontual de carregamento) sem impedir o ML de descobrir 44
  ofertas, enfileirar 39 e processar um lote de 6 normalmente.
