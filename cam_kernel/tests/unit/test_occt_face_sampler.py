from cam_kernel.geometry.occt_session import OcctSession
from cam_kernel.sampling.face_sampler import sample_face_from_shape


def test_selected_occt_face_produces_trimmed_zigzag_rows():
    shape = OcctSession.make_box(10.0, 20.0, 30.0)
    grid = sample_face_from_shape(
        shape,
        face_index=0,
        stepover=3.0,
        sample_spacing=4.0,
        direction="auto",
    )
    assert grid.face_ids == ("face_0",)
    assert grid.row_count >= 2
    assert grid.total_points >= grid.row_count * 2
    assert all(
        abs(sum(value * value for value in sample.normal) - 1.0) < 1.0e-9
        for row in grid.samples
        for sample in row
    )
