package com.radar.backend.controller;

import com.radar.backend.dto.RunRequest;
import com.radar.backend.dto.RunStatusResponse;
import com.radar.backend.service.RadarProcessService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@Tag(name = "Radar", description = "Controle do subprocesso Python (disparar ciclo de scraping, status, parar)")
@RestController
@RequestMapping("/api/radar")
public class RadarController {

    private final RadarProcessService processService;

    public RadarController(RadarProcessService processService) {
        this.processService = processService;
    }

    @Operation(
            summary = "Dispara um ciclo unico de scraping",
            description = "Roda `main.py --once` com os sites, quantidade e canal informados. "
                    + "`sites` vazio/omitido = ML + AMAZON + SHOPEE. `quantity` e por site. "
                    + "Requer Chrome aberto com --remote-debugging-port=9222 ja logado nos sites.",
            responses = {
                    @ApiResponse(responseCode = "202", description = "Execucao iniciada, status RUNNING"),
                    @ApiResponse(responseCode = "400", description = "Canal WHATSAPP (nao implementado) ou payload invalido"),
                    @ApiResponse(responseCode = "409", description = "Ja existe uma execucao em andamento")
            }
    )
    @PostMapping("/run")
    public ResponseEntity<RunStatusResponse> run(@Valid @RequestBody RunRequest request) {
        RunStatusResponse response = processService.start(request);
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(response);
    }

    @Operation(summary = "Consulta o status da execucao atual/mais recente",
            description = "Inclui timestamps, exit code e as ultimas linhas do log do subprocesso Python.")
    @GetMapping("/status")
    public RunStatusResponse status() {
        return processService.currentStatus();
    }

    @Operation(
            summary = "Interrompe a execucao em andamento",
            description = "Mata o subprocesso Python (SIGTERM, com fallback para kill forcado apos 5s).",
            responses = {
                    @ApiResponse(responseCode = "200", description = "Processo interrompido"),
                    @ApiResponse(responseCode = "409", description = "Nenhuma execucao em andamento")
            }
    )
    @PostMapping("/stop")
    public RunStatusResponse stop() {
        return processService.stop();
    }
}
