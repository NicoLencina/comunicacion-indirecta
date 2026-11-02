# Comunicación indirecta

Presentación y demo de la exposición de **Sistemas Distribuidos** (Grupo 7):
qué gana un sistema cuando entre dos procesos aparece un tercero que guarda los
mensajes.

El eje del trabajo es distinguir dos cosas que suelen confundirse: **difundir**
(un evento llega a todos los suscriptores) y **repartir** (cada tarea la resuelve
un solo worker). Se explica con Kafka y RabbitMQ, y se muestra en vivo qué pasa
cuando el consumidor va más lento que el productor y cuando se cae.

---

## La presentación

[`index.html`](index.html) — un solo archivo. Sin dependencias, sin internet,
sin fuentes externas.

Abrilo con doble click, o:

```bash
xdg-open index.html
```

| tecla | qué hace |
|---|---|
| `←` `→` | navegar |
| `n` | notas del orador con los tiempos |
| `e` | modo edición (se guarda solo en el navegador) |
| `f` | pantalla completa |
| `Home` / `End` | primera / última |

En modo edición se puede hacer click en cualquier texto y escribir. El botón
**Guardar .html** baja una copia con los cambios adentro; **Deshacer** vuelve al
original.

Para PDF: `Ctrl+P`, destino «Guardar como PDF», márgenes «Ninguno», gráficos de
fondo activados. Cada hoja sale en su propia página.

---

## La demo

[`demo/`](demo/) — un productor y un consumidor que se hablan directo por HTTP,
sin broker. Sólo hace falta Python 3: no hay que instalar nada.

```bash
# terminal 1
python3 demo/sd-demo.py consumidor --puerto 9002 --work-ms 250

# terminal 2
python3 demo/sd-demo.py productor --rate 4 --destino http://127.0.0.1:9002/msg
```

Mientras corre, se le puede bajar la velocidad al consumidor **en vivo**, sin
reiniciar nada:

```bash
curl -s '127.0.0.1:9002/config?work=1500'
```

Ahí aparecen los timeouts del lado del productor aunque el consumidor tenga los
mensajes encolados. Ese desacuerdo —cada uno convencido de estar haciendo lo
correcto, y ninguno capaz de saber qué pasó realmente— es el motivo por el que
existe un broker.

Los tres escenarios y qué decir en cada uno están en
[`demo/README.md`](demo/README.md).

---

## Contenido

```
index.html          la presentación
demo/sd-demo.py     productor y consumidor (un archivo, dos roles)
demo/README.md      escenarios y qué mirar
```
