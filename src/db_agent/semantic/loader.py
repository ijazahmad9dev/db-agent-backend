import os
import yaml

from db_agent.core.config import get_settings
from db_agent.semantic.models import SemanticLayer

settings = get_settings()


def _path_for(connection_id: str) -> str:
    os.makedirs(settings.semantic_mappings_dir, exist_ok=True)
    return os.path.join(settings.semantic_mappings_dir, f"{connection_id}.yaml")


def save_semantic_layer(layer: SemanticLayer) -> None:
    with open(_path_for(layer.connection_id), "w") as f:
        yaml.safe_dump(layer.model_dump(), f, sort_keys=False)


def load_semantic_layer(connection_id: str) -> SemanticLayer | None:
    path = _path_for(connection_id)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = yaml.safe_load(f)
    return SemanticLayer.model_validate(data)