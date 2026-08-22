import logging

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from radar.models import Product

logger = logging.getLogger(__name__)


class TelegramClient:
    def __init__(self, token: str, chat_id: str):
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.chat_id = chat_id

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
    def send_offer(self, product: Product, caption: str) -> dict:
        if product.image_url:
            resp = requests.post(
                f"{self.base_url}/sendPhoto",
                data={
                    "chat_id": self.chat_id,
                    "photo": product.image_url,
                    "caption": caption,
                    "parse_mode": "HTML",
                },
                timeout=15,
            )
            if not resp.ok:
                logger.warning("sendPhoto falhou (%s), tentando sendMessage sem imagem", resp.status_code)
                resp = self._send_text(caption)
        else:
            resp = self._send_text(caption)
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
    def send_message(self, text: str, chat_id: str | None = None) -> dict:
        """Envia mensagem de texto livre (HTML) para o chat informado, ou
        para o chat principal (self.chat_id) se nao informado. Usado para
        mensagens personalizadas, fora do fluxo de ofertas."""
        resp = requests.post(
            f"{self.base_url}/sendMessage",
            data={"chat_id": chat_id or self.chat_id, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def _send_text(self, caption: str) -> requests.Response:
        return requests.post(
            f"{self.base_url}/sendMessage",
            data={"chat_id": self.chat_id, "text": caption, "parse_mode": "HTML"},
            timeout=15,
        )

    def send_alert(self, admin_chat_id: str | None, text: str) -> None:
        if not admin_chat_id:
            return
        try:
            requests.post(
                f"{self.base_url}/sendMessage",
                data={"chat_id": admin_chat_id, "text": f"⚠️ {text}"},
                timeout=10,
            )
        except requests.RequestException:
            logger.exception("Falha ao enviar alerta ao admin")
