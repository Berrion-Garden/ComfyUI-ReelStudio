

async def test_still_and_image_edit_validate_against_the_yaml(config):
    from reelstudio import generate
    from reelstudio.errors import ValidationError
    from reelstudio.project import load

    project = load(config)
    try:
        generate.plan(project, "still", {"slug": "nope"})
        raise AssertionError("should not queue")
    except ValidationError as e:
        assert "locations:" in str(e)

    try:
        generate.plan(project, "image_edit", {"name": "nope"})
        raise AssertionError("should not queue")
    except ValidationError as e:
        assert "shots:" in str(e)


async def test_still_and_image_edit_run_reel_py(config, monkeypatch):
    from reelstudio import generate, reel as reel_pipeline
    from reelstudio.project import load

    project = load(config)
    calls = []

    def fake_run(ws, cmd, args):
        calls.append((cmd, args))
        return f"BG: {ws}/backgrounds/x_01_.png" if cmd == "bg" \
            else f"SHOT: {ws}/../stills/s_01_.png"

    monkeypatch.setattr(reel_pipeline, "run_sync", fake_run)
    plate = generate.plan(project, "still", {"slug": "campus_sunset"})
    assert generate.GENERATORS and plate
    execute_still = next(g for g in generate.GENERATORS if g.kind == "still")
    out = execute_still.execute(project, None, str(config.yaml_path.parent),
                                "campus_sunset")
    assert out.endswith("x_01_.png") and calls[-1] == ("bg", ["campus_sunset"])

    execute_shot = next(g for g in generate.GENERATORS if g.kind == "image_edit")
    assert execute_shot.execute.__name__ == "_execute_image_edit"
