from typing import Optional

import carb
import omni.ext
from omni.physx.bindings import _physx as physx_settings


class FluidInCupExtension(omni.ext.IExt):
    """Minimal extension that exposes the FluidCup helper without auto-spawning scenes."""

    def __init__(self) -> None:
        super().__init__()
        self._ext_id: Optional[str] = None
        self._settings = carb.settings.get_settings()

    def on_startup(self, ext_id: str) -> None:
        self._ext_id = ext_id
        carb.log_info(
            f"FluidInCupExtension ({ext_id}) loaded. Instantiate FluidCup() in your own scripts to spawn cups."
        )
        self._ensure_particle_usd_export()

    def on_shutdown(self) -> None:
        carb.log_info("FluidInCupExtension shutting down")
        self._ext_id = None

    def _ensure_particle_usd_export(self) -> None:
        self._settings.set(physx_settings.SETTING_UPDATE_PARTICLES_TO_USD, True)
        self._settings.set(physx_settings.SETTING_UPDATE_VELOCITIES_TO_USD, True)
