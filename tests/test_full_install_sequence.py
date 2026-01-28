from raijin_server.modules.full_install import INSTALL_SEQUENCE


def test_full_install_includes_secrets():
    names = [name for name, *_ in INSTALL_SEQUENCE]
    assert "secrets" in names


def test_full_install_includes_cert_manager():
    names = [name for name, *_ in INSTALL_SEQUENCE]
    assert "cert_manager" in names
