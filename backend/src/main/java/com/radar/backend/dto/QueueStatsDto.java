package com.radar.backend.dto;

import io.swagger.v3.oas.annotations.media.Schema;

@Schema(description = "Contagem de itens da fila (offer_queue) por site e status")
public record QueueStatsDto(
        String siteKey,
        @Schema(description = "pending | done | failed", example = "pending")
        String status,
        long count
) {
}
