from raijin_server.cli import MODULES, MODULE_DESCRIPTIONS
from raijin_server.validators import check_module_dependencies
from raijin_server.utils import ExecutionContext


def test_secrets_registered_in_cli():
    assert "secrets" in MODULES
    assert "secrets" in MODULE_DESCRIPTIONS


def test_cert_manager_registered_in_cli():
    assert "cert_manager" in MODULES
    assert "cert_manager" in MODULE_DESCRIPTIONS


def test_secrets_dependency_on_kubernetes(tmp_path):
    ctx = ExecutionContext(dry_run=True)
    # Em dry-run, dependencias sao ignoradas mas funcao deve retornar True
    assert check_module_dependencies("secrets", ctx) is True


def test_cert_manager_dependency(tmp_path):
    ctx = ExecutionContext(dry_run=True)
    assert check_module_dependencies("cert_manager", ctx) is True
