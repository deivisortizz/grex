const WebSocket = require('ws');

const url = "wss://mainnet.helius-rpc.com/?api-key=afef48e6-b88a-49e6-84c4-9b408156ee55";

console.log("Iniciando teste isolado de conexão com Helius...");
const ws = new WebSocket(url);

ws.on('open', () => {
    console.log("[SUCESSO] Conectado ao WebSocket da Helius!");

    const subPayload = JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        method: "logsSubscribe",
        params: ["all", { commitment: "processed" }]
    });

    ws.send(subPayload);
    console.log("[ENVIO] Mensagem de subscrição enviada. Aguardando pacotes...");
});

ws.on('message', (data) => {
    const response = JSON.parse(data.toString());
    console.log("[DADOS RECEBIDOS] Pacote capturado com sucesso:", response.method || "Confirmação de ID");
    ws.close();
    process.exit(0);
});

ws.on('error', (err) => {
    console.error("[ERRO] Falha na conexão WebSocket:", err.message);
    process.exit(1);
});