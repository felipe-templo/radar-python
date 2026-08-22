package com.radar.backend.model;

public enum Channel {
    TELEGRAM,
    WHATSAPP;

    public String pythonKey() {
        return name().toLowerCase();
    }
}
