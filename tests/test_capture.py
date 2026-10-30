from screen_translator.capture import Monitor, Region

# Màn hình phụ đặt bên phải màn hình chính 1920 px, độ phân giải 2560×1440, scale 125%
MONITOR = Monitor(1920, 0, 2560, 1440)
ORIGIN = (1536, 0)  # 1920 / 1.25


def test_selection_is_converted_to_physical_pixels():
    region = Region.from_selection(MONITOR, ORIGIN, 1.25, 100, 200, 400, 80)
    assert (region.left, region.top, region.width, region.height) == (2045, 250, 500, 100)
    assert region.crop_box() == (125, 250, 625, 350)


def test_round_trip_back_to_logical():
    region = Region.from_selection(MONITOR, ORIGIN, 1.25, 100, 200, 400, 80)
    assert region.to_logical() == (1636, 200, 400, 80)


def test_selection_is_clamped_to_the_monitor():
    region = Region.from_selection(MONITOR, ORIGIN, 1.25, 1900, 1100, 300, 300)
    assert region.left + region.width == MONITOR.left + MONITOR.width
    assert region.top + region.height == MONITOR.height
    *_, right, bottom = region.crop_box()
    assert right <= MONITOR.width and bottom <= MONITOR.height


def test_window_partly_off_the_monitor_is_clipped():
    region = Region.from_physical(MONITOR, ORIGIN, 1.25, 1800, -30, 3000, 900)
    assert (region.left, region.top, region.width, region.height) == (1920, 0, 1080, 900)


def test_sub_region_maps_a_text_line_to_logical_coordinates():
    window = Region.from_physical(MONITOR, ORIGIN, 1.25, 2000, 100, 3920, 1120)
    line = window.sub(410, 810, 1285, 846)  # khung một dòng chữ trong ảnh chụp cửa sổ
    assert (line.left, line.top, line.width, line.height) == (2410, 910, 875, 36)
    assert line.to_logical() == (1536 + 392, 728, 700, 29)


def test_no_scaling():
    region = Region.from_selection(Monitor(0, 0, 1920, 1080), (0, 0), 1.0, 10, 20, 30, 40)
    assert (region.left, region.top, region.width, region.height) == (10, 20, 30, 40)
    assert region.to_logical() == (10, 20, 30, 40)
