package com.radar.backend.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "radar")
public record RadarProperties(String pythonExecutable, String projectDir, String dbPath, String logDir) {
}
