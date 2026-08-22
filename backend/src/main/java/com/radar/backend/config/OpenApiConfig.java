package com.radar.backend.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {

    @Bean
    public OpenAPI radarOpenApi() {
        return new OpenAPI().info(new Info()
                .title("Radar Backend API")
                .description(
                        "Controla o radar-python (scraper de ofertas Mercado Livre / Amazon / Shopee) "
                                + "como subprocesso e expoe os produtos ja capturados (SQLite). "
                                + "Requer Chrome aberto com --remote-debugging-port=9222, logado nos sites.")
                .version("0.1.0"));
    }
}
