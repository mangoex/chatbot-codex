# Plan — CHG-012

## Pruebas que deben fallar primero

1. Equivalencia: para configuraciones ficticias de los cuatro modos, el responsable traducido tiene que ser el del camino legado. Antes de las tablas, el módulo de decisión no existe y la prueba ni colecta.
2. Migración sobre Postgres de prueba: dos corridas dejan el mismo número de reglas, un cambio de URL se refleja, y el reverso borra solo lo que originó `chg-012`.
3. `POST /api/v1/bots/{bot_id}/reply` con secreto en la query responde 400. Con el flag apagado responde 409.

## Fases

1. Esta. Modelo, migración reversible, flag apagado, alias condicionado, equivalencia. El pipeline legado se queda.
2. Después del OK de Miguel, encender el flag en un bot ficticio o de prueba y revisar el contrato con el externo.
3. Solo con bots ya movidos y otro OK, retirar `handle_inbound` y `forward_all`. No forma parte de este PR.

## Rollback

`routing_migrate.reverse_all()` borra reglas, conexiones y secretos con origen `chg-012`, apaga `routing_v2_enabled` y no toca `bot_integrations`. Las tablas pueden quedarse vacías. El camino legado no depende de ellas.

## Deploy

No se despliega en esta fase. Aunque se desplegara, el flag nace apagado y la reconciliación, si falla, se registra y no tumba el arranque.
