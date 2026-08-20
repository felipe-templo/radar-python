class OffersPageSelectors:
    """Seletores da pagina de ofertas do Mercado Livre.

    Calibrados em 2026-08-18 inspecionando o DOM real via
    scripts/inspect_offers.py contra https://www.mercadolivre.com.br/ofertas.
    Se o Mercado Livre redesenhar a pagina, isso pode quebrar - reajustar
    aqui usando o mesmo script.
    """

    COOKIE_BANNER_ACCEPT = "button:has-text('Entendi'), button:has-text('Aceitar')"
    OFFER_CARD = "div.poly-card"
    OFFER_TITLE = "a.poly-component__title"
    OFFER_LINK = "a.poly-component__title"
    OFFER_IMAGE = "img.poly-component__picture"
    OFFER_PRICE_ORIGINAL = "s.andes-money-amount--previous"
    OFFER_PRICE_DISCOUNT = "div.poly-price__current span.andes-money-amount"
    # Nao ha badge de "% OFF" explicito no card nesta versao da pagina;
    # o percentual e calculado a partir de original/discount price
    # (ver parsing.compute_discount_percent).
    OFFER_DISCOUNT_BADGE = ".poly-price__discount, .andes-money-amount__discount"
    LOAD_MORE_BUTTON = "button:has-text('Ver mais ofertas')"


class ProductPageSelectors:
    """Seletores da pagina de produto (botao Compartilhar).

    Calibrados em 2026-08-18. O popup de compartilhamento do Mercado Livre
    pode aparecer em DUAS variantes (o app leva ~1s para hidratar apos o
    load da pagina; clicar cedo demais faz o popup nao abrir ou abrir com
    estado desatualizado - por isso o goto usa wait_until="load" + espera
    extra em product_page.py):

    1. Popup "Gerar link / ID de produto": link curto de afiliado (dominio
       meli.la) num <textarea readonly>, testid 'text-field__label_link'.
       Observado como variante padrao na maioria dos produtos testados.
    2. Popup social simples (WhatsApp/Copiar link/X/Facebook/E-mail), onde
       o item "Copiar link" e um <a> cujo href ja contem os parametros de
       afiliado (matt_tool=...) embutidos - basta ler o atributo href.
    """

    SHARE_BUTTON = "button[data-testid='ui-pdp-share__link__label']"
    SHARE_MODAL_LINK_INPUT = "textarea[data-testid='text-field__label_link']"
    SHARE_MODAL_COPY_BUTTON = "button[data-testid='copy-button__label_link']"
    COPY_LINK_ANCHOR = "a[data-testid='share-on-click_COPY_LINK']"


class ShopeeOffersPageSelectors:
    """Seletores da pagina de ofertas relampago da Shopee (shopee.com.br/flash_sale).

    Calibrados em 2026-08-19 inspecionando o DOM real via
    scripts/inspect_shopee_offers.py. Shopee usa classes CSS com hash de
    build (ex.: "BlBXvx", "J0nYy6") que provavelmente mudam a cada deploy -
    por isso o card e localizado pelo <a> que envolve o item inteiro, via
    seu aria-label (texto de acessibilidade, mais estavel que classes).
    Nome/desconto/preco sao extraidos direto do texto do aria-label
    (padrao observado: "{nome} null promocao menos {desconto}% preco atual
    R${preco} ... entrar em ofertas relampago"), nao de sub-elementos -
    ver CARD_LABEL_PATTERN em scraper/shopee_offers_page.py. Sem selector
    de imagem: o card nao usa <img src> para a foto do produto (e
    background-image inline em div com classe com hash), entao image_url
    fica sempre None pros produtos Shopee.
    """

    COOKIE_BANNER_ACCEPT = "button:has-text('Aceitar'), button:has-text('OK, entendi')"
    OFFER_CARD = "a[aria-label*='ofertas relâmpago' i]"
    LOAD_MORE_BUTTON = "button:has-text('Ver mais')"


class ShopeeAffiliatePortalSelectors:
    """Seletores do portal de afiliados Shopee (affiliate.shopee.com.br/offer/product_offer/{item_id}).

    Calibrados em 2026-08-19 contra o DOM real (portal usa Ant Design -
    classes "ant-*" sao da biblioteca, bem mais estaveis que hashes de
    build). Fluxo confirmado: abrir a URL do item -> clicar "Obter link"
    -> abre modal "Link de Oferta de Produto" com um
    <textarea disabled class="ant-input"> ja preenchido com o link curto
    (formato "https://s.shopee.com.br/XXXXXXXX"). O textarea e disabled,
    NAO readonly - .input_value() do Playwright funciona mesmo assim.
    """

    GET_LINK_BUTTON = "button:has-text('Obter link'), button:has-text('Gerar link')"
    LINK_MODAL_INPUT = "textarea.ant-input"
    LINK_COPY_BUTTON = "button:has-text('Copiar')"
    COPY_LINK_ANCHOR = "a:has-text('Copiar link')"


class AmazonOffersPageSelectors:
    """Seletores da pagina de ofertas do dia da Amazon (amazon.com.br/deals).

    Calibrado em 2026-08-19 inspecionando o DOM real (Chrome logado,
    scripts/inspect_amazon_offers.py + dump de HTML manual) contra
    https://www.amazon.com.br/deals. O card e o proprio widget React de
    produto (`data-testid="product-card"`), que traz o ASIN pronto no
    atributo `data-asin` - mais estavel que extrair da URL, embora
    `parsing.extract_amazon_asin` continue sendo usado a partir do
    `product_url` no restante do pipeline (mesmo contrato dos outros
    sites). O grid carrega os produtos de forma incremental via scroll
    (virtualizado, so um punhado de cards fica no DOM por vez - mesmo
    padrao ja tratado por `_load_cards`).

    A secao de preco (`data-testid="price-section"`) tem dois
    `span.a-price`: o de "Preco da Oferta" (sem a classe extra
    `a-text-price`) e o riscado "De:" (com `a-text-price`) - por isso
    OFFER_PRICE_DISCOUNT usa `:not(.a-text-price)` pra nao pegar o
    riscado por engano. O badge de desconto
    (`div[data-component="dui-badge"]`) tem dois `span.a-size-mini`: o
    primeiro e o percentual ("42% off"), o segundo e o rotulo ("Oferta") -
    por isso `.first` em vez de pegar todos.
    """

    COOKIE_BANNER_ACCEPT = "input#sp-cc-accept, button:has-text('Aceitar')"
    OFFER_CARD = "div[data-testid='product-card']"
    OFFER_LINK = "a[data-testid='product-card-link']"
    OFFER_TITLE = "span.a-truncate-full"
    OFFER_IMAGE = "img"
    OFFER_PRICE_DISCOUNT = "div[data-testid='price-section'] span.a-price:not(.a-text-price) span.a-offscreen"
    OFFER_PRICE_ORIGINAL = "div[data-testid='price-section'] span.a-price.a-text-price span.a-offscreen"
    OFFER_DISCOUNT_BADGE = "div[data-component='dui-badge'] span.a-size-mini"
    LOAD_MORE_BUTTON = "button:has-text('Ver mais')"


class AmazonSiteStripeSelectors:
    """Seletores da barra SiteStripe (Amazon Associates) na propria pagina
    do produto.

    Calibrado em 2026-08-19 contra o DOM real (Chrome logado com
    Associates ativo, produto B09LHW62H7). Diferente do que se imaginava
    inicialmente, o SiteStripe fica fixo no TOPO da pagina (`#nav-AssociateStripe`),
    nao acima do rodape - e o fluxo NAO expoe o link num campo de texto:
    clicar em "Obter link" (`#amzn-ss-get-link-button`) abre um popover
    com radio buttons de formato (link curto/completo) e um botao
    "Copiar link de afiliado" (`#amzn-ss-copy-affiliate-link-btn`) que
    copia direto pro clipboard - sem nenhum <textarea>/<input> visivel
    pra ler o valor. Confirmado que o link curto gerado usa dominio
    `link.amazon/{codigo}` (NAO `amzn.to`, que e o encurtador antigo) -
    ver AFFILIATE_LINK_PATTERN em amazon_affiliate.py.
    """

    GET_LINK_BUTTON = "#amzn-ss-get-link-button"
    COPY_LINK_BUTTON = "#amzn-ss-copy-affiliate-link-btn"
