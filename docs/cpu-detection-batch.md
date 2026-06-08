# CPU: batch/stream na detecção (p5-cpu-batch-eval)

## Decisão

| Caminho | Stream/batch | Status |
|---------|--------------|--------|
| Frame cache CPU (`frame_paths`) | `model.track(source=lista_jpegs, stream=True, batch=…)` | **Implementado**, opt-in via `CPU_STREAM_DETECTION=true` (default `false`) |
| Vídeo direto CPU (sem cache) | `model.track(source=vídeo, vid_stride=…)` | **Adiado** — amostragem diferente do loop OpenCV atual |

## Frame cache — por que é seguro (com opt-in)

- Os JPEGs já foram extraídos pelo FFmpeg na ordem temporal; a lista preserva essa ordem.
- `stream=True` + `persist=True` mantém o estado do ByteTrack entre frames, como no loop frame a frame.
- `yolo_batch_size_cpu` default é `1`, então o comportamento padrão não muda.
- Não passamos `conf` no `model.track` (igual ao loop atual): limiares por classe continuam em `_process_frame_result`.

## Vídeo direto CPU — por que foi adiado

O loop atual (`_run_detection_cpu_loop` sem `frame_paths`) usa `frame_indices()`, que:

1. Calcula passo `round(fps / sample_fps)`.
2. Garante inclusão dos frames 0, 1 e 2 quando ausentes.

O caminho GPU (`vid_stride`) usa apenas o passo fixo, sem os frames extras. Replicar `vid_stride` no CPU alteraria quais frames são analisados e os timestamps dos tracks, sem testes de regressão com YOLO real.

O frame cache CPU usa amostragem FFmpeg (`fps=sample_fps`), já distinta do loop OpenCV — outro motivo para não unificar via `vid_stride` sem validação end-to-end.

## Ativar (quando quiser experimentar)

```env
CPU_STREAM_DETECTION=true
YOLO_BATCH_SIZE_CPU=1   # manter 1 até validar tracking com batch > 1
```
