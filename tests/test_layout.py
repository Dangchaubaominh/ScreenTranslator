from screen_translator.layout import TextBox, group_lines, has_japanese, similar

# Các dòng OneOCR đọc được trên ảnh chụp game thật (4.webp, 1.png), giữ nguyên tọa độ


def test_wrapped_sentence_is_joined_into_one_block():
    lines = [
        TextBox("ここには誰もいない。", 1575, 99, 1783, 121),
        TextBox("見取り図で人のいる部屋へ移動すると話", 1574, 120, 1901, 144),
        TextBox("せる", 1579, 145, 1612, 164),
    ]
    assert group_lines(lines) == [
        TextBox("ここには誰もいない。見取り図で人のいる部屋へ移動すると話せる", 1574, 99, 1901, 164)
    ]


def test_short_labels_stay_separate():
    lines = [
        TextBox("台所", 23, 365, 57, 384),
        TextBox("タクミ咲夜", 25, 382, 128, 403),
        TextBox("ニューゲーム", 144, 583, 303, 608),
        TextBox("ギャラリー", 142, 642, 277, 669),
    ]
    assert [b.text for b in group_lines(lines)] == ["台所", "タクミ咲夜", "ニューゲーム", "ギャラリー"]


def test_separate_rows_of_a_table_stay_separate():
    lines = [
        TextBox("戦闘で相手に与える経験値と成長。戦闘で上がり、周回で持ち越す", 737, 407, 1295, 429),
        TextBox("サイズに応じて戦闘時の報酬にボーナス", 738, 446, 1444, 469),
    ]
    assert len(group_lines(lines)) == 2


def test_lines_side_by_side_stay_separate():
    lines = [TextBox("1日目 早朝 行動力", 398, 66, 579, 88), TextBox("現在地:Scottの部屋(密室)", 718, 65, 1004, 89)]
    assert len(group_lines(lines)) == 2


def test_latin_words_keep_their_space():
    lines = [TextBox("Press the Enter key to go", 0, 0, 400, 20), TextBox("on to the next page", 0, 24, 300, 44)]
    assert group_lines(lines)[0].text == "Press the Enter key to go on to the next page"


# Các cột chữ dọc OneOCR đọc được trên trang manga dựng sẵn (chữ ~20 px), giữ nguyên tọa độ


def test_columns_of_a_speech_bubble_are_read_right_to_left():
    lines = [
        TextBox("ですか", 1113, 127, 1136, 199),  # cột ngắn canh trên
        TextBox("無理があるんじゃない", 1139, 127, 1163, 332),
        TextBox("先生、それはちょっと", 1166, 125, 1191, 335),
        TextBox("黙って聞け", 763, 145, 788, 254),
        TextBox("うるさい!", 792, 147, 813, 258),
    ]
    assert group_lines(lines) == [
        TextBox("先生、それはちょっと無理があるんじゃないですか", 1113, 125, 1191, 335),
        TextBox("うるさい!黙って聞け", 763, 145, 813, 258),
    ]


def test_bubbles_next_to_each_other_stay_separate():
    lines = [
        TextBox("えっ…", 1167, 772, 1191, 846),
        TextBox("本当に?", 1140, 767, 1164, 862),
        TextBox("かしこまりました", 1093, 760, 1118, 920),  # bóng bên trái: cách xa hơn khoảng giữa hai cột
        TextBox("お茶とお菓子な", 1140, 900, 1164, 1060),  # bóng bên dưới: không ngang hàng
    ]
    assert [b.text for b in group_lines(lines)] == ["えっ…本当に?", "お茶とお菓子な", "かしこまりました"]


def test_horizontal_lines_and_vertical_columns_on_one_page():
    lines = [TextBox("かしこまりました", 799, 468, 825, 630), TextBox("第3話 霊夢の休日", 700, 60, 1000, 84)]
    assert [b.text for b in group_lines(lines)] == ["第3話 霊夢の休日", "かしこまりました"]
    # một ký tự: không biết là cột hay dòng, nên không nối vào cột bên cạnh
    assert len(group_lines([TextBox("はい", 14, 0, 24, 30), TextBox("!", 0, 0, 10, 30)])) == 2


def test_has_japanese():
    assert has_japanese("ログ▲") and has_japanese("ｽｷｯﾌﾟ") and has_japanese("1日目")
    assert not has_japanese("ver 1.00") and not has_japanese("HP") and not has_japanese("×")


def test_similar_tolerates_ocr_slips_but_not_a_different_line():
    line = "枕元に何かが転がっていた。"
    assert similar(line, "枕元に何かが転がつていた。")  # っ đọc thành つ
    assert similar(line, "枕元に何かが転がっていた")  # sót dấu chấm
    assert not similar(line, "枕元に何かが転がつていた")  # 13 ký tự: chỉ được lệch 1
    assert not similar("うん", "ううん") and not similar("行きます", "行きません")  # câu ngắn phải khớp hẳn
    assert similar("", "") and not similar("", "はい")
