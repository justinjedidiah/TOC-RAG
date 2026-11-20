from toc_app.pacing import MIN_CHARS, TextPacer


def shown_ticks(pacer: TextPacer) -> list[str]:
    out = []
    while (text := pacer.tick()) is not None:
        out.append(text)
    return out


def test_text_comes_out_in_whole_words_and_ends_complete():
    pacer = TextPacer()
    pacer.set_target("Equipment grew fastest, by 15.0 percent, from 98.3 to 113.0 million dollars.")
    steps = shown_ticks(pacer)
    assert len(steps) > 3  # spread over several ticks, not all at once
    assert steps[-1] == pacer.target
    for text in steps[:-1]:
        assert text.endswith(" "), text  # never stops in the middle of a word
    assert all(b.startswith(a) for a, b in zip(steps, steps[1:]))  # only ever grows


def test_a_big_burst_is_caught_up_quickly_and_a_trickle_is_shown_at_once():
    pacer = TextPacer()
    pacer.set_target("word " * 400)  # 2,000 characters arrive in one burst
    assert len(shown_ticks(pacer)) < 40  # under two seconds at 20 ticks a second

    pacer.set_target(pacer.target + "and ")  # then a few characters trickle in
    assert pacer.tick() == pacer.target
    assert pacer.tick() is None


def test_the_slowest_pace_still_moves():
    pacer = TextPacer()
    pacer.set_target("abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz")  # no spaces to round up to
    first = pacer.tick()
    assert first is not None and len(first) >= MIN_CHARS


def test_a_changed_beginning_keeps_only_what_still_matches_and_reset_starts_over():
    pacer = TextPacer()
    pacer.set_target("The answer is here and more")
    shown_ticks(pacer)
    pacer.set_target("The answer was here")  # an earlier part changed
    assert pacer.text() == "The answer "
    assert shown_ticks(pacer)[-1] == "The answer was here"
    pacer.reset()
    assert pacer.text() == "" and pacer.tick() is None
