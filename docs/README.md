# khemoo.examples.fluid_in_cup

This extension recreates the core ideas from `FluidBallEmitterDemo.py` and spawns a simple scene that
uses a fully procedural glass cup authored in USD. The cup geometry provides:

- GPU-friendly analytic colliders (tiling boxes + floor) so fluids interact reliably without relying on mesh collisions.
- A watertight visual mesh bound to `OmniGlass`, so the container renders like real glass without shipping an external asset.
- Configurable rigid-body behavior (static by default, but you can turn it into a dynamic body for interactive scenes).

## Using the extension

1. Enable the extension (e.g. by adding `--enable khemoo.examples.fluid_in_cup` to your Kit command line or through the
   Extension Manager UI). This automatically registers the procedural cup builder.
2. From your own script or kit extension, instantiate `FluidCup` at any stage path and call `.generate()`. The helper
   will emit the glass cup, build the fluid particle system, and initialize the point instancer.
3. Query the remaining fluid volume via the built-in helpers:

```python
import omni.usd
from khemoo.examples.fluid_in_cup import FluidCup

stage = omni.usd.get_context().get_stage()
cup = FluidCup(stage, root_prim_path="/World/CustomCup").generate()
status = cup.get_fluid_status()
print(status.as_dict())
print(cup.get_remaining_fraction())
```

Make sure the `khemoo.examples.fluid_in_cup` extension is enabled before importing `FluidCup`, and create any required
scene context (default prim, physics scene, ground, lighting) beforehand. The class tracks how many PhysX particles
remain inside the cup walls and exposes the data through `get_fluid_status()` and `get_remaining_fraction()`.

> FluidCup does not add lights, ground planes, or physics scenes; set these up before calling `generate()`.

### SimulationApp example

To drive this extension from a standalone Python process, run
`python extsUser/khemoo.examples.fluid_in_cup/khemoo/examples/fluid_in_cup/examples/fluid_cup_simulation_app.py`. The
script bootstraps `SimulationApp`, ensures the extension is enabled, and prints the remaining fluid percentage while the
simulation runs for a short session.

## Procedural cup configuration

The procedural cup is authored directly on the USD stage. You can customize its geometry, material, and physics behavior
by editing the `DEFAULT_GLASS_CUP_CONFIG` dictionary (or passing overrides to `create_glass_cup()`):

| Key | Description | Default |
| --- | --- | --- |
| `base_radius` | Outer radius of the bottom cylinder (meters) | `0.06` |
| `wall_thickness` | Wall thickness for collider panels | `0.008` |
| `base_height` / `wall_height` | Bottom thickness and wall height | `0.01` / `0.12` |
| `segment_count` | Number of cube panels forming the wall collider | `32` |
| `visual_segments` | Tessellation of the visual mesh | `64` |
| `enable_rigid_body` | Whether the root Xform becomes a PhysX rigid body | `True` |
| `mass` | Mass (kg) assigned when rigid body is enabled | `0.5` |
| `glass_color`, `glass_ior`, `glass_depth`, `glass_thin_walled` | OmniGlass shading controls | see config |

When FluidCup instantiates the cup, it disables the rigid body (static container) and gravity so the cup remains fixed.
If you want the cup to fall or interact with other rigid bodies, set `enable_rigid_body=True` and `disable_gravity=False`
when calling `create_glass_cup()`.
