"""Unit tests for app/container.py — Container.close(). Lot 14,
docs/refactoring-plan.md ("own and close clients/resources").
"""
from __future__ import annotations

from modular_rag.app.container import Container
from modular_rag.contracts.manifests import ComponentConfig, PipelineManifest


class _ClosableComponent:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FailingCloseComponent:
    def close(self) -> None:
        raise RuntimeError("close failed")


class _NoCloseComponent:
    """No close() at all — most components (chunkers, evaluators) are like
    this; Container.close() must skip them without error."""


def _container() -> Container:
    manifest = PipelineManifest(
        id="test-pipeline",
        chunker=ComponentConfig(type="fake"),
        embedder=ComponentConfig(type="fake"),
        indexer=ComponentConfig(type="fake"),
        retriever=ComponentConfig(type="fake"),
        generator=ComponentConfig(type="fake"),
    )
    return Container(manifest)


def test_close_calls_close_on_every_closable_component():
    container = _container()
    indexer = _ClosableComponent()
    generator = _ClosableComponent()
    container.register("indexer", indexer)
    container.register("generator", generator)

    container.close()

    assert indexer.closed is True
    assert generator.closed is True


def test_close_skips_components_without_a_close_method():
    container = _container()
    container.register("chunker", _NoCloseComponent())

    container.close()  # must not raise


def test_close_continues_after_one_component_fails_to_close():
    container = _container()
    ok = _ClosableComponent()
    container.register("indexer", _FailingCloseComponent())
    container.register("generator", ok)

    container.close()  # must not raise

    assert ok.closed is True  # the failure didn't stop the rest from closing
