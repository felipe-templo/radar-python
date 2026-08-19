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
