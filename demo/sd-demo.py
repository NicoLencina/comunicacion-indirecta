#!/usr/bin/env python3
"""
sd-demo.py — productor y consumidor para la demo de comunicación indirecta.

Los dos roles viven en el mismo archivo para copiar uno solo a cada máquina.
Sólo biblioteca estándar: no hace falta pip ni internet en el aula.

  # terminal 1 · el consumidor
  python3 sd-demo.py consumidor --puerto 9002 --work-ms 250

  # terminal 2 · el productor
  python3 sd-demo.py productor --rate 8 --destino http://127.0.0.1:9002/msg

  # en cualquier lado, para mirar o para cambiar el ritmo en vivo
  curl -s 127.0.0.1:9002/stats
  curl -s '127.0.0.1:9002/config?work=900'
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs


# ───────────────────────────── consumidor ─────────────────────────────
class Estado:
    """Lo que el consumidor cuenta, y lo que la banda de arriba va a leer."""

    def __init__(self, work_ms: int, concurrencia: int) -> None:
        self.lock = threading.Lock()
        self.work_ms = work_ms
        self.concurrencia = concurrencia
        # El freno: cuántos mensajes se procesan a la vez. Si es 1, el resto
        # espera, y eso es lo que hace aparecer los timeouts del otro lado.
        self.sem = threading.BoundedSemaphore(concurrencia)
        self.recibidos = 0
        self.procesados = 0
        self.en_proceso = 0
        self.errores = 0
        self.desde = time.time()

    def llegar(self) -> None:
        """El mensaje llegó: cuenta como recibido aunque todavía no se atienda."""
        with self.lock:
            self.recibidos += 1

    def entrar(self) -> None:
        """Espera turno. Acá es donde se arma la cola de espera."""
        self.sem.acquire()
        with self.lock:
            self.en_proceso += 1

    def salir(self, ok: bool = True) -> None:
        with self.lock:
            self.en_proceso -= 1
            if ok:
                self.procesados += 1
            else:
                self.errores += 1
        self.sem.release()

    def resumen(self) -> dict:
        with self.lock:
            return {
                "rol": "consumidor",
                "recibidos": self.recibidos,
                "procesados": self.procesados,
                "en_proceso": self.en_proceso,
                "errores": self.errores,
                "deuda": max(0, self.recibidos - self.procesados - self.en_proceso),
                "work_ms": self.work_ms,
                "concurrencia": self.concurrencia,
                "uptime_s": round(time.time() - self.desde, 1),
            }


class Handler(BaseHTTPRequestHandler):
    estado: Estado = None  # type: ignore[assignment]

    # ── POST /msg : el productor entrega un mensaje y espera la respuesta ──
    def do_POST(self) -> None:
        ruta = urlparse(self.path).path
        if ruta != "/msg":
            self.send_error(404)
            return

        largo = int(self.headers.get("Content-Length") or 0)
        cuerpo = self.rfile.read(largo).decode("utf-8", "replace")

        self.estado.llegar()
        self.estado.entrar()
        try:
            time.sleep(self.estado.work_ms / 1000.0)   # acá "se trabaja"
        except Exception:
            self.estado.salir(ok=False)
            self.send_error(500)
            return
        self.estado.salir(ok=True)

        cuerpo_resp = json.dumps({"ok": True, "eco": cuerpo[:80]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo_resp)))
        self.end_headers()
        self.wfile.write(cuerpo_resp)

    # ── GET /stats y /config : para mirar y para cambiar en vivo ──
    def do_GET(self) -> None:
        u = urlparse(self.path)

        if u.path == "/stats":
            cuerpo_resp = json.dumps(self.estado.resumen()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(cuerpo_resp)))
            self.end_headers()
            self.wfile.write(cuerpo_resp)
            return

        if u.path == "/config":
            q = parse_qs(u.query)
            if "work" in q:
                self.estado.work_ms = max(0, int(float(q["work"][0])))
            # la concurrencia se fija al arrancar: cambiarla en caliente
            # necesitaría redimensionar el semáforo y no vale la pena
            cuerpo_resp = json.dumps(self.estado.resumen()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(cuerpo_resp)))
            self.end_headers()
            self.wfile.write(cuerpo_resp)
            return

        if u.path == "/":
            texto = (
                "consumidor de la demo\n"
                "  POST /msg        recibe un mensaje y lo procesa\n"
                "  GET  /stats      contadores\n"
                "  GET  /config?work=900&concurrencia=1\n"
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(texto)))
            self.end_headers()
            self.wfile.write(texto)
            return

        self.send_error(404)

    def log_message(self, *args) -> None:
        pass  # la consola es para los números, no para el access log


def cmd_consumidor(a: argparse.Namespace) -> int:
    estado = Estado(a.work_ms, a.concurrencia)
    Handler.estado = estado

    try:
        srv = ThreadingHTTPServer((a.host, a.puerto), Handler)
    except OSError as e:
        if e.errno == 98:      # EADDRINUSE
            print(f"\n  El puerto {a.puerto} ya está ocupado: parece que hay otro\n"
                  f"  consumidor corriendo. Bajalo con:\n\n"
                  f"      pkill -f '[s]d-demo'\n\n"
                  f"  (los corchetes evitan que pkill mate la propia línea de comando)\n")
            return 1
        raise
    srv.daemon_threads = True

    def resumen_periodico() -> None:
        while True:
            time.sleep(1)
            r = estado.resumen()
            print(
                f"\rrecibidos={r['recibidos']:<6} procesados={r['procesados']:<6} "
                f"en_proceso={r['en_proceso']:<3} deuda={r['deuda']:<6} "
                f"work={r['work_ms']}ms",
                end="", flush=True,
            )

    threading.Thread(target=resumen_periodico, daemon=True).start()

    print(f"consumidor escuchando en {a.host}:{a.puerto}  work={a.work_ms}ms")
    print("  Ctrl+C para matarlo (esto es la escena «se cae el consumidor»)\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        r = estado.resumen()
        print(f"\n\ncerrado · recibidos={r['recibidos']} procesados={r['procesados']}")
    return 0


# ───────────────────────────── productor ──────────────────────────────
def cmd_productor(a: argparse.Namespace) -> int:
    env, ok, timeout, error = 0, 0, 0, 0
    pendientes = 0
    lock = threading.Lock()
    frenar = threading.Event()
    t0 = time.time()
    intervalo = 1.0 / a.rate if a.rate > 0 else 0.0

    def entregar(n: int) -> None:
        nonlocal ok, timeout, error, pendientes
        cuerpo = json.dumps({"id": n, "t": round(time.time(), 3)}).encode()
        req = urllib.request.Request(
            a.destino, data=cuerpo,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with lock:
            pendientes += 1
        try:
            with urllib.request.urlopen(req, timeout=a.timeout) as r:
                r.read()
            with lock:
                ok += 1
        except (socket.timeout, TimeoutError):
            with lock:
                timeout += 1
        except urllib.error.HTTPError:
            with lock:
                error += 1
        except urllib.error.URLError as e:
            # timeout de socket viene envuelto acá a veces
            with lock:
                if isinstance(getattr(e, "reason", None), (socket.timeout, TimeoutError)):
                    timeout += 1
                else:
                    error += 1
        except Exception:
            with lock:
                error += 1
        finally:
            with lock:
                pendientes -= 1

    def reporte() -> None:
        while not frenar.is_set():
            time.sleep(1)
            with lock:
                e_, o, t, x, p = env, ok, timeout, error, pendientes
            print(
                f"\r[{time.time()-t0:6.1f}s] env={e_:<6} ok={o:<6} "
                f"timeout={t:<6} err={x:<4} en_vuelo={p:<3}",
                end="", flush=True,
            )

    threading.Thread(target=reporte, daemon=True).start()

    # ── /stats : lo que lee la banda de arriba ──
    if a.stats_puerto:
        class HStats(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if urlparse(self.path).path != "/stats":
                    self.send_error(404)
                    return
                with lock:
                    d = {"rol": "productor", "publicados": env, "ok": ok,
                         "timeout": timeout, "errores": error, "en_vuelo": pendientes}
                b = json.dumps(d).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def log_message(self, *args) -> None:
                pass

        try:
            sstats = ThreadingHTTPServer(("0.0.0.0", a.stats_puerto), HStats)
            sstats.daemon_threads = True
            threading.Thread(target=sstats.serve_forever, daemon=True).start()
        except OSError:
            print(f"  (puerto {a.stats_puerto} ocupado: la banda no va a leer este productor)")

    print(f"productor → {a.destino}  ritmo={a.rate}/s  workers={a.workers}  timeout={a.timeout}s")
    print("  Ctrl+C para cortar\n")

    hebras: list[threading.Thread] = []
    n = 0
    try:
        while True:
            if a.total and n >= a.total:
                break
            n += 1
            with lock:
                env += 1
            if a.workers <= 1:
                entregar(n)                       # secuencial: el ritmo manda
            else:
                h = threading.Thread(target=entregar, args=(n,), daemon=True)
                h.start()
                hebras.append(h)
                hebras = [x for x in hebras if x.is_alive()]
                if len(hebras) >= a.workers:
                    hebras[0].join()
            if intervalo:
                time.sleep(intervalo)
        for h in hebras:
            h.join()
    except KeyboardInterrupt:
        pass

    frenar.set()
    with lock:
        e_, o, t, x = env, ok, timeout, error
    dur = time.time() - t0
    print("\n")
    print("─" * 62)
    print(f"  publicados {e_} en {dur:.1f}s")
    print(f"  respondidos {o}   timeouts {t}   errores {x}")
    perdidos = e_ - o
    if perdidos:
        print(f"  ⚠  {perdidos} mensajes no se completaron: eso es trabajo perdido")
    else:
        print("  todo respondió: nadie perdió trabajo")
    print("─" * 62)
    return 0


# ─────────────────────────────── cli ──────────────────────────────────
def main() -> int:
    p = argparse.ArgumentParser(description="Productor y consumidor de la demo")
    sub = p.add_subparsers(dest="rol", required=True)

    c = sub.add_parser("consumidor", help="atiende mensajes por HTTP")
    c.add_argument("--host", default="0.0.0.0")
    c.add_argument("--puerto", type=int, default=9002)
    c.add_argument("--work-ms", type=int, default=250, dest="work_ms",
                   help="cuánto tarda procesar cada mensaje")
    c.add_argument("--concurrencia", type=int, default=1)
    c.set_defaults(func=cmd_consumidor)

    pr = sub.add_parser("productor", help="genera mensajes contra un consumidor")
    pr.add_argument("--destino", default="http://127.0.0.1:9002/msg")
    pr.add_argument("--rate", type=float, default=8.0, help="mensajes por segundo")
    pr.add_argument("--total", type=int, default=0, help="0 = hasta Ctrl+C")
    pr.add_argument("--workers", type=int, default=1,
                    help="1 = secuencial, el productor se atasca cuando el otro va lento")
    pr.add_argument("--timeout", type=float, default=2.0)
    pr.add_argument("--stats-puerto", type=int, default=9001, dest="stats_puerto",
                    help="puerto donde publica sus contadores para la banda (0 = no publicar)")
    pr.set_defaults(func=cmd_productor)

    a = p.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
