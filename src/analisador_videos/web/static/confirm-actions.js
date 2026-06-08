(function () {
  const modalEl = document.getElementById("confirmActionModal");
  if (!modalEl || typeof bootstrap === "undefined") {
    return;
  }

  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
  const titleEl = document.getElementById("confirmActionTitle");
  const bodyEl = document.getElementById("confirmActionBody");
  const submitBtn = document.getElementById("confirmActionSubmit");
  let pendingForm = null;
  let confirmRequested = false;

  function resolveConfirmTarget(form, submitter) {
    if (submitter && submitter.dataset.confirm) {
      return submitter;
    }
    return form;
  }

  function applyVariant(target) {
    const variant = target.dataset.confirmVariant || "primary";
    submitBtn.className = "btn btn-" + variant;
  }

  function submitConfirmedForm(form) {
    const submitter = form._confirmSubmitter;
    form._confirmSubmitter = null;
    form.dataset.confirmBypass = "0";

    // Botões com name (ex.: sensitive=0/1) precisam do submitter.
    if (submitter && submitter.name && typeof form.requestSubmit === "function") {
      form.dataset.confirmBypass = "1";
      form.requestSubmit(submitter);
      return;
    }

    // Exclusão/cancelamento: submit nativo evita reabrir o modal.
    form.submit();
  }

  document.addEventListener("submit", function (event) {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) {
      return;
    }
    if (form.dataset.confirmBypass === "1") {
      form.dataset.confirmBypass = "0";
      return;
    }

    const submitter = event.submitter;
    const target = resolveConfirmTarget(form, submitter);
    const message = target.dataset.confirm || form.dataset.confirm;
    if (!message) {
      return;
    }

    event.preventDefault();
    pendingForm = form;
    pendingForm._confirmSubmitter = submitter || null;
    confirmRequested = false;

    titleEl.textContent = target.dataset.confirmTitle || "Confirmar ação";
    bodyEl.textContent = message;
    applyVariant(target);
    modal.show();
  });

  submitBtn.addEventListener("click", function () {
    if (!pendingForm) {
      return;
    }
    confirmRequested = true;
    pendingForm.dataset.confirmBypass = "1";
    modal.hide();
  });

  modalEl.addEventListener("hidden.bs.modal", function () {
    if (!pendingForm) {
      confirmRequested = false;
      return;
    }

    const form = pendingForm;
    const shouldSubmit = confirmRequested && form.dataset.confirmBypass === "1";
    pendingForm = null;
    confirmRequested = false;

    if (!shouldSubmit) {
      form.dataset.confirmBypass = "0";
      form._confirmSubmitter = null;
      return;
    }

    // Aguarda o foco do modal liberar antes do POST.
    window.setTimeout(function () {
      submitConfirmedForm(form);
    }, 0);
  });
})();
