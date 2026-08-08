from modular_rag.app.application import ApplicationService


class _Native:
    manifest_id = "test"

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _Selected:
    def name(self) -> str:
        return "selected-engine"


def test_application_exposes_selected_engine_name() -> None:
    service = ApplicationService(_Native(), _Selected())  # type: ignore[arg-type]

    assert service.engine_name == "selected-engine"


def test_application_closes_native_container_resources() -> None:
    native = _Native()
    service = ApplicationService(native, _Selected())  # type: ignore[arg-type]

    service.close()

    assert native.closed is True
