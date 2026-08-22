package com.radar.backend.dto;

import com.radar.backend.model.Channel;
import com.radar.backend.model.Site;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import java.util.Set;

@Schema(description = "Parametros de um ciclo de scraping")
public record RunRequest(
        @Schema(description = "Sites a rodar. Vazio/omitido = todos (ML, AMAZON, SHOPEE).")
        Set<Site> sites,

        @Min(value = 1, message = "quantity deve ser >= 1")
        @Schema(description = "Quantidade de produtos por site nesta execucao (override de MAX_PRODUCTS_PER_CYCLE).", example = "20")
        Integer quantity,

        @NotNull(message = "channel e obrigatorio")
        @Schema(description = "Canal de envio. Apenas TELEGRAM esta implementado hoje; WHATSAPP retorna 400.", example = "TELEGRAM")
        Channel channel
) {
    public Set<Site> sitesOrAll() {
        return (sites == null || sites.isEmpty()) ? Set.of(Site.values()) : sites;
    }
}
