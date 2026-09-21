"""Admin snapshot projections. Each module owns one read model."""

from runtime.admin.projections.agents import project_agents
from runtime.admin.projections.pets import project_pets
from runtime.admin.projections.services import project_services
from runtime.admin.projections.speech import project_stt, project_tts

__all__ = [
    "project_agents",
    "project_pets",
    "project_services",
    "project_stt",
    "project_tts",
]
