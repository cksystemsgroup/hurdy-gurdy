from gurdy.core.diagnostics import Diagnostic, DiagnosticBag, Severity


def test_diagnostic_render():
    d = Diagnostic(Severity.ERROR, "E001", "boom", location="file.py:10")
    out = d.render()
    assert "[error]" in out
    assert "E001" in out
    assert "boom" in out
    assert "file.py:10" in out


def test_diagnostic_is_error_levels():
    assert Diagnostic(Severity.ERROR, "X", "x").is_error()
    assert Diagnostic(Severity.FATAL, "X", "x").is_error()
    assert not Diagnostic(Severity.WARNING, "X", "x").is_error()
    assert not Diagnostic(Severity.INFO, "X", "x").is_error()


def test_diagnostic_bag_collects_and_reports_errors():
    bag = DiagnosticBag()
    bag.add(Diagnostic(Severity.WARNING, "W", "warn"))
    bag.add(Diagnostic(Severity.ERROR, "E", "err"))
    assert len(bag) == 2
    assert bag.has_errors()
    assert len(bag.errors()) == 1
    assert bool(bag) is True
    rendered = bag.render()
    assert "warn" in rendered
    assert "err" in rendered
