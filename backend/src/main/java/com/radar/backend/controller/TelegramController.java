package com.radar.backend.controller;

import com.radar.backend.dto.TelegramMessageRequest;
import com.radar.backend.service.TelegramMessageService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Tag(name = "Telegram", description = "Envio de mensagem personalizada, fora do fluxo de ofertas")
@RestController
@RequestMapping("/api/telegram")
public class TelegramController {

    private final TelegramMessageService telegramMessageService;

    public TelegramController(TelegramMessageService telegramMessageService) {
        this.telegramMessageService = telegramMessageService;
    }

    @Operation(
            summary = "Envia mensagem personalizada pro Telegram",
            description = "Chama o Telegram Bot API diretamente (sem Chrome/scraping). "
                    + "`chatId` opcional: se omitido, usa TELEGRAM_CHAT_ID do .env.",
            responses = {
                    @ApiResponse(responseCode = "200", description = "Mensagem enviada"),
                    @ApiResponse(responseCode = "400", description = "Payload invalido (text vazio)"),
                    @ApiResponse(responseCode = "502", description = "Falha ao enviar (Telegram indisponivel, token invalido, etc)")
            }
    )
    @PostMapping("/message")
    public ResponseEntity<Void> sendMessage(@Valid @RequestBody TelegramMessageRequest request) {
        telegramMessageService.send(request);
        return ResponseEntity.status(HttpStatus.OK).build();
    }
}
