package com.radar.backend.exception;

public class TelegramSendFailedException extends RuntimeException {
    public TelegramSendFailedException(String details) {
        super("Falha ao enviar mensagem pro Telegram: " + details);
    }
}
