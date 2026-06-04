# Analisador de Vídeos

Sistema de análise de vídeos MP4 com detecção **YOLO11n** (80 classes COCO), tracking ByteTrack, clipes, supercuts, evidências visuais e relatórios forenses (HTML, JSON, CSV, PDF). Interface web e API REST.

Repositório: [github.com/lucaslamdev/Analisador-Videos](https://github.com/lucaslamdev/Analisador-Videos)

---

## O que você precisa

| Requisito | Versão / nota |
|-----------|----------------|
| **Python** | 3.12 ou superior |
| **FFmpeg** | No `PATH` (obrigatório para clipes, cache de frames e supercuts) |
| **Git** | Para clonar o repositório |
| **GPU NVIDIA** | Opcional — acelera a inferência (`DEVICE=cuda`) |

Espaço em disco: vídeos de entrada, `data/` (clipes, snapshots, relatórios, SQLite) e cache de frames em CPU podem ocupar vários GB.

---

## Instalação em qualquer computador

### 1. Clonar o projeto

```bash
git clone https://github.com/lucaslamdev/Analisador-Videos.git
cd Analisador-Videos
```

### 2. Ambiente virtual (recomendado)

**Windows (PowerShell):**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**Linux / macOS:**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> Sem venv: use `pip install -r requirements.txt` no Python 3.12+ global (menos isolado, mas funciona).

### 3. FFmpeg

O app chama `ffmpeg` e `ffprobe` pelo terminal. Instale e confira:

```bash
ffmpeg -version
ffprobe -version
```

| SO | Como instalar |
|----|----------------|
| **Windows** | [ffmpeg.org/download](https://ffmpeg.org/download.html) (build gyan.dev ou winget: `winget install Gyan.FFmpeg`) e adicione a pasta `bin` ao **PATH** do sistema |
| **Ubuntu/Debian** | `sudo apt update && sudo apt install ffmpeg` |
| **macOS** | `brew install ffmpeg` |

Reabra o terminal após alterar o PATH.

### 4. Configuração (`.env`)

Na raiz do projeto:

```bash
cp .env.example .env
```

Edite `.env` se precisar mudar pastas, limiares ou fila de jobs. O arquivo `.env` **não vai para o Git** — cada máquina tem o seu.

**Perfis prontos** (copie um deles em vez do `.env.example` se quiser):

| Perfil | Arquivo | Uso típico |
|--------|---------|------------|
| CPU Intel | `.env.cpu-intel.example` | 2 jobs em paralelo, cache de frames FFmpeg |
| GPU RTX | `.env.gpu-rtx4060.example` | 1 job, YOLO em CUDA, stream no vídeo |

```bash
# Exemplo: máquina só com CPU
cp .env.cpu-intel.example .env

# Exemplo: máquina com NVIDIA
cp .env.gpu-rtx4060.example .env
```

Na primeira análise, o **Ultralytics** baixa automaticamente o modelo `yolo11n.pt` (fica na pasta do projeto; está no `.gitignore`).

### 5. Pastas de trabalho

Na primeira execução o app cria:

- `data/` — banco SQLite, vídeos processados, clipes, snapshots, supercuts, relatórios
- `incoming/` — coloque aqui os MP4 para processar em lote

Essas pastas também estão no `.gitignore`; em outro PC você começa vazio (só código + `.env`).

---

## Executar o servidor

Sempre na **raiz** do repositório, com o venv ativo:

```bash
python -m uvicorn analisador_videos.main:app --host 127.0.0.1 --port 8000 --reload --app-dir src
```

Abra no navegador: **http://127.0.0.1:8000**

Para aceitar conexões na rede local (outro PC na mesma rede):

```bash
python -m uvicorn analisador_videos.main:app --host 0.0.0.0 --port 8000 --reload --app-dir src
```

**Verificar se está tudo certo:**

```bash
curl http://127.0.0.1:8000/health
```

Resposta esperada inclui `backend`, `device_name` e `max_concurrent_jobs`.

Documentação interativa da API: **http://127.0.0.1:8000/docs**

---

## Uso rápido (interface web)

| Página | URL | Função |
|--------|-----|--------|
| Início | `/` | Upload de MP4 ou processar pasta `incoming/` |
| Jobs | `/jobs` | Fila, progresso, cancelar, excluir, exportar, **job v2** (bbox sensível) |
| Detalhe do job | `/jobs/{id}` | Relatórios, supercut, anotações |
| Eventos | `/events` | Galeria com filtros (classe, vídeo, horário, etc.) |
| Evento | `/events/{id}` | Clipe, snapshots, bbox padrão/sensível |
| Lote | `/lotes/{slug}` | Vários vídeos, relatório do lote, ZIP de supercuts |

**Fluxo típico**

1. Envie um ou mais `.mp4` pela página inicial **ou** copie vídeos para `incoming/` e use *Processar pasta*.
2. Acompanhe em **Jobs** até o status `completed`.
3. Veja detecções em **Eventos**; abra um evento para clipe e evidências.
4. Gere **supercut** por vídeo (botão na UI ou API).
5. Opcional: **Bbox no vídeo** (YOLO desenhando caixas) — modo padrão ou **sensível** (limiares mais baixos, útil para pessoas difíceis).
6. Opcional: **Job/Lote v2** — nova passagem só de bbox sensível + relatórios `v2`, mantendo a versão original para comparar.

**Lotes:** processar `incoming/` cria um slug `lote{N}-DD-MM-YYYY`. Relatório HTML: `/lotes/{slug}/relatorio`.

---

## API (resumo)

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `POST` | `/process` | Inicia job (upload multipart ou `{"source":"folder"}`) |
| `GET` | `/status/{job_id}` | Progresso do job |
| `GET` | `/health` | Backend, device, fila |
| `GET` | `/events`, `/events/{id}` | Lista / detalhe de eventos |
| `GET` | `/videos/{id}/supercut` | Supercut (query `?download=1` para baixar) |
| `POST` | `/videos/{id}/annotate-supercut` | Gera supercut com bbox |
| `POST` | `/events/{event_id}/annotate-clip` | Gera clipe com bbox |
| `POST` | `/jobs/{job_id}/cancel` | Cancela job em fila/execução |
| `DELETE` | `/jobs/{job_id}` | Remove job e **todos** os arquivos ligados ao vídeo |
| `GET` | `/jobs/{job_id}/reports/{format}` | `html`, `json`, `csv`, `pdf` |
| `POST` | `/jobs/{job_id}/sensitive-v2` | Job filho com bbox sensível + relatórios v2 |
| `GET` | `/lotes/{slug}` | Detalhe do lote |
| `POST` | `/lotes/{slug}/cancel` | Cancela jobs do lote |
| `DELETE` | `/lotes/{slug}` | Exclui lote e vídeos associados |
| `GET` | `/lotes/{slug}/supercuts.zip` | ZIP com supercuts do lote |
| `GET` | `/lotes/{slug}/reports/{format}` | Relatório agregado do lote |

Clipe/supercut anotado: rotas `.../clip/annotated` e `.../supercut/annotated` com `?sensitive=1` quando existir versão sensível.

---

## Duas máquinas (CPU vs GPU)

Use perfis diferentes copiando o `.env` adequado em cada PC. O mesmo repositório Git serve para as duas; **não** versione `data/` nem `.env`.

| Perfil | Jobs paralelos | Detecção | Estimativa (72 vídeos × 1 h) |
|--------|----------------|----------|------------------------------|
| Intel CPU | 2 | Cache FFmpeg + YOLO frame a frame | ~2–3 dias |
| RTX 4060 | 1 | `stream=True` + stride no vídeo | ~10–18 h |

`DEVICE=auto` tenta CUDA e cai para CPU se `ALLOW_CPU_FALLBACK=true`.

---

## Configuração (`.env`)

Principais variáveis (lista completa em `.env.example`):

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `DATA_DIR` | `data` | Raiz de mídia e SQLite |
| `VIDEOS_INPUT_DIR` | `incoming` | Pasta monitorada para lotes |
| `DEVICE` | `auto` | `auto`, `cpu` ou `cuda` |
| `SAMPLE_FPS` | `1` | Amostragem (1 frame/s de vídeo real) |
| `CONFIDENCE_THRESHOLD` | `0.5` | Limiar geral de detecção |
| `ANNOTATE_SENSITIVE_CONFIDENCE` | `0.22` | Bbox sensível (pessoa) |
| `ANNOTATE_SENSITIVE_VEHICLE_CONFIDENCE` | `0.18` | Bbox sensível (veículos) |
| `MAX_CONCURRENT_JOBS_CPU` | `2` | Fila em CPU |
| `MAX_CONCURRENT_JOBS_GPU` | `1` | Fila em GPU |
| `GENERATE_REPORTS_ON_COMPLETE` | `false` | Se `true`, gera PDF/CSV/JSON ao terminar cada job |

---

## Testes

Com o venv ativo, na raiz do projeto:

```bash
python -m pytest tests/ -v
```

Não é necessário GPU nem vídeos reais para a suíte de testes.

---

## Problemas comuns

| Sintoma | O que fazer |
|---------|-------------|
| `ffmpeg` não encontrado | Instale FFmpeg e confira `ffmpeg -version` no **mesmo** terminal em que roda o uvicorn |
| Muito lento em CPU | Use perfil `.env.cpu-intel.example`; reduza vídeos simultâneos; confira `FRAME_CACHE_ENABLED_CPU=true` |
| CUDA não usada | Instale driver NVIDIA + PyTorch com CUDA; defina `DEVICE=cuda` no `.env` |
| Erro ao importar módulo | Use `--app-dir src` e rode a partir da raiz do clone |
| Pasta `data/` vazia após clone | Normal — dados são locais; reprocesse vídeos nesta máquina |
| Lote não acha vídeos em subpastas | MP4 devem estar em `incoming/` **ou subpastas** (versão atual); rode uvicorn na **raiz** do projeto; veja logs `scan_folder` com `--log-level info` |
| Modelo YOLO não baixa | Verifique internet no primeiro job; proxy/firewall pode bloquear download do Ultralytics |

---

## Estrutura do repositório

```
Analisador-Videos/
├── src/analisador_videos/   # App FastAPI, pipeline, relatórios, web
├── tests/                   # Pytest
├── incoming/                # Entrada de MP4 para lotes (criada em runtime)
├── data/                    # Saída local (não versionada)
├── .env.example             # Modelo de configuração
├── .env.cpu-intel.example
├── .env.gpu-rtx4060.example
└── requirements.txt
```

Spec e plano de implementação: `docs/superpowers/`.

---

## Licença e contribuição

Projeto de uso local / forense. Para atualizar o código em outra máquina: `git pull` na pasta do clone, reative o venv, `pip install -r requirements.txt` se `requirements.txt` mudou, e reinicie o uvicorn.
