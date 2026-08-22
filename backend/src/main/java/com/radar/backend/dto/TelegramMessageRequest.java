package com.radar.backend.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;

@Schema(description = "Mensagem personalizada a enviar direto pro Telegram, fora do fluxo de ofertas")
public record TelegramMessageRequest(
        @NotBlank(message = "text e obrigatorio")
        @Schema(description = "Texto da mensagem, suporta HTML (negrito, links) como no Telegram Bot API.", example = "<b>Aviso</b>: manutencao as 22h")
        String text,

        @Schema(description = "Chat/canal de destino. Se omitido, usa TELEGRAM_CHAT_ID do .env (canal principal).")
        String chatId
) {
}
