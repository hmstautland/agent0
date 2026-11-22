from storage import integrations


def test_off_by_default_and_toggles():
    assert integrations.is_enabled("kush-explain") is False
    integrations.set_enabled("kush-explain", True)
    assert integrations.is_enabled("kush-explain") is True
    integrations.set_enabled("kush-explain", False)
    assert integrations.is_enabled("kush-explain") is False


def test_flags_are_independent():
    integrations.set_enabled("a", True)
    assert integrations.is_enabled("b") is False
