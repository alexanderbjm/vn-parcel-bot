from pathlib import Path

from vn_parcel_bot.services.module_agent import (
    build_prompt,
    extract_source,
    module_code,
    review,
    target_path,
    unsafe_reason,
)

GOOD = """from vn_parcel_bot.carriers.api import PRIORITY_PREFIXED, CarrierModule, Rule

MODULE = CarrierModule(
    code="jtcargo",
    display_name="J&T Cargo",
    rules=(Rule(r"JTC\\d{12}", PRIORITY_PREFIXED),),
    link_template="https://jtcargo.vn/{code}",
    examples=(("JTC123456789012", True),),
)
"""


def test_the_prompt_carries_the_contract_and_the_request():
    prompt = build_prompt("thêm hãng J&T Cargo, mã JTC + 12 số")
    assert "MODULE = CarrierModule" in prompt
    assert "J&T Cargo" in prompt
    assert "Never set build_client" in prompt, "the agent is told the one hard limit"
    assert "ghtk" in prompt, "a worked example to copy"


def test_source_is_taken_out_of_a_fenced_reply():
    reply = "Here you go:\n\n```python\n" + GOOD + "```\n"
    assert extract_source(reply) == GOOD.strip()


def test_a_bare_reply_still_works_and_chatter_alone_does_not():
    assert extract_source(GOOD) == GOOD.strip()
    assert extract_source("I could not work out the code shape, sorry.") is None


def test_the_module_name_is_read_from_the_source():
    assert module_code(GOOD) == "jtcargo"
    assert module_code("MODULE = CarrierModule(display_name='x')") is None


def test_a_plain_module_is_allowed():
    assert unsafe_reason(GOOD) is None


def test_anything_reaching_outside_the_contract_is_refused():
    for bad, needle in [
        ("import os\n" + GOOD, "import"),
        ("import httpx\n" + GOOD, "import"),
        (GOOD + "\nopen('x')\n", "open("),
        (GOOD + "\nexec('x')\n", "exec("),
        (GOOD.replace("link_template", "build_client"), "build_client"),
    ]:
        reason = unsafe_reason(bad)
        assert reason is not None, bad[:40]
        assert needle in reason


def test_writes_cannot_escape_the_modules_directory(tmp_path):
    assert target_path("jtcargo", tmp_path) == (tmp_path / "jtcargo.py").resolve()
    for bad in ("../evil", "a/b", "", "Jt", "x" * 40, ".hidden"):
        assert target_path(bad, tmp_path) is None, bad


def test_review_accepts_a_good_reply_and_names_the_file():
    outcome = review("```python\n" + GOOD + "```")
    assert outcome.ok is True
    assert outcome.code == "jtcargo"
    assert outcome.source is not None and outcome.source.endswith("\n")


def test_review_explains_why_it_refused():
    assert review("no module here").error == "the reply did not contain a module"
    assert "not allowed" in (review("```python\nimport os\n" + GOOD + "```").error or "")


def test_the_example_in_the_prompt_is_a_module_the_checks_accept():
    """The shape we hand the agent must itself pass every gate."""
    from vn_parcel_bot.services.module_agent import EXAMPLE_MODULE

    outcome = review(EXAMPLE_MODULE)
    assert outcome.ok is True
    assert outcome.code == "ghtk"


def test_target_path_defaults_to_the_real_modules_directory():
    path = target_path("jtcargo")
    assert path is not None
    assert path.parent.name == "modules"
    assert Path(path).suffix == ".py"
