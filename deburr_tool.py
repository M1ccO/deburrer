#!/usr/bin/env python3
import csv
import os
from datetime import datetime

# -------------------------------------------------------
# CONFIG – where the CSV is
# -------------------------------------------------------
BASE_DIR = r"C:\Users\Omistaja\Desktop\NTX_Deburr"
CSV_NAME = "edge_points.csv"


# -------------------------------------------------------
# CSV loader
# -------------------------------------------------------
def load_points(csv_path):
    points = []
    with open(csv_path, newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            try:
                x, y, z = map(float, row[:3])
            except ValueError:
                # skip header or bad rows
                continue
            points.append((x, y, z))
    return points


# -------------------------------------------------------
# MODEL-SPACE SCALE + OFFSET
# -------------------------------------------------------
def scale_and_offset_model(points, scale=1.0, dx=0.0, dy=0.0, dz=0.0):
    """
    Scales the model symmetrically around its own bounding-box center,
    then applies XYZ offset.
    """

    if not points:
        return []

    # 1) Compute bounding-box center
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]

    cx = (min(xs) + max(xs)) * 0.5
    cy = (min(ys) + max(ys)) * 0.5
    cz = (min(zs) + max(zs)) * 0.5

    centered_scaled = []
    for (x, y, z) in points:
        # 2) scale around center
        x2 = cx + (x - cx) * scale
        y2 = cy + (y - cy) * scale
        z2 = cz + (z - cz) * scale

        # 3) apply offsets
        centered_scaled.append((x2 + dx, y2 + dy, z2 + dz))

    return centered_scaled



# -------------------------------------------------------
# MACHINE-SPACE RADIAL SCALE (Y/Z) – NTX STYLE
# -------------------------------------------------------
def radial_scale_machine_yz(mach_points, scale=1.0, cy=0.0, cz=0.0):
    """
    Scale radius in MACHINE Y/Z plane around center (cy, cz).

    For each (X, Y, Z):
      r    = sqrt((Y-cy)^2 + (Z-cz)^2)
      rnew = r * scale
      Y,Z moved along same angle to rnew
      X (depth) is unchanged.

    This matches mill-turn logic where:
      - X is depth / diameter direction
      - the 'radial' plane for a face/OD deburr is Y/Z
    """
    out = []
    for X, Y, Z in mach_points:
        dy = Y - cy
        dz = Z - cz
        r2 = dy*dy + dz*dz
        if r2 == 0.0:
            # exactly on axis, cannot define direction → leave as is
            out.append((X, Y, Z))
            continue
        r = r2**0.5
        new_r = r * scale
        factor = new_r / r
        Yn = cy + dy * factor
        Zn = cz + dz * factor
        out.append((X, Yn, Zn))
    return out


# -------------------------------------------------------
# Remap + NC generator
# -------------------------------------------------------
def remap_xyz(x, y, z):
    """
    Your requested remapping:
      model x -> machine Z
      model y -> machine Y
      model z -> machine X
    """
    Xm = z
    Ym = y
    Zm = x
    return Xm, Ym, Zm


def generate_nc(points,
                program_number,
                tool_number,
                b_angle,
                feed,
                spindle_speed,
                spindle_dir,
                coolant_on,
                comp_mode,
                clearance,
                radial_scale=1.0,
                spindle_m_code="M303",
                work_offset="G54",
                diameter_mode=True):
    """
    points        : MODEL points (after any model scaling/offset)
    radial_scale  : applied in MACHINE Y/Z after remap, around (Y0,Z0)
    spindle_m_code: M303 (main) or M304 (sub)
    work_offset   : G54 (main) or G57 (sub)
    """
    # Model -> machine axes
    mach_pts = [remap_xyz(*p) for p in points]

    # Radial scaling around spindle axis in Y/Z plane
    if radial_scale != 1.0:
        mach_pts = radial_scale_machine_yz(
            mach_pts, radial_scale, cy=0.0, cz=0.0
        )

    # Actual spindle rotation direction M03/M04
    spindle_m = "M03" if spindle_dir.upper() == "CW" else "M04"

    lines = []
    lines.append(f"O{program_number:04d} (DEBURR PROGRAM)")
    lines.append(
        f"(AUTO-GENERATED {datetime.now().isoformat(timespec='seconds')})"
    )

    # Absolute, selected work offset (G54 main or G57 sub)
    lines.append(f"G90 {work_offset}")

    # Process selection: main / subspindle (M303 / M304)
    lines.append(spindle_m_code)

    # Tool + spindle
    lines.append(f"T{tool_number:02d} M06")
    lines.append(f"S{spindle_speed} {spindle_m}")

    # -------------------------------
    # DMG MORI NTX B-axis activation
    # -------------------------------
    lines.append(f"G361 B{b_angle:.3f} D1")
    lines.append(f"G43 H{tool_number}")

    if coolant_on:
        lines.append("M08")

    # Diameter mode: double X values
    x_mul = 2.0 if diameter_mode else 1.0

    # Origin = center of contour bounding box (matches HTML preview)
    x_center = 0.5 * (min(p[0] for p in mach_pts) + max(p[0] for p in mach_pts))
    y_center = 0.5 * (min(p[1] for p in mach_pts) + max(p[1] for p in mach_pts))
    z_center = 0.5 * (min(p[2] for p in mach_pts) + max(p[2] for p in mach_pts))
    origin = (x_center, y_center, z_center)
    safe_origin = (x_center, y_center, z_center + clearance)

    # 1. Rapid to origin at safe Z
    lines.append(
        f"G00 X{safe_origin[0] * x_mul:.4f} Y{safe_origin[1]:.4f} Z{safe_origin[2]:.4f}"
    )

    # 2. Plunge to origin depth
    lines.append(f"G01 Z{origin[2]:.4f} F{feed:.3f}")

    # 3. Cutter compensation
    if comp_mode in ("G41", "G42"):
        lines.append(comp_mode)

    # 4. Move to first contour point, traverse full contour, return to origin
    for i, (x, y, z) in enumerate(mach_pts):
        if i == 0:
            lines.append(f"G01 X{x * x_mul:.4f} Y{y:.4f} Z{z:.4f} F{feed:.3f}")
        else:
            lines.append(f"G01 X{x * x_mul:.4f} Y{y:.4f} Z{z:.4f}")

    # 5. Close back to origin (same as first point for closed contour)
    lines.append(f"G01 X{origin[0] * x_mul:.4f} Y{origin[1]:.4f} Z{origin[2]:.4f}")

    # 6. Cancel compensation
    if comp_mode in ("G41", "G42"):
        lines.append("G40")

    if coolant_on:
        lines.append("M09")

    lines.append(f"G00 Z{safe_origin[2]:.4f}")
    lines.append("M05")
    lines.append("M30")

    return lines



# -------------------------------------------------------
# MAIN
# -------------------------------------------------------
if __name__ == "__main__":
    csv_path = os.path.join(BASE_DIR, CSV_NAME)

    if not os.path.isfile(csv_path):
        print(f"ERROR: CSV not found:\n  {csv_path}")
        raise SystemExit(1)

    points = load_points(csv_path)
    if not points:
        print(f"ERROR: No valid points found in:\n  {csv_path}")
        raise SystemExit(1)

    print(f"Loaded {len(points)} points from {csv_path}")

    # --- MODEL-SCALE + OFFSET LAYER ---
    print("\n--- Optional MODEL scaling / offset ---")
    try:
        scl = float(input("Global model scale (1.0 = none): ") or "1.0")
        dx  = float(input("Model offset X (mm, 0 = none): ") or "0.0")
        dy  = float(input("Model offset Y (mm, 0 = none): ") or "0.0")
        dz  = float(input("Model offset Z (mm, 0 = none): ") or "0.0")
    except ValueError:
        scl, dx, dy, dz = 1.0, 0.0, 0.0, 0.0

    points = scale_and_offset_model(points, scl, dx, dy, dz)

    # --- G-code parameters ---
    program_number = int(input("\nProgram number: "))
    tool_number    = int(input("Tool number (Tnn): "))
    b_angle        = float(input("B-axis angle: "))
    feed           = float(input("Feedrate: "))
    spindle_speed  = float(input("Spindle speed (RPM): "))
    spindle_dir    = input("Spindle direction (CW/CCW): ").upper()

    coolant_choice = input("Coolant on? (y/n): ").lower()
    coolant_on = coolant_choice == "y"

    comp_choice = input("Cutter comp mode (none/G41/G42): ").upper()
    if comp_choice not in ("G41", "G42"):
        comp_choice = None

    clearance = float(input("Approach clearance (mm): "))

    # --- MACHINE RADIAL SCALE LAYER (Y/Z) ---
    try:
        rs = float(input("Radial scale in machine Y/Z (1.0 = none): ") or "1.0")
    except ValueError:
        rs = 1.0

    # generate program
    nc_lines = generate_nc(points,
                           program_number,
                           tool_number,
                           b_angle,
                           feed,
                           spindle_speed,
                           spindle_dir,
                           coolant_on,
                           comp_choice,
                           clearance,
                           radial_scale=rs)

    out_name = f"O{program_number:04d}_deburr.nc"
    out_path = os.path.join(BASE_DIR, out_name)

    with open(out_path, "w") as f:
        for line in nc_lines:
            f.write(line + "\n")

    print(f"\nSaved NC program:\n  {out_path}")
