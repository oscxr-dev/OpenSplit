# ADR-001: Wallet Lookup by Name Instead of ID

**Fecha:** 2026-05-17  
**Contexto:** LNBits wallet IDs en `split_targets` se almacenan como strings UUID fijos. Si el seed script corre múltiples veces o si las wallets se recrean, el ID referenciado puede quedar huérfano aunque exista otra wallet con el mismo nombre.

**Problema:** En el setup regtest se encontraron wallets duplicadas (ej: 2 wallets "Barista", 2 "Impuestos") porque el seed creó wallets nuevas con IDs distintos pero nombres idénticos. El orchestrator seguía apuntando a IDs viejos que todavía existen, pero la relación es frágil.

**Decisión:**
1. Agregar columna `lnbits_wallet_name` a `split_targets` (migración Alembic 002)
2. Al crear/actualizar targets, guardar el nombre de wallet junto al ID
3. `LNBitsClient.resolve_wallet_id(name)` — función que busca wallets por nombre en LNBits, con cache de 5min
4. El nombre se usa como respaldo si el ID no se encuentra

**Alternativa descartada:** Volumen persistente — PostgreSQL ya garantiza persistencia de IDs, pero no resuelve el caso de wallets recreadas con nombres iguales.

**Estado:** Implementado.
