"""Medição de tempo (time.perf_counter) e pico de memória (tracemalloc)."""
from __future__ import annotations

import time
import tracemalloc


def medir(func, *args, repeticoes_tempo: int = 1, **kwargs):
    """Executa `func` e devolve (resultado, segundos, pico_memoria_KiB).

    O tempo é medido SEM o tracemalloc ligado (ele deixa o código mais lento);
    a memória é medida numa execução separada com tracemalloc ativo.
    """
    tempos = []
    resultado = None
    for _ in range(max(1, repeticoes_tempo)):
        t0 = time.perf_counter()
        resultado = func(*args, **kwargs)
        tempos.append(time.perf_counter() - t0)

    tracemalloc.start()
    func(*args, **kwargs)
    _, pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return resultado, min(tempos), pico / 1024
