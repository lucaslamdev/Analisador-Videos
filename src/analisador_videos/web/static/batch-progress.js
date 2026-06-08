(function () {
  const table = document.getElementById("batch-jobs-table");
  if (!table) return;

  const slug = table.dataset.batchSlug;
  if (!slug) return;

  const POLL_MS = 5000;

  const STATUS_LABELS = {
    queued: "Na fila",
    running: "Em execução",
    done: "Concluído",
    failed: "Falhou",
    pending: "Pendente",
    processing: "Processando",
    cancelled: "Cancelado",
  };

  const STAGE_LABELS = {
    ingest: "Ingestão",
    extract: "Extração de frames",
    detect: "Detecção",
    merge: "Mesclagem",
    media: "Mídia",
    reports: "Relatórios",
    done: "Finalizado",
  };

  let timer = null;

  function statusBadgeHtml(status) {
    const label = STATUS_LABELS[status] || status;
    return (
      '<span class="badge rounded-pill badge-status badge-status-' +
      status +
      '">' +
      label +
      "</span>"
    );
  }

  function formatProgress(job) {
    const parts = [];
    if (job.stage) {
      parts.push(STAGE_LABELS[job.stage] || job.stage);
    }
    parts.push(job.progress_pct + "%");
    if (job.frames_total) {
      parts.push("(" + (job.frames_done || 0) + "/" + job.frames_total + ")");
    }
    return parts.join(" · ");
  }

  function updateRow(job) {
    const row = table.querySelector('tr[data-job-id="' + job.id + '"]');
    if (!row) return;
    const statusCell = row.querySelector(".job-status-cell");
    const progressCell = row.querySelector(".job-progress-cell");
    if (statusCell) statusCell.innerHTML = statusBadgeHtml(job.status);
    if (progressCell) progressCell.textContent = formatProgress(job);
  }

  async function poll() {
    try {
      const res = await fetch("/lotes/" + encodeURIComponent(slug) + "/jobs-status");
      if (!res.ok) return;
      const data = await res.json();
      (data.jobs || []).forEach(updateRow);
      if (!data.active_jobs_count && timer !== null) {
        clearInterval(timer);
        timer = null;
      }
    } catch (_err) {
      /* próximo ciclo */
    }
  }

  timer = setInterval(poll, POLL_MS);
  poll();
})();
