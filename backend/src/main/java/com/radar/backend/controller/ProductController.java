package com.radar.backend.controller;

import com.radar.backend.dto.ProductDto;
import com.radar.backend.dto.QueueStatsDto;
import com.radar.backend.service.ProductQueryService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@Tag(name = "Produtos", description = "Leitura dos produtos ja capturados pelo radar-python (SQLite)")
@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductQueryService productQueryService;

    public ProductController(ProductQueryService productQueryService) {
        this.productQueryService = productQueryService;
    }

    @Operation(summary = "Ultimos produtos postados",
            description = "Le a tabela posted_products (dedup), mais recentes primeiro. "
                    + "`inferredSource` (ml/amazon/shopee) vem do prefixo do product_id gravado pelo Python.")
    @GetMapping("/recent")
    public List<ProductDto> recent(
            @Parameter(description = "Quantidade maxima de produtos a retornar") @RequestParam(defaultValue = "50") int limit) {
        return productQueryService.recentProducts(limit);
    }

    @Operation(summary = "Estatisticas da fila de processamento",
            description = "Contagem de itens em offer_queue agrupados por site e status (pending/failed/done).")
    @GetMapping("/queue-stats")
    public List<QueueStatsDto> queueStats() {
        return productQueryService.queueStats();
    }
}
