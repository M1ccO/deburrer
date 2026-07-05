/// Joint-space smoothing for B/C axis values using a moving-average filter.
/// Accepts flat (B, C) interleaved arrays and returns smoothed values.
///
/// This is equivalent to the Python `joint_filter.moving_average_smooth`
/// but runs in native code for production toolpaths with 10k+ points.
#[no_mangle]
pub extern "C" fn joint_smoothing_ma(
    b_values: *const f64,
    c_values: *const f64,
    n: usize,
    window: usize,
    b_out: *mut f64,
    c_out: *mut f64,
) {
    if n == 0 || window <= 1 {
        for i in 0..n {
            unsafe {
                *b_out.add(i) = *b_values.add(i);
                *c_out.add(i) = *c_values.add(i);
            }
        }
        return;
    }

    let half = window / 2;
    for i in 0..n {
        let start = if i < half { 0 } else { i - half };
        let end = if i + half + 1 > n { n } else { i + half + 1 };

        let mut b_sum = 0.0;
        let mut c_sum = 0.0;
        let count = (end - start) as f64;

        for j in start..end {
            unsafe {
                b_sum += *b_values.add(j);
                c_sum += *c_values.add(j);
            }
        }

        unsafe {
            *b_out.add(i) = b_sum / count;
            *c_out.add(i) = c_sum / count;
        }
    }
}
