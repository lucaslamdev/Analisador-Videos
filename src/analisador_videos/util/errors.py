import traceback


def format_job_error(exc: BaseException) -> str:
    """Mensagem detalhada para exibir na UI (tipo + texto + traceback)."""
    tb = traceback.format_exc()
    return f"{type(exc).__name__}: {exc}\n\n{tb}"
