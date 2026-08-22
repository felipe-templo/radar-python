package com.radar.backend.service;

import com.radar.backend.config.RadarProperties;
import com.radar.backend.dto.ProductDto;
import com.radar.backend.dto.QueueStatsDto;
import org.springframework.stereotype.Service;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

/**
 * Leitura read-only do SQLite que o radar-python escreve (posted_products +
 * offer_queue). Nunca escreve nessas tabelas - quem escreve e o processo
 * Python; conflito de escrita concorrente nao e um cenario suportado aqui.
 */
@Service
public class ProductQueryService {

    private final RadarProperties properties;

    public ProductQueryService(RadarProperties properties) {
        this.properties = properties;
    }

    private Connection connect() throws SQLException {
        return DriverManager.getConnection("jdbc:sqlite:" + properties.dbPath() + "?busy_timeout=5000");
    }

    public List<ProductDto> recentProducts(int limit) {
        String sql = """
                SELECT product_id, name, url, discount_percent, posted_at, telegram_message_id
                FROM posted_products
                ORDER BY posted_at DESC
                LIMIT ?
                """;
        List<ProductDto> results = new ArrayList<>();
        try (Connection conn = connect(); PreparedStatement stmt = conn.prepareStatement(sql)) {
            stmt.setInt(1, limit);
            try (ResultSet rs = stmt.executeQuery()) {
                while (rs.next()) {
                    String productId = rs.getString("product_id");
                    long telegramMessageId = rs.getLong("telegram_message_id");
                    results.add(new ProductDto(
                            productId,
                            rs.getString("name"),
                            rs.getString("url"),
                            (Integer) rs.getObject("discount_percent"),
                            rs.getString("posted_at"),
                            rs.wasNull() ? null : telegramMessageId,
                            inferSource(productId)
                    ));
                }
            }
        } catch (SQLException e) {
            throw new IllegalStateException("Falha ao consultar posted_products em " + properties.dbPath(), e);
        }
        return results;
    }

    public List<QueueStatsDto> queueStats() {
        String sql = """
                SELECT site_key, status, COUNT(*) AS total
                FROM offer_queue
                GROUP BY site_key, status
                ORDER BY site_key, status
                """;
        List<QueueStatsDto> results = new ArrayList<>();
        try (Connection conn = connect();
             PreparedStatement stmt = conn.prepareStatement(sql);
             ResultSet rs = stmt.executeQuery()) {
            while (rs.next()) {
                results.add(new QueueStatsDto(rs.getString("site_key"), rs.getString("status"), rs.getLong("total")));
            }
        } catch (SQLException e) {
            throw new IllegalStateException("Falha ao consultar offer_queue em " + properties.dbPath(), e);
        }
        return results;
    }

    /**
     * O product_id gravado em posted_products e na verdade "site_key:id"
     * (ver dedup_key em radar/pipeline.py), entao o prefixo antes de ":" e
     * o site de origem real - nao e uma heuristica.
     */
    private String inferSource(String productId) {
        if (productId == null || !productId.contains(":")) {
            return "unknown";
        }
        return productId.substring(0, productId.indexOf(':'));
    }
}
