# Signet Status — Fase 6 Bloqueada

## Progreso General
- ✅ F1-F5 completos (bugfixes incluidos)
- ✅ Backup regtest: `backups/regtest-20260518/`
- ✅ docker-compose.regtest.yml guardado
- ⏸️ **F6 (Signet)** — Bloqueada

## Lo que funciona
- Configs bitcoind/lnd/lnd2 actualizados para signet
- Clave privada/pública generada para signet privado
- Llaves guardadas en `signet_keys/`
- bitcoind arranca con custom signet, healthy

## Lo que no funciona
- `generatetoaddress` no soporta firmar bloques signet en bitcoind v26.0
- Minería externa implementada en `scripts/signet_miner_final.py` pero `bad-signet-blksig`
- Public signet: DNS seeds devuelven IPs pero no se puede conectar (puertos cerrados)
- Mutinynet: requiere fork de bitcoind
- Faucets públicos: todos requieren captcha/Cloudflare, no automatizables

## Próximos pasos
  a) Debuggear el signing con python-bitcoinlib usando `contrib/signet/miner` como referencia
  b) Configurar un faucet interno en nuestro signet privado
  c) Volver a intentar cuando bitcoind v28+ tenga mejor soporte signet
