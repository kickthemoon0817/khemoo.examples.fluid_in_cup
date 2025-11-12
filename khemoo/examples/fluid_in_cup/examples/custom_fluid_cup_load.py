"""
Small SimulationApp example that enables the `khemoo.examples.fluid_in_cup` extension, runs the simulation for a few
seconds, and logs how much fluid remains inside the mug. Use `FLUID_CUP_DYNAMIC=1` to let the cup fall as a rigid body,
and set `FLUID_CUP_COLOR=r,g,b` (0-1 floats) to tweak the OmniGlass tint.
"""

from isaacsim import SimulationApp

# Initialize the SimulationApp before importing any omni.* modules.
simulation_app = SimulationApp({"headless": False})

import os  # noqa: E402
import sys  # noqa: E402

EXT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if EXT_ROOT not in sys.path:
    sys.path.insert(0, EXT_ROOT)

import carb  # noqa: E402,E401
import omni.kit.app  # noqa: E402,E401
import omni.timeline  # noqa: E402,E401
import omni.usd  # noqa: E402,E401
from omni.physx.scripts import physicsUtils  # noqa: E402,E401
from pxr import Gf, Sdf, UsdGeom, UsdLux  # noqa: E402,E401

from khemoo.examples.fluid_in_cup import FluidCup

EXTENSION_ID = "khemoo.examples.fluid_in_cup"
ASSET_ROOT = "/home/khemoo/Downloads/coco_one_fix_prim.usd"


def _enable_extension():
    app = omni.kit.app.get_app()
    ext_manager = app.get_extension_manager()
    if not ext_manager.is_extension_enabled(EXTENSION_ID):
        carb.log_info(f"[FluidCupExample] Enabling {EXTENSION_ID}")
        ext_manager.set_extension_enabled_immediate(EXTENSION_ID, True)


def _get_stage():
    usd_context = omni.usd.get_context()
    if not usd_context.get_stage():
        usd_context.new_stage()
    return usd_context.get_stage()


def _ensure_world(stage):
    if not stage.GetPrimAtPath("/World"):
        world = UsdGeom.Xform.Define(stage, "/World")
        stage.SetDefaultPrim(world.GetPrim())
    elif not stage.GetDefaultPrim():
        stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))


def _setup_environment(stage):
    _ensure_world(stage)
    if not stage.GetPrimAtPath("/World/GroundPlane"):
        physicsUtils.add_ground_plane(
            stage,
            "/World/GroundPlane",
            "Z",
            4.0,
            Gf.Vec3f(0.0, 0.0, 0.0),
            Gf.Vec3f(0.25, 0.25, 0.25),
        )
    if not stage.GetPrimAtPath("/World/KeyLight"):
        key_light = UsdLux.DistantLight.Define(stage, "/World/KeyLight")
        key_light.CreateIntensityAttr(5000.0)
        key_light.CreateAngleAttr(0.4)
        key_light.AddTranslateOp().Set(Gf.Vec3f(2.0, -3.0, 5.0))
        key_light.AddOrientOp().Set(Gf.Quatf(0.9239, -0.3827, 0.0, 0.0))


def _resolve_asset_path():
    if ASSET_ROOT and ASSET_ROOT != "<fill your asset path>":
        return ASSET_ROOT
    return None


def _print_fluid_status(fluid_cup, frame):
    if not fluid_cup:
        return
    status = fluid_cup.get_fluid_status()
    fraction = status.fraction * 100.0
    print(
        f"[FluidCupExample] frame={frame:04d} "
        f"in_cup={status.particles_in_cup}/{status.initial_particles} ({fraction:.2f}%)"
    )
    carb.log_info(
        f"[FluidCupExample] frame={frame:04d} "
        f"in_cup={status.particles_in_cup}/{status.initial_particles} ({fraction:.2f}%)"
    )


def main():
    _enable_extension()
    asset_path = _resolve_asset_path()

    stage = _get_stage()
    _setup_environment(stage)
    # === Load custom asset with FluidCup ===
    if asset_path:
        cup_prim = stage.GetPrimAtPath("/World/coco_one")
        if not cup_prim.IsValid():
            cup_prim = stage.DefinePrim("/World/coco_one", "Xform")
        carb.log_info(f"[FluidCupExample] Opening stage at {asset_path}")
        payref = Sdf.Reference(asset_path)
        omni.kit.commands.execute(
            "AddReference",
            stage=stage,
            prim_path="/World/coco_one",
            reference=payref,
        )
        if not stage:
            carb.log_error(f"[FluidCupExample] Failed to load stage: {asset_path}")
            return

    fluid_root_path = os.environ.get("FLUID_CUP_ROOT_PATH", "/World/coco_one/fluid_cup")
    fluid_cup = FluidCup(stage, root_prim_path=fluid_root_path, auto_generate=asset_path is None)
    initial_particles = fluid_cup.capture_initial_state()
    if initial_particles == 0:
        carb.log_warn("[FluidCupExample] No fluid particles detected at initialization.")

    timeline = omni.timeline.get_timeline_interface()
    if timeline.is_stopped():
        timeline.play()

    target_frames = 6000
    log_interval = 120

    for frame in range(target_frames):
        simulation_app.update()
        if frame % log_interval == 0:
            _print_fluid_status(fluid_cup, frame)

    timeline.stop()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        carb.log_error(f"[FluidCupExample] Exception during simulation: {e}")
    finally:
        simulation_app.close()
