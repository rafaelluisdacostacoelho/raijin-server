"""Gerenciador de configuracoes via arquivo YAML/JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import typer

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


class ConfigManager:
    """Gerencia configuracoes do raijin-server via arquivo."""

    def __init__(self, config_path: str | Path | None = None):
        self.config_path = Path(config_path) if config_path else None
        self.config: Dict[str, Any] = {}
        if self.config_path and self.config_path.exists():
            self.load()

    def load(self) -> None:
        """Carrega configuracoes do arquivo."""
        if not self.config_path or not self.config_path.exists():
            return

        try:
            content = self.config_path.read_text()
            if self.config_path.suffix in [".yaml", ".yml"]:
                if not YAML_AVAILABLE:
                    raise ImportError("PyYAML nao instalado. Instale com: pip install pyyaml")
                self.config = yaml.safe_load(content) or {}
            elif self.config_path.suffix == ".json":
                self.config = json.loads(content)
            else:
                raise ValueError(f"Formato nao suportado: {self.config_path.suffix}")
        except Exception as e:
            typer.secho(f"Erro ao carregar config de {self.config_path}: {e}", fg=typer.colors.RED)
            raise

    def get(self, key: str, default: Any = None) -> Any:
        """Obtem valor de configuracao."""
        keys = key.split(".")
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        return value if value is not None else default

    def get_module_config(self, module: str) -> Dict[str, Any]:
        """Obtem configuracoes especificas de um modulo."""
        return self.config.get("modules", {}).get(module, {})

    def get_global(self, key: str, default: Any = None) -> Any:
        """Obtem configuracao global."""
        return self.config.get("global", {}).get(key, default)

    @classmethod
    def create_template(cls, output_path: str | Path) -> None:
        """Cria template de configuracao."""
        template = {
            "global": {
                "dry_run": False,
                "max_retries": 3,
                "retry_delay": 5,
                "timeout": 300,
                "skip_health_checks": False,
            },
            "modules": {
                "network": {
                    "interface": "ens18",
                    "address": "192.168.0.10/24",
                    "gateway": "192.168.0.1",
                    "dns": "1.1.1.1,8.8.8.8",
                },
                "kubernetes": {
                    "pod_cidr": "10.244.0.0/16",
                    "service_cidr": "10.96.0.0/12",
                    "cluster_name": "raijin",
                    "advertise_address": "0.0.0.0",
                },
                "calico": {
                    "pod_cidr": "10.244.0.0/16",
                },
                "prometheus": {
                    "namespace": "observability",
                    "retention": "15d",
                    "storage": "20Gi",
                },
                "grafana": {
                    "namespace": "observability",
                    "admin_password": "changeme",
                    "ingress_host": "grafana.example.com",
                },
                "traefik": {
                    "namespace": "traefik",
                    "ingress_class": "traefik",
                },
            },
        }

        path = Path(output_path)
        if path.suffix in [".yaml", ".yml"]:
            if not YAML_AVAILABLE:
                typer.secho("PyYAML nao instalado. Salvando como JSON...", fg=typer.colors.YELLOW)
                path = path.with_suffix(".json")
                content = json.dumps(template, indent=2)
            else:
                content = yaml.dump(template, default_flow_style=False, sort_keys=False)
        else:
            content = json.dumps(template, indent=2)

        path.write_text(content)
        typer.secho(f"Template de configuracao criado em: {path}", fg=typer.colors.GREEN)


def prompt_or_config(
    prompt_text: str,
    default: str,
    config_manager: ConfigManager | None,
    config_key: str,
) -> str:
    """Obtem valor de prompt ou config file."""
    if config_manager:
        value = config_manager.get(config_key)
        if value is not None:
            typer.echo(f"{prompt_text} (via config): {value}")
            return str(value)

    return typer.prompt(prompt_text, default=default)
