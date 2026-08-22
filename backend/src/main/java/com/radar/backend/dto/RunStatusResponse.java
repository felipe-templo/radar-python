package com.radar.backend.dto;

import com.radar.backend.model.RunStatus;
import com.radar.backend.model.Site;
import io.swagger.v3.oas.annotations.media.Schema;

import java.time.Instant;
import java.util.List;
import java.util.Set;

@Schema(description = "Estado atual/mais recente da execucao do subprocesso Python")
public record RunStatusResponse(
        @Schema(description = "IDLE = nunca rodou nesta instancia do backend; RUNNING = em andamento; "
                + "COMPLETED = terminou com exit code 0; FAILED = terminou com erro; STOPPED = interrompido via /stop.")
        RunStatus status,
        Instant startedAt,
        Instant finishedAt,
        @Schema(description = "Exit code do processo Python (0 = sucesso). Nulo enquanto RUNNING.")
        Integer exitCode,
        Set<Site> requestedSites,
        Integer requestedQuantity,
        @Schema(description = "Ultimas linhas do log do processo (stdout+stderr combinados).")
        List<String> logTail
) {
}
