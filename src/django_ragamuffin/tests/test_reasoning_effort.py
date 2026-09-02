from django.test import override_settings

from django_ragamuffin.models import get_reasoning_effort, get_reasoning_options


@override_settings(EFFORT="low")
def test_environment_effort_takes_precedence(monkeypatch):
    monkeypatch.setenv("EFFORT", "high")

    assert get_reasoning_effort() == "high"
    assert get_reasoning_options() == {"effort": "high", "summary": "auto"}


@override_settings(EFFORT="low")
def test_django_effort_used_without_environment_override(monkeypatch):
    monkeypatch.delenv("EFFORT", raising=False)

    assert get_reasoning_effort() == "low"


@override_settings(EFFORT="")
def test_reasoning_effort_defaults_to_medium(monkeypatch):
    monkeypatch.delenv("EFFORT", raising=False)

    assert get_reasoning_effort() == "medium"


@override_settings(EFFORT="low")
def test_blank_environment_effort_does_not_override_django(monkeypatch):
    monkeypatch.setenv("EFFORT", "   ")

    assert get_reasoning_effort() == "low"
