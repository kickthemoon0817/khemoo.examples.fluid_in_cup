from __future__ import annotations

import math
from typing import Dict, List, Tuple

import carb
import numpy as np
from pxr import Gf, PhysxSchema, Sdf, UsdGeom, UsdPhysics, UsdShade

DEFAULT_GLASS_CUP_CONFIG: Dict[str, float] = {
    "base_radius": 0.06,
    "base_height": 0.01,
    "wall_height": 0.12,
    "wall_thickness": 0.008,
    "segment_count": 32,
    "segment_width": 0.0,
    "visual_segments": 64,
    "enable_rigid_body": True,
    "mass": 0.5,
    "disable_gravity": False,
    "glass_color": (0.88, 0.95, 1.0),
    "glass_ior": 1.45,
    "glass_depth": 0.01,
    "glass_thin_walled": True,
}


def _apply_collider(prim) -> None:
    collision_api = UsdPhysics.CollisionAPI.Apply(prim)
    collision_api.CreateCollisionEnabledAttr(True)
    physx_collision_api = PhysxSchema.PhysxCollisionAPI.Apply(prim)
    physx_collision_api.CreateContactOffsetAttr(0.002)
    physx_collision_api.CreateRestOffsetAttr(0.0)


def _configure_root_physics(root_prim, *, enable_rigid_body: bool, disable_gravity: bool, mass: float) -> None:
    if not enable_rigid_body:
        return
    rigid_api = UsdPhysics.RigidBodyAPI.Apply(root_prim)
    rigid_api.CreateRigidBodyEnabledAttr(True)
    physx_api = PhysxSchema.PhysxRigidBodyAPI.Apply(root_prim)
    physx_api.GetDisableGravityAttr().Set(disable_gravity)
    if mass > 0.0:
        mass_api = UsdPhysics.MassAPI.Apply(root_prim)
        mass_api.CreateMassAttr(mass)


def _make_base(stage, root_path: str, config: Dict[str, float]) -> None:
    base_path = f"{root_path}/Base"
    base = UsdGeom.Cylinder.Define(stage, base_path)
    base.GetRadiusAttr().Set(config["base_radius"])
    base_height = config["base_height"]
    base.GetHeightAttr().Set(base_height)
    xform = UsdGeom.XformCommonAPI(base)
    xform.SetTranslate(Gf.Vec3d(0.0, 0.0, base_height * 0.5))
    _apply_collider(base.GetPrim())


def _make_wall_segments(stage, root_path: str, config: Dict[str, float]) -> None:
    wall_root = UsdGeom.Xform.Define(stage, f"{root_path}/Wall")
    outer_radius = max(config["base_radius"], config["wall_thickness"] + 1e-4)
    ring_radius = max(outer_radius - config["wall_thickness"] * 0.5, 1e-4)
    overlap = config.get("wall_overlap_height", config["particle_spacing"] if "particle_spacing" in config else 0.004)
    overlap = float(min(max(overlap, 0.0), config["base_height"]))
    z_center = config["base_height"] - overlap + config["wall_height"] * 0.5
    wall_height = config["wall_height"] + overlap
    segment_count = max(3, int(config["segment_count"]))
    segment_width = config["segment_width"]
    if segment_width <= 0.0:
        segment_width = 2.0 * ring_radius * math.tan(math.pi / segment_count)
    for idx in range(segment_count):
        angle = 2.0 * math.pi * idx / segment_count
        segment_path = f"{wall_root.GetPath()}/Segment_{idx:02d}"
        cube = UsdGeom.Cube.Define(stage, segment_path)
        cube.CreateSizeAttr(1.0)
        x = ring_radius * math.cos(angle)
        y = ring_radius * math.sin(angle)
        xform = UsdGeom.XformCommonAPI(cube)
        xform.SetScale(Gf.Vec3f(segment_width, config["wall_thickness"], wall_height))
        xform.SetRotate(Gf.Vec3f(0.0, 0.0, math.degrees(angle) - 90.0))
        xform.SetTranslate(Gf.Vec3d(x, y, z_center))
        _apply_collider(cube.GetPrim())


def _ring(radius: float, z: float, segments: int) -> List[Gf.Vec3f]:
    two_pi = 2.0 * math.pi
    return [
        Gf.Vec3f(radius * math.cos(two_pi * i / segments), radius * math.sin(two_pi * i / segments), z)
        for i in range(segments)
    ]


def _add_quad(indices: List[int], counts: List[int], a: int, b: int, c: int, d: int, reverse: bool = False) -> None:
    counts.extend([3, 3])
    if reverse:
        indices.extend([a, c, b, a, d, c])
    else:
        indices.extend([a, b, c, a, c, d])


def _connect_rings(indices: List[int], counts: List[int], start_a: int, start_b: int, segments: int, reverse: bool) -> None:
    for i in range(segments):
        a = start_a + i
        b = start_a + ((i + 1) % segments)
        c = start_b + ((i + 1) % segments)
        d = start_b + i
        _add_quad(indices, counts, a, b, c, d, reverse)


def _build_visual_mesh(stage, root_path: str, config: Dict[str, float]) -> UsdGeom.Mesh:
    mesh_path = f"{root_path}/Visual"
    mesh = UsdGeom.Mesh.Define(stage, mesh_path)

    outer_radius = max(config["base_radius"], 1e-4)
    wall_thickness = min(config["wall_thickness"], outer_radius - 1e-4)
    inner_radius = max(outer_radius - wall_thickness, 1e-4)
    bottom_height = max(config["base_height"], 1e-4)
    total_height = bottom_height + max(config["wall_height"], 1e-4)
    segments = max(16, int(config.get("visual_segments", 64)))

    outer_bottom = _ring(outer_radius, 0.0, segments)
    outer_top = _ring(outer_radius, total_height, segments)
    inner_top = _ring(inner_radius, total_height, segments)
    inner_bottom = _ring(inner_radius, bottom_height, segments)
    bottom_center = Gf.Vec3f(0.0, 0.0, 0.0)
    floor_center = Gf.Vec3f(0.0, 0.0, bottom_height)

    points: List[Gf.Vec3f] = []
    idx_counts: List[int] = []
    face_indices: List[int] = []

    start_outer_bottom = len(points)
    points.extend(outer_bottom)
    start_outer_top = len(points)
    points.extend(outer_top)
    start_inner_top = len(points)
    points.extend(inner_top)
    start_inner_bottom = len(points)
    points.extend(inner_bottom)
    bottom_center_idx = len(points)
    points.append(bottom_center)
    floor_center_idx = len(points)
    points.append(floor_center)

    _connect_rings(face_indices, idx_counts, start_outer_bottom, start_outer_top, segments, reverse=False)
    _connect_rings(face_indices, idx_counts, start_outer_top, start_inner_top, segments, reverse=True)
    _connect_rings(face_indices, idx_counts, start_inner_top, start_inner_bottom, segments, reverse=True)

    for i in range(segments):
        next_i = (i + 1) % segments
        idx_counts.append(3)
        face_indices.extend(
            [
                bottom_center_idx,
                start_outer_bottom + next_i,
                start_outer_bottom + i,
            ]
        )
        idx_counts.append(3)
        face_indices.extend(
            [
                floor_center_idx,
                start_inner_bottom + i,
                start_inner_bottom + next_i,
            ]
        )

    mesh.CreatePointsAttr(points)
    mesh.CreateFaceVertexCountsAttr(idx_counts)
    mesh.CreateFaceVertexIndicesAttr(face_indices)
    mesh.CreateSubdivisionSchemeAttr().Set("none")
    UsdGeom.Gprim(mesh.GetPrim()).CreateDoubleSidedAttr(True)
    return mesh


def _apply_omniglass_material(stage, root_prim, config: Dict[str, float]) -> None:
    if root_prim is None:
        return
    try:
        from isaacsim.core.api.materials.omni_glass import OmniGlass
    except Exception as exc:  # pragma: no cover
        carb.log_warn(f"Could not import OmniGlass material helpers: {exc}")
        return
    root_path = root_prim.GetPath()
    parent_path = root_path.GetParentPath()
    looks_name = f"{root_path.name}Looks"
    looks_scope = UsdGeom.Scope.Define(stage, parent_path.AppendChild(looks_name))
    material_path = f"{looks_scope.GetPath()}/CupOmniGlass"
    glass = OmniGlass(material_path)
    glass_color = config.get("glass_color")
    if isinstance(glass_color, (list, tuple)) and len(glass_color) == 3:
        glass.set_color(np.array(glass_color, dtype=np.float32))
    glass_ior = config.get("glass_ior")
    if isinstance(glass_ior, (float, int)):
        glass.set_ior(float(glass_ior))
    glass_depth = config.get("glass_depth")
    if isinstance(glass_depth, (float, int)):
        glass.set_depth(float(glass_depth))
    glass_thin = config.get("glass_thin_walled")
    if isinstance(glass_thin, bool):
        shader = glass.shaders_list[0]
        shader.CreateInput("thin_walled", Sdf.ValueTypeNames.Bool).Set(glass_thin)
    UsdShade.MaterialBindingAPI(root_prim).Bind(glass.material)


def create_glass_cup(
    stage,
    root_path: str = "/World/GlassCup",
    *,
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    overrides: Dict[str, float] | None = None,
):
    config = dict(DEFAULT_GLASS_CUP_CONFIG)
    if overrides:
        config.update(overrides)

    if stage.GetPrimAtPath(root_path):
        stage.RemovePrim(root_path)
    root = UsdGeom.Xform.Define(stage, root_path)
    root_xform = UsdGeom.Xformable(root)
    root_xform.ClearXformOpOrder()
    root_xform.AddTranslateOp().Set(Gf.Vec3f(*position))
    _configure_root_physics(
        root.GetPrim(),
        enable_rigid_body=bool(config.get("enable_rigid_body", True)),
        disable_gravity=bool(config.get("disable_gravity", False)),
        mass=float(config.get("mass", 0.5)),
    )

    _make_base(stage, root_path, config)
    _make_wall_segments(stage, root_path, config)
    _build_visual_mesh(stage, root_path, config)
    _apply_omniglass_material(stage, root.GetPrim(), config)

    carb.log_info(
        f"Created procedural glass cup at {root_path} "
        f"(radius={config['base_radius']}, wall_height={config['wall_height']}, segments={config['segment_count']})"
    )
    return stage.GetPrimAtPath(root_path)


__all__ = ["DEFAULT_GLASS_CUP_CONFIG", "create_glass_cup"]
