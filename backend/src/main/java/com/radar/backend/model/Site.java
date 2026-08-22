package com.radar.backend.model;

public enum Site {
    ML("ml"),
    AMAZON("amazon"),
    SHOPEE("shopee");

    private final String pythonKey;

    Site(String pythonKey) {
        this.pythonKey = pythonKey;
    }

    public String pythonKey() {
        return pythonKey;
    }
}
