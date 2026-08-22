package com.radar.backend.service;

import com.radar.backend.config.RadarProperties;
import com.radar.backend.dto.RunRequest;
import com.radar.backend.dto.RunStatusResponse;
import com.radar.backend.exception.ChannelNotImplementedException;
import com.radar.backend.exception.NoRunInProgressException;
import com.radar.backend.exception.RunAlreadyInProgressException;
import com.radar.backend.model.Channel;
import com.radar.backend.model.RunStatus;
import com.radar.backend.model.Site;
import org.springframework.stereotype.Service;

import java.io.File;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.Collectors;

/**
 * Gerencia o ciclo de vida do subprocesso Python (main.py --once) que faz
 * uma unica rodada de descoberta+postagem. Suporta no maximo uma execucao
 * por vez - a fila/dedup do proprio Python (SQLite) nao foi desenhada pra
 * duas instancias escrevendo ao mesmo tempo.
 */
@Service
public class RadarProcessService {

    private final RadarProperties properties;
    private final ExecutorService executor = Executors.newSingleThreadExecutor(runnable -> {
        Thread thread = new Thread(runnable, "radar-run-watcher");
        thread.setDaemon(true);
        return thread;
    });

    private final AtomicReference<RunStatus> status = new AtomicReference<>(RunStatus.IDLE);
    private volatile Process process;
    private volatile Path logFile;
    private volatile Instant startedAt;
    private volatile Instant finishedAt;
    private volatile Integer exitCode;
    private volatile Set<Site> requestedSites;
    private volatile Integer requestedQuantity;

    public RadarProcessService(RadarProperties properties) {
        this.properties = properties;
    }

    public synchronized RunStatusResponse start(RunRequest request) {
        if (request.channel() == Channel.WHATSAPP) {
            throw new ChannelNotImplementedException(Channel.WHATSAPP);
        }
        if (status.get() == RunStatus.RUNNING) {
            throw new RunAlreadyInProgressException();
        }

        Set<Site> sites = request.sitesOrAll();
        String sitesArg = sites.stream().map(Site::pythonKey).collect(Collectors.joining(","));

        List<String> command = List.of(
                properties.pythonExecutable(),
                "main.py",
                "--sites", sitesArg,
                "--once",
                "--channel", request.channel().pythonKey()
        );
        if (request.quantity() != null) {
            command = new java.util.ArrayList<>(command);
            command.add("--quantity");
            command.add(String.valueOf(request.quantity()));
        }

        try {
            Path logDir = Path.of(properties.logDir());
            Files.createDirectories(logDir);
            this.logFile = logDir.resolve("run-" + System.currentTimeMillis() + ".log");

            ProcessBuilder builder = new ProcessBuilder(command)
                    .directory(new File(properties.projectDir()))
                    .redirectErrorStream(true)
                    .redirectOutput(this.logFile.toFile());

            this.process = builder.start();
        } catch (IOException e) {
            throw new UncheckedIOException("Falha ao iniciar processo Python", e);
        }

        this.requestedSites = sites;
        this.requestedQuantity = request.quantity();
        this.startedAt = Instant.now();
        this.finishedAt = null;
        this.exitCode = null;
        this.status.set(RunStatus.RUNNING);

        Process watchedProcess = this.process;
        executor.submit(() -> awaitCompletion(watchedProcess));

        return currentStatus();
    }

    private void awaitCompletion(Process watchedProcess) {
        try {
            int code = watchedProcess.waitFor();
            synchronized (this) {
                if (this.process == watchedProcess) {
                    this.exitCode = code;
                    this.finishedAt = Instant.now();
                    this.status.set(code == 0 ? RunStatus.COMPLETED : RunStatus.FAILED);
                }
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    public synchronized RunStatusResponse stop() {
        if (status.get() != RunStatus.RUNNING || process == null) {
            throw new NoRunInProgressException();
        }
        process.destroy();
        try {
            if (!process.waitFor(5, java.util.concurrent.TimeUnit.SECONDS)) {
                process.destroyForcibly();
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            process.destroyForcibly();
        }
        this.finishedAt = Instant.now();
        this.exitCode = process.exitValue();
        this.status.set(RunStatus.STOPPED);
        return currentStatus();
    }

    public RunStatusResponse currentStatus() {
        return new RunStatusResponse(
                status.get(),
                startedAt,
                finishedAt,
                exitCode,
                requestedSites,
                requestedQuantity,
                readLogTail(50)
        );
    }

    private List<String> readLogTail(int maxLines) {
        Path file = this.logFile;
        if (file == null || !Files.exists(file)) {
            return List.of();
        }
        try {
            List<String> lines = Files.readAllLines(file);
            int from = Math.max(0, lines.size() - maxLines);
            return lines.subList(from, lines.size());
        } catch (IOException e) {
            return List.of("Nao foi possivel ler o log: " + e.getMessage());
        }
    }
}
