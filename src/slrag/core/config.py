import os
from pathlib import Path
from typing import Any, Dict

import yaml


def load_config(config_name: str) -> Dict[str, Any]:
    """Load a YAML configuration file from the config directory.
    
    Args:
        config_name: The name of the config file (e.g., 'controller.yaml')
        
    Returns:
        Dict containing the configuration.
    """
    # Assuming config is always relative to the project root
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    config_path = project_root / "config" / config_name
    
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

# Global instances for lazy loading
_controller_config = None

def get_controller_config() -> Dict[str, Any]:
    """Get the controller configuration, loading it if necessary."""
    global _controller_config
    if _controller_config is None:
        _controller_config = load_config("controller.yaml")
    return _controller_config
