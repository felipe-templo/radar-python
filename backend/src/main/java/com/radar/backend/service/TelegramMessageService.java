package com.radar.backend.service;

import com.radar.backend.config.RadarProperties;
import com.radar.backend.dto.TelegramMessageRequest;
import com.radar.backend.exception.TelegramSendFailedException;
import org.springframework.stereotype.Service;

import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

/**
 * Envia mensagem avulsa pro Telegram chamando "python main.py --message ...".
 * E uma chamada curta e independente do ciclo de scraping (nao usa Chrome,
 * nao mexe no SQLite) - por isso roda sincrona, sem passar pelo
 * RadarProcessService (que so controla o subprocesso de scraping).
 */
@Service
public class TelegramMessageService {

    // TelegramClient.send_message tenta 3x com backoff exponencial (ate 20s
    // entre tentativas) + timeout de 15s por request HTTP - pior caso reserva
    // folga confortavel pra isso terminar antes do Java desistir.
    private static final long TIMEOUT_SECONDS = 60;

    private final RadarProperties properties;

    public TelegramMessageService(RadarProperties properties) {
        this.properties = properties;
    }

    public void send(TelegramMessageRequest request) {
        List<String> command = new ArrayList<>(List.of(
                properties.pythonExecutable(),
                "main.py",
                "--message", request.text()
        ));
        if (request.chatId() != null && !request.chatId().isBlank()) {
            command.add("--chat-id");
            command.add(request.chatId());
        }

        Process process;
        try {
            process = new ProcessBuilder(command)
                    .directory(new File(properties.projectDir()))
                    .redirectErrorStream(true)
                    .start();
        } catch (IOException e) {
            throw new UncheckedIOException("Falha ao iniciar processo Python", e);
        }

        String output = readOutput(process);
        boolean finished = waitFor(process);
        if (!finished) {
            process.destroyForcibly();
            throw new TelegramSendFailedException("timeout apos " + TIMEOUT_SECONDS + "s. Saida: " + output);
        }
        if (process.exitValue() != 0) {
            throw new TelegramSendFailedException("exit code " + process.exitValue() + ". Saida: " + output);
        }
    }

    private String readOutput(Process process) {
        StringBuilder output = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                output.append(line).append('\n');
            }
        } catch (IOException e) {
            output.append("[erro lendo saida: ").append(e.getMessage()).append(']');
        }
        return output.toString().trim();
    }

    private boolean waitFor(Process process) {
        try {
            return process.waitFor(TIMEOUT_SECONDS, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return false;
        }
    }
}
