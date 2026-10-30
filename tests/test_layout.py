from screen_translator.layout import TextBox, group_lines, has_japanese

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


def test_has_japanese():
    assert has_japanese("ログ▲") and has_japanese("ｽｷｯﾌﾟ") and has_japanese("1日目")
    assert not has_japanese("ver 1.00") and not has_japanese("HP") and not has_japanese("×")
