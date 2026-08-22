package com.radar.backend.dto;

import io.swagger.v3.oas.annotations.media.Schema;

@Schema(description = "Produto ja postado (linha de posted_products)")
public record ProductDto(
        @Schema(description = "product_id gravado pelo Python, formato 'site_key:id' (ex: ml:MLB123456)")
        String productId,
        String name,
        String url,
        Integer discountPercent,
        @Schema(description = "Timestamp ISO de quando foi postado")
        String postedAt,
        @Schema(description = "ID da mensagem no Telegram, nulo se DRY_RUN=true")
        Long telegramMessageId,
        @Schema(description = "Site de origem (ml/amazon/shopee), extraido do prefixo de productId")
        String inferredSource
) {
}
