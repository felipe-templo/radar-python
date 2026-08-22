package com.radar.backend.exception;

public class NoRunInProgressException extends RuntimeException {
    public NoRunInProgressException() {
        super("Nenhuma execucao em andamento para parar.");
    }
}
