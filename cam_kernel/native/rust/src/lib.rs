use nalgebra::Vector3;
use numpy::PyReadonlyArray1;
use pyo3::prelude::*;
use pyo3::wrap_pyfunction;

type Vec3 = [f64; 3];

fn vec3_to_nalgebra(v: &Vec3) -> Vector3<f64> {
    Vector3::new(v[0], v[1], v[2])
}

fn normalize(v: Vec3) -> Vec3 {
    let len = (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]).sqrt();
    if len < 1e-12 {
        return v;
    }
    [v[0] / len, v[1] / len, v[2] / len]
}

fn cross(a: Vec3, b: Vec3) -> Vec3 {
    [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]
}

fn dot(a: Vec3, b: Vec3) -> f64 {
    a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}

#[pyfunction]
fn cross_product(ax: f64, ay: f64, az: f64, bx: f64, by: f64, bz: f64) -> (f64, f64, f64) {
    let result = cross([ax, ay, az], [bx, by, bz]);
    (result[0], result[1], result[2])
}

#[pyfunction]
fn normalize_vector(x: f64, y: f64, z: f64) -> (f64, f64, f64) {
    let result = normalize([x, y, z]);
    (result[0], result[1], result[2])
}

/// Fast posture-cost computation.
/// Accepts flat arrays of floats representing tool axes and computes
/// pairwise angular deviations.
#[pyfunction]
fn posture_cost_batch(
    axes: PyReadonlyArray1<f64>,
    preferred: PyReadonlyArray1<f64>,
) -> Vec<f64> {
    let axes_slice = axes.as_slice().unwrap();
    let pref_slice = preferred.as_slice().unwrap();
    let n = axes_slice.len() / 3;

    let mut costs = Vec::with_capacity(n);
    for i in 0..n {
        let idx = i * 3;
        let a = [axes_slice[idx], axes_slice[idx + 1], axes_slice[idx + 2]];
        let p = [pref_slice[idx], pref_slice[idx + 1], pref_slice[idx + 2]];
        let a_n = normalize(a);
        let p_n = normalize(p);
        let cos_angle = dot(a_n, p_n).clamp(-1.0, 1.0);
        costs.push(cos_angle.acos().to_degrees() * 0.01);
    }
    costs
}

#[pymodule]
fn cam_kernel_native(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(cross_product, m)?)?;
    m.add_function(wrap_pyfunction!(normalize_vector, m)?)?;
    m.add_function(wrap_pyfunction!(posture_cost_batch, m)?)?;
    Ok(())
}
