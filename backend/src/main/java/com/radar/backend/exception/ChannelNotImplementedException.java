package com.radar.backend.exception;

import com.radar.backend.model.Channel;

public class ChannelNotImplementedException extends RuntimeException {
    public ChannelNotImplementedException(Channel channel) {
        super("Canal " + channel + " ainda nao implementado. Hoje apenas TELEGRAM esta disponivel.");
    }
}
