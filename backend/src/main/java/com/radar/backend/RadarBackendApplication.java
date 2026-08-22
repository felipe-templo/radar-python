package com.radar.backend;

import com.radar.backend.config.RadarProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(RadarProperties.class)
public class RadarBackendApplication {

    public static void main(String[] args) {
        SpringApplication.run(RadarBackendApplication.class, args);
    }
}
