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
def scale_and_offset_model(points, scale=1.0,
                           dx=0.0, dy=0.0, dz=0.0):
    """
    Global transform in MODEL coordinates:
      (x, y, z) -> (x*scale + dx, y*scale + dy, z*scale + dz)
    """
    out = []
    for x, y, z in points:
        out.append((
            x * scale + dx,
            y * scale + dy,
            z * scale + dz
        ))
    return out


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
                work_offset="G54"):
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

    start = mach_pts[0]

    # Safe approach = Z + clearance
    approach = (start[0], start[1], start[2] + clearance)

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

    # Approach
    lines.append(
        f"G00 X{approach[0]:.4f} Y{approach[1]:.4f} Z{approach[2]:.4f}"
    )
    lines.append(f"G01 Z{start[2]:.4f} F{feed:.3f}")

    # Cutter compensation
    if comp_mode in ("G41", "G42"):
        lines.append(comp_mode)

    # Motion path
    for x, y, z in mach_pts:
        lines.append(f"G01 X{x:.4f} Y{y:.4f} Z{z:.4f} F{feed:.3f}")

    # Cancel compensation
    if comp_mode in ("G41", "G42"):
        lines.append("G40")

    if coolant_on:
        lines.append("M09")

    lines.append(f"G00 Z{approach[2]:.4f}")
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
