package com.radar.backend.exception;

public class RunAlreadyInProgressException extends RuntimeException {
    public RunAlreadyInProgressException() {
        super("Ja existe uma execucao em andamento. Aguarde terminar ou chame /api/radar/stop.");
    }
}
