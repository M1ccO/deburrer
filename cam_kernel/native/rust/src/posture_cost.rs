/// Fast posture-cost batch computation using nalgebra.
///
/// Equivalent to the Python `posture_cost.deviation_cost` multiplied
/// across a batch of axes for parallelism.
///
/// For integration with the Python pipeline via pyo3, or standalone
/// C ABI for C++ callers.
use nalgebra::Vector3;

pub fn angular_deviation(a: &Vector3<f64>, b: &Vector3<f64>) -> f64 {
    let cos_angle = a.dot(b).clamp(-1.0, 1.0);
    cos_angle.acos().to_degrees() * 0.01
}

pub fn posture_cost_batch_nalgebra(
    axes: &[Vector3<f64>],
    preferred: &[Vector3<f64>],
) -> Vec<f64> {
    axes.iter()
        .zip(preferred.iter())
        .map(|(a, p)| angular_deviation(a, p))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_angular_deviation_zero() {
        let a = Vector3::new(1.0, 0.0, 0.0);
        let b = Vector3::new(1.0, 0.0, 0.0);
        assert!((angular_deviation(&a, &b) - 0.0).abs() < 1e-12);
    }

    #[test]
    fn test_angular_deviation_90() {
        let a = Vector3::new(1.0, 0.0, 0.0);
        let b = Vector3::new(0.0, 1.0, 0.0);
        assert!((angular_deviation(&a, &b) - 0.9).abs() < 0.01);
    }
}
