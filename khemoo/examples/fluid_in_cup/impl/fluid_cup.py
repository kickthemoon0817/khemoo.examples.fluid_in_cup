import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import carb
from omni.physx.scripts import particleUtils, physicsUtils, utils as physx_utils
from pxr import Gf, PhysxSchema, Sdf, Usd, UsdGeom, UsdPhysics, Vt

from .glass_cup import DEFAULT_GLASS_CUP_CONFIG, create_glass_cup


@dataclass(frozen=True)
class FluidStatus:
    """Simple container returned by FluidCup.get_fluid_status()."""

    particles_in_cup: int
    initial_particles: int
    fraction: float

    def as_dict(self) -> dict:
        return {
            "particles_in_cup": self.particles_in_cup,
            "initial_particles": self.initial_particles,
            "fraction": self.fraction,
        }


class FluidCup:
    """Utility that spawns a mug with a PhysX fluid block and tracks the remaining fluid."""

    def __init__(
        self,
        stage: Usd.Stage,
        *,
        assets_root_url: Optional[str] = None,
        root_prim_path: str = "/World/FluidCup",
        auto_generate: bool = False,
        cup_overrides: Optional[Dict[str, float]] = None,
    ) -> None:
        self._stage = stage
        self._root_prim_path = Sdf.Path(root_prim_path)
        self._cup_prim_path = self._root_prim_path.AppendChild("Cup")
        self._particle_system_path = self._root_prim_path.AppendChild("ParticleSystem")
        self._particle_set_path = self._root_prim_path.AppendChild("Fluid")
        self._particle_material_path = self._root_prim_path.AppendChild("ParticleMaterial")
        self._assets_root_url = assets_root_url
        self._cup_overrides = dict(cup_overrides) if cup_overrides else {}

        # Cup dimensions (meters) aligning with the procedural glass cup
        self._cup_inner_radius = DEFAULT_GLASS_CUP_CONFIG["base_radius"] - DEFAULT_GLASS_CUP_CONFIG["wall_thickness"]
        self._cup_interior_height = DEFAULT_GLASS_CUP_CONFIG["wall_height"]
        self._cup_floor_height = DEFAULT_GLASS_CUP_CONFIG["base_height"]
        self._fluid_max_height = 0.115
        self._fluid_margin = 0.0025
        self._fluid_spawn_offset = 0.0005

        # Particle configuration (Ratios inspired by FluidBallEmitterDemo)
        self._particle_spacing = 0.006
        self._rest_offset = self._particle_spacing * 0.9
        self._solid_rest_offset = self._rest_offset
        self._fluid_rest_offset = self._rest_offset * 0.6
        self._particle_contact_offset = max(self._solid_rest_offset + 0.002, self._fluid_rest_offset / 0.6)
        self._contact_offset = self._rest_offset + 0.002
        self._particle_mass = 0.0005

        self._initial_particle_count = 0
        self._generated = False

        if auto_generate:
            self.generate()

    @property
    def particle_count(self) -> int:
        return self._initial_particle_count

    def generate(self) -> "FluidCup":
        """Create (or recreate) the fluid cup prim hierarchy on the stage."""
        carb.log_info(f"FluidCup: generating cup at {self._root_prim_path}")
        UsdGeom.Xform.Define(self._stage, self._root_prim_path)
        self._spawn_cup()
        self._create_particle_system()
        self._fill_fluid()
        self._generated = True
        return self

    def _spawn_cup(self) -> None:
        cup_path = str(self._cup_prim_path)
        carb.log_info(f"FluidCup: generating procedural glass cup at {cup_path}")
        base_overrides = {
            "enable_rigid_body": True,
            "disable_gravity": False,
            "mass": 0.5,
            "glass_color": (0.9, 0.95, 1.0),
        }
        base_overrides.update(self._cup_overrides)
        create_glass_cup(
            self._stage,
            cup_path,
            position=(0.0, 0.0, 0.0),
            overrides=base_overrides,
        )

    def _create_particle_system(self) -> None:
        particleUtils.add_physx_particle_system(
            self._stage,
            self._particle_system_path,
            contact_offset=self._contact_offset,
            rest_offset=self._rest_offset,
            particle_contact_offset=self._particle_contact_offset,
            solid_rest_offset=self._solid_rest_offset,
            fluid_rest_offset=self._fluid_rest_offset,
            solver_position_iterations=4,
            simulation_owner=None,
            max_neighborhood=96,
        )
        particleUtils.add_physx_particle_smoothing(self._stage, self._particle_system_path, strength=1.0)
        particleUtils.add_physx_particle_anisotropy(self._stage, self._particle_system_path, scale=1.0)
        particleUtils.add_pbd_particle_material(
            self._stage,
            self._particle_material_path,
            cohesion=0.005,
            viscosity=0.01,
            surface_tension=0.001,
            friction=0.1,
            damping=0.05,
        )
        physicsUtils.add_physics_material_to_prim(
            self._stage, self._stage.GetPrimAtPath(self._particle_system_path), self._particle_material_path
        )

    def _fill_fluid(self) -> None:
        positions, velocities = self._generate_cylindrical_particles()
        self._initial_particle_count = len(positions)
        if not positions:
            carb.log_warn("FluidCup: could not generate fluid positions")
            return

        particle_prim = particleUtils.add_physx_particleset_pointinstancer(
            self._stage,
            self._particle_set_path,
            positions,
            velocities,
            self._particle_system_path,
            self_collision=True,
            fluid=True,
            particle_group=0,
            particle_mass=self._particle_mass,
            density=0.0,
            num_prototypes=1,
        )
        self._setup_particle_prototype(particle_prim)

    def _generate_cylindrical_particles(self) -> tuple[List[Gf.Vec3f], List[Gf.Vec3f]]:
        effective_radius = self._cup_inner_radius - self._fluid_margin
        max_height = max(
            0.0, min(self._fluid_max_height, self._cup_interior_height - self._fluid_margin - self._fluid_spawn_offset)
        )
        if max_height <= 0.0:
            return [], []
        height = max_height
        layers = max(1, int(math.floor(height / self._particle_spacing)))
        radial_steps = max(1, int(math.floor(effective_radius / self._particle_spacing)))

        positions: List[Gf.Vec3f] = []
        velocities: List[Gf.Vec3f] = []

        base_z = self._cup_floor_height + self._fluid_margin + self._fluid_spawn_offset

        for layer in range(layers):
            z = base_z + layer * self._particle_spacing
            for ix in range(-radial_steps, radial_steps + 1):
                x = ix * self._particle_spacing
                for iy in range(-radial_steps, radial_steps + 1):
                    y = iy * self._particle_spacing
                    if (x * x + y * y) > (effective_radius * effective_radius):
                        continue
                    positions.append(Gf.Vec3f(x, y, z))
                    velocities.append(Gf.Vec3f(0.0, 0.0, 0.0))
        return positions, velocities

    def _setup_particle_prototype(self, particle_prim: Usd.Prim) -> None:
        if not particle_prim:
            return
        instancer = UsdGeom.PointInstancer(particle_prim)
        if not instancer:
            return

        proto_path = self._particle_set_path.AppendChild("particlePrototype0")
        sphere = UsdGeom.Sphere.Define(self._stage, proto_path)
        sphere.CreateRadiusAttr().Set(self._fluid_rest_offset)
        sphere.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(0.3, 0.5, 0.9)]))
        proto_rel = instancer.GetPrototypesRel()
        if proto_path not in proto_rel.GetTargets():
            proto_rel.AddTarget(proto_path)
        positions = instancer.GetPositionsAttr().Get() or []
        proto_indices = instancer.GetProtoIndicesAttr().Get() or []
        if len(proto_indices) != len(positions):
            instancer.GetProtoIndicesAttr().Set([0] * len(positions))

    def _get_current_particle_positions(self) -> Sequence[Gf.Vec3f]:
        prim = self._stage.GetPrimAtPath(self._particle_set_path)
        if not prim:
            return []

        particle_set = PhysxSchema.PhysxParticleSetAPI(prim)
        sim_points_attr = particle_set.GetSimulationPointsAttr()
        if sim_points_attr and sim_points_attr.HasAuthoredValue():
            points = sim_points_attr.Get()
            if points:
                return points

        instancer = UsdGeom.PointInstancer(prim)
        if instancer:
            points = instancer.GetPositionsAttr().Get()
            if points:
                return points
        points_prim = UsdGeom.Points(prim)
        if points_prim:
            points = points_prim.GetPointsAttr().Get()
            if points:
                return points
        return []

    def _get_world_to_cup_transform(self) -> Optional[Gf.Matrix4d]:
        """Return the matrix that converts world coordinates into the cup's local space."""
        prim = self._stage.GetPrimAtPath(self._cup_prim_path)
        if not prim:
            return None
        xformable = UsdGeom.Xformable(prim)
        if not xformable:
            return None
        cup_to_world = xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        return cup_to_world.GetInverse()

    def _is_inside_cup(self, point: Gf.Vec3f, *, world_to_cup: Optional[Gf.Matrix4d] = None) -> bool:
        local_point = point
        if world_to_cup is not None:
            transformed = world_to_cup.Transform(Gf.Vec3d(point[0], point[1], point[2]))
            local_point = Gf.Vec3f(transformed[0], transformed[1], transformed[2])

        radial_sq = local_point[0] * local_point[0] + local_point[1] * local_point[1]
        radius_limit = (self._cup_inner_radius - self._fluid_margin) ** 2
        height_min = self._cup_floor_height - self._fluid_margin
        height_max = self._cup_floor_height + self._cup_interior_height + self._fluid_margin
        if radial_sq > radius_limit:
            return False
        return height_min <= local_point[2] <= height_max

    def get_fluid_status(self) -> FluidStatus:
        """Return how much fluid is still inside the cup."""
        positions = self._get_current_particle_positions()
        if not positions or not self._initial_particle_count:
            return FluidStatus(0, self._initial_particle_count, 0.0)

        world_to_cup = self._get_world_to_cup_transform()
        inside = sum(1 for pos in positions if self._is_inside_cup(pos, world_to_cup=world_to_cup))
        fraction = inside / self._initial_particle_count if self._initial_particle_count else 0.0
        return FluidStatus(inside, self._initial_particle_count, fraction)

    def get_remaining_fraction(self) -> float:
        """Convenience wrapper returning only the fraction."""
        return self.get_fluid_status().fraction
