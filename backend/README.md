# radar-backend

API Spring Boot que controla o `radar-python` (scraper de ofertas Mercado Livre / Amazon / Shopee) como subprocesso, e expõe os produtos já capturados (SQLite) via REST.

## Pré-requisito

Chrome já aberto com `--remote-debugging-port=9222`, logado nos sites desejados (mesmo requisito do `radar-python` via CLI/GUI). Este backend não abre nem loga o Chrome.

## Rodar

```
cd backend
mvn spring-boot:run
```

Config em `src/main/resources/application.yml` (override via env vars `RADAR_PYTHON_EXE`, `RADAR_PROJECT_DIR`, `RADAR_DB_PATH`, `RADAR_LOG_DIR`).

## Swagger

- UI: http://localhost:8080/swagger-ui/index.html
- Spec: http://localhost:8080/v3/api-docs

## Endpoints

- `POST /api/radar/run` — dispara um ciclo único do scraper.
  ```json
  { "sites": ["ML", "AMAZON"], "quantity": 20, "channel": "TELEGRAM" }
  ```
  `sites` vazio/omitido = todos (ML, AMAZON, SHOPEE). `quantity` é por site. `channel: "WHATSAPP"` retorna 400 (não implementado ainda). Retorna 202 com o status inicial; 409 se já houver execução em andamento.
- `GET /api/radar/status` — status atual (`IDLE|RUNNING|COMPLETED|FAILED|STOPPED`), timestamps, exit code, últimas linhas do log.
- `POST /api/radar/stop` — mata o processo em execução.
- `GET /api/products/recent?limit=50` — últimos produtos postados (lidos do SQLite `posted_products`), com `inferredSource` (ml/amazon/shopee) extraído do `product_id`.
- `GET /api/products/queue-stats` — contagem de itens da fila (`offer_queue`) por site/status (pending/failed/done).
- `POST /api/telegram/message` — envia mensagem personalizada direto pro Telegram (sem Chrome/scraping).
  ```json
  { "text": "<b>Aviso</b>: manutencao as 22h", "chatId": null }
  ```
  `chatId` opcional (default `TELEGRAM_CHAT_ID` do `.env`). Retorna 200, 400 (texto vazio) ou 502 (falha ao enviar).

## Troubleshooting: `POST /api/radar/run` falha ou volta 0 produtos

Esse endpoint so dispara `main.py` (mesmo scraper Python das secoes
anteriores) como subprocesso — se ele falhar (`GET /api/radar/status`
com `FAILED`) ou terminar sem capturar produto nenhum pro site pedido,
o problema esta no scraper Python, nao no backend Java. Nesse caso a API
nao ajuda a diagnosticar; teste o site direto com os scripts isolados do
`radar-python` (passo a passo completo no
[`README.md`](../README.md#4-seletores-e-scripts-de-link-de-afiliado-ja-calibrados-so-mexer-se-o-site-mudar)
da raiz):

1. Chrome com debug port aberto (mesmo requisito de cima), logado no
   site em questao (Shopee: tambem no portal de afiliados; Amazon:
   tambem com Amazon Associates ativo).
2. No terminal, na raiz do `radar-python` (nao em `backend/`), com o
   venv Python ativado:
   ```powershell
   python scripts/inspect_offers.py           # Mercado Livre
   python scripts/inspect_shopee_offers.py    # Shopee
   python scripts/inspect_amazon_offers.py    # Amazon
   ```
3. Contagem 0 ofertas ou `FALHOU: AffiliateLinkNotFoundError` confirma
   que um seletor quebrou (site mudou de layout) — ajuste
   `src/radar/selectors.py` conforme `SPEC.md` secoes 6/6b/6c/6d, rode o
   script de novo ate a saida vir limpa, e so entao dispare
   `POST /api/radar/run` de novo.
