# Demo

Dos procesos sueltos, en dos terminales distintas, hablándose **directo** por
HTTP. No hay broker: es el "antes" de la exposición, el estado inicial que se
rompe.

Sólo necesita Python 3. Sin dependencias, sin `pip`, sin internet.

## Correr

**Terminal 1** — el consumidor, que "trabaja" 250 ms por mensaje:

```bash
python3 sd-demo.py consumidor --puerto 9002 --work-ms 250
```

**Terminal 2** — el productor:

```bash
python3 sd-demo.py productor --rate 4 --destino http://127.0.0.1:9002/msg
```

Si corren en máquinas distintas, cambiá el destino:

```bash
python3 sd-demo.py productor --rate 4 --destino http://10.0.0.22:9002/msg
```

---

## Escenario 1 · el caso aburrido

Con el consumidor a 200 ms y el productor a 5 por segundo, todo responde.

```bash
python3 sd-demo.py productor --rate 5 --total 30 --destino http://127.0.0.1:9002/msg
```

`ok` sube al mismo ritmo que `env`, cero timeouts. Funciona, y por eso nadie ve
el problema hasta que el consumidor se pone lento en producción.

---

## Escenario 2 · el consumidor se hace lento (en vivo)

Sin reiniciar el consumidor, se le baja la velocidad:

```bash
curl -s '127.0.0.1:9002/config?work=1500'
```

Y el productor publica sin esperar a nadie:

```bash
python3 sd-demo.py productor --rate 6 --total 24 --workers 4 --timeout 2 \
        --destino http://127.0.0.1:9002/msg
```

Resultado medido: `publicados 24 · respondidos 1 · timeouts 23`.

Ahora se mira el consumidor:

```bash
curl -s 127.0.0.1:9002/stats
```

`recibidos=36 procesados=21 deuda=14`.

El productor dio por perdidos 23 mensajes; el consumidor los tiene encolados.
Los dos están convencidos de estar haciendo lo correcto, y **ninguno de los dos
puede saber qué pasó realmente con esos mensajes**.

---

## Escenario 3 · se cae el consumidor

`Ctrl+C` en la terminal 1 y se publica otra vez:

```bash
python3 sd-demo.py productor --rate 6 --total 12 --workers 2 \
        --destino http://127.0.0.1:9002/msg
```

Todos los envíos fallan. El trabajo que estaba encolado se fue con el proceso:
**no hay de dónde recuperarlo**, porque el único lugar donde existía era la
memoria de una máquina.

---

## Los tres números que importan

| número | dónde | qué significa |
|---|---|---|
| `env` vs `ok` | productor | lo que el productor **cree** que entregó |
| `timeout` | productor | lo que dejó de esperar: acá nace el "trabajo perdido" |
| `deuda` | consumidor | lo que el consumidor **sabe** que le falta |

La diferencia entre la primera columna y la tercera es el tema de la
exposición.

---

## Opciones

Productor:

| opción | por defecto | qué hace |
|---|---|---|
| `--destino` | `http://127.0.0.1:9002/msg` | a quién le entrega |
| `--rate` | `8` | mensajes por segundo |
| `--total` | `0` | cuántos manda; 0 = hasta Ctrl+C |
| `--workers` | `1` | con 1 el productor se atasca cuando el otro va lento |
| `--timeout` | `2` | segundos que espera cada pedido |
| `--stats-puerto` | `9001` | dónde publica sus contadores |

Consumidor:

| opción | por defecto | qué hace |
|---|---|---|
| `--puerto` | `9002` | dónde escucha |
| `--work-ms` | `250` | cuánto tarda cada mensaje |
| `--concurrencia` | `1` | cuántos atiende a la vez; el resto espera |

`GET /stats` devuelve los contadores en JSON y `GET /config?work=<ms>` cambia la
velocidad en caliente.
