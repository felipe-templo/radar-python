# Spec — Radar de Ofertas Mercado Livre + Shopee + Amazon -> Telegram

Status: **em producao**. ML calibrado e validado contra o site real em
2026-08-18; Shopee calibrado e validado contra o site real em 2026-08-19
(listagem + resolucao de link de afiliado testadas de ponta a ponta, ver
secao 6b e secao 11); Amazon calibrado e validado contra o site real em
2026-08-19 (listagem + resolucao de link de afiliado via SiteStripe
testadas de ponta a ponta, ver secao 6c e secao 11). Backend HTTP (Java)
adicionado em 2026-08-21 como camada de controle opcional sobre o mesmo
motor (ver secao 12). Documento descreve o app como construido, nao como
planejado.

## 1. Objetivo

Monitorar as paginas de ofertas relampago do Mercado Livre
(`https://www.mercadolivre.com.br/ofertas`), da Shopee
(`https://shopee.com.br/flash_sale`) e as ofertas do dia da Amazon
(`https://www.amazon.com.br/deals`), extrair produtos com desconto, obter
o link de afiliado de cada um e publicar automaticamente um anuncio
formatado (nome, de/por, % off, link, origem) num grupo/canal do Telegram,
em loop continuo, sem repetir produto ja postado. Ao iniciar, o usuario
escolhe qual(is) site(s) rodar (Mercado Livre, Shopee, Amazon, ou todos).

## 2. Escopo e nao-escopo

Dentro do escopo:
- Leitura da pagina de ofertas (ML e Shopee) e extracao de cards de produto.
- Captura de link de afiliado real (nao um link generico do produto) — via
  botao "Compartilhar" na propria pagina do produto (ML), via portal de
  afiliados `affiliate.shopee.com.br` (Shopee, ver secao 6b) ou via botao
  "Obter link" (SiteStripe do Amazon Associates) na propria pagina do
  produto (Amazon, ver secao 6c).
- Escolha interativa, ao iniciar (CLI `main.py` ou GUI `gui.py`), de qual(is)
  site(s) rodar nesta execucao.
- Formatacao e envio de mensagem para um unico destino Telegram (mesmo canal
  para os dois sites, com indicacao de origem na mensagem).
- Deduplicacao persistente entre execucoes/reinicios, por site (chave
  `{site}:{product_id}`, sem colisao entre marketplaces).
- Alertas de erro para um chat Telegram de admin (opcional).

Fora do escopo (nao implementado):
- Login/autenticacao automatizada no Mercado Livre/Shopee/Amazon — a
  sessao logada e responsabilidade do usuario, mantida manualmente num
  Chrome externo (inclusive login no portal de afiliados Shopee e na
  conta Amazon Associates).
- Publicacao em outros canais alem do Telegram — `WHATSAPP` ja existe
  como valor de enum na API HTTP (secao 12), mas retorna erro (400): sem
  implementacao real do lado Python ainda.
- Reimplementacao do scraper em outra linguagem — o backend Java (secao
  12) e uma camada de controle/orquestracao por cima do Python via
  subprocess, nao um substituto do motor Playwright/CDP.
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
| `main.py` | Entrypoint CLI: sem args, pergunta qual(is) site(s) rodar e chama `run_forever` (comportamento original). Com args (`--sites`, `--quantity`, `--once`, `--channel`, `--message`/`--chat-id`), roda nao-interativo — usado pelo backend Java (secao 12) |
| `gui.py` | Entrypoint GUI (customtkinter): mesmo loop, com seletor de site(s) e botao iniciar/parar |
| `src/radar/config.py` | Le `.env` -> `Settings` (dataclass imutavel) |
| `src/radar/browser.py` | Conecta a um Chrome ja aberto via CDP; concede permissao de clipboard (ML e Shopee) |
| `src/radar/sites.py` | Registry `SiteConfig` (ML e Shopee): agrupa listagem, resolucao de afiliado e extracao de ID por site |
| `src/radar/selectors.py` | Constantes de seletores CSS/testid, unico lugar a editar se um site mudar |
| `src/radar/scraper/offers_page.py` | Le a listagem de ofertas do ML, faz scroll incremental, extrai `RawOfferCard` |
| `src/radar/scraper/product_page.py` | Abre pagina do produto ML, clica Compartilhar, extrai o link de afiliado |
| `src/radar/scraper/shopee_offers_page.py` | Le a listagem de ofertas relampago da Shopee, extrai `RawOfferCard` |
| `src/radar/scraper/shopee_affiliate.py` | Abre o item no portal de afiliados Shopee, clica Obter link, extrai o link |
| `src/radar/scraper/amazon_offers_page.py` | Le a pagina de ofertas do dia da Amazon, faz scroll incremental, extrai `RawOfferCard` |
| `src/radar/scraper/amazon_affiliate.py` | Abre a pagina do produto Amazon, clica "Obter link"/"Copiar link de afiliado" (SiteStripe), le o link do clipboard |
| `src/radar/parsing.py` | Parsing de preco (`R$ 1.234,56` -> `Decimal`), % desconto, ID do produto (ML e Shopee) |
| `src/radar/models.py` | `RawOfferCard` (dado cru do card) e `Product` (dado final, com afiliado e `source`) |
| `src/radar/formatter.py` | Monta o texto HTML da mensagem do Telegram, com emoji/rotulo por origem |
| `src/radar/telegram_client.py` | `sendPhoto`/`sendMessage` via Telegram Bot API (HTTP puro, com retry) |
| `src/radar/dedup.py` | Repositorio SQLite: `is_posted(key)` / `mark_posted(product, dedup_key, ...)` |
| `src/radar/queue_repo.py` | `OfferQueue`: fila SQLite compartilhada entre sites, intercalada round-robin (ver secao 3b) |
| `src/radar/pipeline.py` | `discover_offers` (lista+filtra+enfileira, por site) e `process_queue` (drena fila, resolve afiliado, formata, envia, marca) |
| `src/radar/scheduler.py` | `run_all_sites` (descoberta isolada por site + drena fila); `run_forever` roda em loop infinito com reconexao/backoff/alertas; `run_once` conecta, roda um ciclo e fecha (usado por `main.py --once` / backend Java) |
| `src/radar/exceptions.py` | `ChromeNotConnectableError`, `AffiliateLinkNotFoundError` |
| `scripts/inspect_offers.py` | Script manual pra recalibrar `selectors.py` (ML) quando o site mudar |
| `scripts/inspect_shopee_offers.py` | Script manual pra recalibrar `selectors.py` (Shopee) quando o site mudar |
| `scripts/inspect_amazon_offers.py` | Script manual pra calibrar/recalibrar `selectors.py` (Amazon) — ver secao 6c |

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

## 6c. Captura do link de afiliado — Amazon

Calibrado e validado de ponta a ponta contra o DOM real em 2026-08-19
(Chrome logado com sessao Amazon Associates ativa, ciclo completo de
`discover_offers` + `process_queue` rodado contra
`amazon.com.br/deals` em `DRY_RUN`, ver secao 11). Implementado em
`src/radar/scraper/amazon_offers_page.py` (listagem) e
`src/radar/scraper/amazon_affiliate.py` (afiliado). Passos:

1. `list_offers` abre `AMAZON_OFFERS_URL` (padrao: pagina de ofertas do
   dia, `amazon.com.br/deals`) e localiza os cards via
   `div[data-testid="product-card"]` — o widget React de produto, que ja
   traz o ASIN pronto no atributo `data-asin`. O grid e virtualizado (so
   um punhado de cards fica montado no DOM por vez, o resto entra/sai
   conforme rola), por isso o mesmo scroll incremental de ML/Shopee
   (`_load_cards`) e usado, com dedupe por ASIN pra nao repetir produto
   entre leituras.
2. Preco atual vem de `div[data-testid="price-section"]
   span.a-price:not(.a-text-price) span.a-offscreen`; o preco original
   riscado (quando existe) do mesmo container mas com a classe extra
   `.a-text-price`. O badge de desconto
   (`div[data-component="dui-badge"] span.a-size-mini`, primeiro span —
   o segundo e so o rotulo "Oferta") da o percentual direto; se ausente,
   cai pro fallback `parsing.compute_discount_percent` (mesmo do ML).
3. `get_affiliate_link` abre o produto numa nova aba. **Confirmado**: a
   barra SiteStripe fica fixa no TOPO da pagina
   (`#nav-AssociateStripe`), nao acima do rodape como se imaginava antes
   de calibrar. Clicar em "Obter link" (`#amzn-ss-get-link-button`) abre
   um popover com radio buttons de formato (link curto/completo) e um
   botao "Copiar link de afiliado"
   (`#amzn-ss-copy-affiliate-link-btn`) que copia o link **direto pro
   clipboard** — diferente de ML/Shopee, nao ha nenhum `<textarea>` ou
   `<input>` visivel com o valor pra ler via DOM, entao a unica camada
   real de extracao e clipboard: primeiro `navigator.clipboard.readText()`
   da propria pagina, com fallback pro clipboard do sistema operacional
   via `pyperclip` (exige janela do Chrome visivel).
4. **Confirmado**: o link curto gerado usa o dominio `link.amazon/{codigo}`
   (ex.: `https://link.amazon/B0h5jcXcC`), NAO `amzn.to` (encurtador
   antigo da Amazon, mantido no regex de validacao como fallback).
   `_looks_like_affiliate_link()` usa
   `link\.amazon/|amzn\.to/|tag=|linkCode=`.
5. `AffiliateLinkNotFoundError` se nada validar; a aba e sempre fechada no
   `finally`.

`extract_amazon_asin` (`src/radar/parsing.py`) extrai o ASIN via regex
`/(?:dp|gp/product)/([A-Za-z0-9]{10})` a partir do `product_url`, usado
como `product_id` (chave de dedup `"amazon:{ASIN}"`, mesmo esquema de
prefixo por site da secao 7).

## 6d. Como rodar os scripts de link de afiliado (recalibracao manual)

Os 3 scripts em `scripts/` exercitam o codigo das secoes 6/6b/6c acima
contra o DOM real, sem rodar o pipeline inteiro (sem postar no
Telegram, sem tocar `posted_products.db`). Passo a passo:

1. Abra o Chrome com debug port (README secao 1) e logue manualmente no
   site em questao: ML normal; Shopee + portal de afiliados
   (`affiliate.shopee.com.br`); Amazon + Amazon Associates ativo (sem
   Associates a SiteStripe da secao 6c nao aparece).
2. No terminal (venv ativado), rode so a listagem de ofertas:
   ```powershell
   python scripts/inspect_offers.py           # ML -> OffersPageSelectors
   python scripts/inspect_shopee_offers.py    # Shopee -> shopee_offers_page.list_offers
   python scripts/inspect_amazon_offers.py    # Amazon -> amazon_offers_page.list_offers
   ```
   Cada um imprime a contagem de ofertas e os 10 primeiros produtos
   (desconto/preco/nome/URL). Contagem 0 = seletor de card/preco/desconto
   quebrou (secoes 4 e 6/6b/6c descrevem os seletores exatos).
3. Pra exercitar tambem a captura do link de afiliado (secoes 6b/6c),
   rode de novo passando um ID real de produto:
   ```powershell
   python scripts/inspect_shopee_offers.py <item_id>   # numero final da URL: shopee.com.br/produto-i.123.<item_id>
   python scripts/inspect_amazon_offers.py <ASIN>       # 10 chars apos /dp/ na URL do produto
   ```
   `inspect_offers.py` (ML) nao tem esse modo — a captura de link do ML
   (secao 6) so e exercitada pelo pipeline completo (`main.py` com
   `DRY_RUN=true`), porque depende do fluxo Compartilhar dentro da propria
   pagina de ofertas, nao de uma URL de produto avulsa.
4. Resultado esperado: `Link de afiliado obtido: <url>` batendo com o
   dominio confirmado em 6b/6c (`s.shopee.com.br` / `shope.ee` pra
   Shopee, `link.amazon/...` / `amzn.to` pra Amazon). `FALHOU:
   AffiliateLinkNotFoundError` indica que uma das camadas de extracao
   (textarea/href/clipboard) descritas em 6/6b/6c parou de bater com o
   DOM real.
5. Se algo quebrou, abra o DevTools (F12) no elemento real (botao/popup/
   modal do fluxo de afiliado) e ajuste o seletor correspondente em
   `src/radar/selectors.py`; se a estrutura do popup/modal mudou (nao so
   o seletor), ajuste tambem o parsing em `scraper/*_affiliate.py` ou
   `scraper/*_offers_page.py` conforme o caso, atualizando a secao
   6/6b/6c correspondente com a nova data de calibracao.

## 7. Deduplicacao

SQLite (`data/posted_products.db`), tabela `posted_products` com
`product_id TEXT PRIMARY KEY` (na pratica, chave prefixada por site —
`"ml:MLB123..."` / `"shopee:18899..."` / `"amazon:B08N5WRWNW"` — pra nao
colidir entre marketplaces; ver `pipeline.process_queue`). Escolhido em
vez de JSON por
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
| `AMAZON_OFFERS_URL` | nao | `https://www.amazon.com.br/deals?ref_=nav_cs_gb` | URL alvo do scraping (Amazon, ofertas do dia) |
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
- **Amazon depende de sessao Associates ativa**: `get_affiliate_link` so
  funciona se a conta logada no Chrome de debug tiver Amazon Associates
  ativo (a barra SiteStripe so aparece nesse caso). Sem isso,
  `#amzn-ss-get-link-button` nao existe no DOM e o item cai em
  `AffiliateLinkNotFoundError` (retry ate `MAX_ATTEMPTS`, ver secao 9).
- **Grid de ofertas da Amazon e virtualizado**: `product-card` sai/entra
  do DOM conforme rola (so um punhado fica montado por vez), diferente do
  ML/Shopee onde os cards ja lidos permanecem no DOM. O dedupe por ASIN em
  `amazon_offers_page.py` cobre o caso de reler o mesmo produto entre
  leituras, mas se a Amazon mudar esse comportamento de virtualizacao,
  vale reconferir com `scripts/inspect_amazon_offers.py`.

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
- **Amazon calibrado e validado em 2026-08-19** contra o site real (Chrome
  com `--remote-debugging-port`, logado na Amazon com Amazon Associates
  ativo):
  - `list_offers` extraiu 24 ofertas reais de `amazon.com.br/deals`
    (nome, `%` desconto, preco atual, preco original quando presente,
    URL do produto — todos corretos, incluindo acentuacao/UTF-8 real,
    confirmado via `repr()` — o mojibake visto no console era so
    limitacao de codepage do terminal Windows, nao corrupcao de dados).
  - `get_affiliate_link` resolveu o link de afiliado real de dois
    produtos distintos de ponta a ponta (`https://link.amazon/...`, link
    unico por produto).
  - Ciclo completo (`discover_offers` + `process_queue`, `DRY_RUN=true`)
    rodado contra o site real: 24 ofertas descobertas, 19 enfileiradas
    (5 abaixo de `MIN_DISCOUNT_PERCENT`), processamento sem erro,
    mensagem formatada corretamente (nome, de/por, % off, link, emoji de
    origem).
  - **2 achados corrigidos durante a calibracao** (a implementacao
    inicial era best-effort, sem acesso ao DOM real): (1) `OFFER_CARD`
    apontava para `a[href*='/dp/']` com uma heuristica de ancestor via
    xpath — trocado por `div[data-testid="product-card"]` (o card real,
    com ASIN pronto em `data-asin`); (2) a suposicao inicial de que o
    botao "Obter link" ficava acima do rodape e copiava direto era
    parcialmente errada — o botao (`#amzn-ss-get-link-button`) fica fixo
    no TOPO da pagina e so abre um popover; o link so e copiado ao
    clicar num segundo botao dentro do popover
    (`#amzn-ss-copy-affiliate-link-btn`), e o dominio do link curto
    gerado e `link.amazon/` (nao `amzn.to`, que era a suposicao inicial).
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

## 12. Backend Java (API HTTP, opcional)

Adicionado em 2026-08-21 (`backend/`, Spring Boot 3 + Java 21 + Maven).
Objetivo: controlar o motor Python via HTTP (disparar ciclo sob demanda
escolhendo sites/quantidade/canal, consultar status/log, ler produtos ja
capturados, mandar mensagem avulsa) sem reescrever scraping nenhum.

**Decisao de arquitetura**: reimplementar Playwright + CDP + fallback de
clipboard em Java nao compensava o esforco pro beneficio (o motor Python
ja funciona, calibrado e validado — secoes 6/6b/6c/11). Em vez disso, o
backend gerencia o processo Python como subprocess (`ProcessBuilder`) e
le diretamente o SQLite que o Python ja escreve. Ele nunca abre Chrome,
nunca fala com Playwright, nunca escreve no SQLite — so orquestra e le.

**Mudancas no lado Python pra viabilizar isso** (mantendo 100% do
comportamento anterior quando chamado sem args):
- `scheduler.run_once(settings, sites)` — extraido de `run_forever`:
  conecta ao Chrome, roda um `run_all_sites` e fecha, sem loop. Usado
  quando a API pede "1 ciclo agora" em vez de loop continuo.
- `main.py` ganhou `argparse` opcional: `--sites ml,shopee,amazon|all`,
  `--quantity N` (override de `MAX_PRODUCTS_PER_CYCLE` nessa execucao),
  `--once` (chama `run_once` em vez de `run_forever`), `--channel
  telegram|whatsapp` (`whatsapp` sai com erro — nao implementado),
  `--message TEXTO` + `--chat-id ID` (atalho pra mandar uma mensagem
  Telegram avulsa sem tocar em Chrome/scraping, via
  `TelegramClient.send_message`, novo metodo). Sem nenhum desses args,
  `main.py` continua identico a antes (prompt interativo + loop).

**Por que 1-ciclo-por-chamada, nao loop controlado pela API**: decisao
tomada com o usuario — mais simples de raciocinar (sem estado de
"processo de longa duracao gerenciado por outro processo"), sem
diferenca pratica de throughput (quem quiser recorrencia so chama a API
nesse intervalo por fora, ex.: cron/scheduler).

**Endpoints** (documentados via springdoc-openapi, Swagger UI em
`/swagger-ui/index.html`, `/` redireciona pra la):
- `POST /api/radar/run` — `{sites, quantity, channel}` -> dispara `main.py
  --once` com esses args; 202 (RUNNING), 409 se ja tem execucao em
  andamento, 400 se `channel=WHATSAPP`.
- `GET /api/radar/status` — estado (`IDLE/RUNNING/COMPLETED/FAILED/STOPPED`),
  timestamps, exit code, ultimas linhas do log do subprocesso.
- `POST /api/radar/stop` — mata o subprocess em andamento.
- `GET /api/products/recent` — le `posted_products` (SQLite), mais
  recentes primeiro; `inferredSource` vem do prefixo real do
  `product_id` gravado (`"site:id"`, ver secao 7), nao e heuristica.
- `GET /api/products/queue-stats` — `offer_queue` agrupado por
  site/status (pending/done/failed).
- `POST /api/telegram/message` — `{text, chatId?}` -> roda `main.py
  --message` sincrono (timeout 60s, cobrindo os 3 retries com backoff
  do `TelegramClient`); 502 se o envio falhar.

**Limitacao conhecida**: no maximo 1 execucao de scraping por vez (o
SQLite de fila/dedup nao foi desenhado pra duas instancias do Python
escrevendo ao mesmo tempo) — `RadarProcessService` (Java) garante isso
com um `ExecutorService` single-thread e checagem de estado antes de
iniciar um novo `run`. `/api/telegram/message` e independente disso (nao
mexe no SQLite nem no Chrome), pode rodar mesmo com um ciclo de scraping
em andamento.

**Validado em 2026-08-21/22**: ciclo real disparado via
`POST /api/radar/run` (`sites=[ML]`, `DRY_RUN=true` no teste, depois
`DRY_RUN=false` em producao com `--sites all --once` direto) — Chrome de
debug com profile persistente (`ChromeDebugProfile`, ver README secao 1),
ciclo `COMPLETED` com exit 0, produtos reais lidos de volta via
`GET /api/products/recent`. `POST /api/telegram/message` validado com
envio real (200) e com texto vazio (400). `POST /api/radar/run` com
`channel=WHATSAPP` validado retornando 400 sem subir processo nenhum.
