class ChromeNotConnectableError(Exception):
    pass


class AffiliateLinkNotFoundError(Exception):
    def __init__(self, product_url: str):
        super().__init__(f"Link de afiliado nao encontrado para: {product_url}")
        self.product_url = product_url
