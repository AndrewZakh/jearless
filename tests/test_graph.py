import pytest

from jearless import graph as graph_mod
from jearless.errors import JearlessError

LINKED = """\
tasks:
  p:
    - id: 1
      summary: first task
    - id: 2
      summary: second task
      depends_on: 1
  other:
    - id: 3
      summary: helper task
      depends_on: [p/1]
"""


def test_render_nodes_and_cross_project_edge(tmp_path):
    (tmp_path / "tasks.yml").write_text(LINKED, encoding="utf-8")
    out = graph_mod.render(tmp_path)
    assert out.startswith("flowchart LR")
    assert 'p_1["p/1: first task"]' in out
    assert 'p_2["p/2: second task"]' in out
    assert "p_2 --> p_1" in out
    assert "other_3 --> p_1" in out


def test_labels_are_sanitized(tmp_path):
    (tmp_path / "tasks.yml").write_text(
        'tasks:\n  p:\n    - id: 1\n      summary: the "quoted" [tricky] label\n',
        encoding="utf-8",
    )
    out = graph_mod.render(tmp_path)
    assert 'p_1["p/1: the quoted tricky label"]' in out  # quotes and brackets stripped


def test_unknown_target_refuses(tmp_path):
    (tmp_path / "tasks.yml").write_text(
        "tasks:\n  p:\n    - id: 1\n      summary: a\n      depends_on: 99\n",
        encoding="utf-8",
    )
    with pytest.raises(JearlessError, match="no such task"):
        graph_mod.render(tmp_path)


def test_cycle_refuses(tmp_path):
    (tmp_path / "tasks.yml").write_text(
        "tasks:\n  p:\n"
        "    - id: 1\n      summary: a\n      depends_on: 2\n"
        "    - id: 2\n      summary: b\n      depends_on: 1\n",
        encoding="utf-8",
    )
    with pytest.raises(JearlessError, match="cycle"):
        graph_mod.render(tmp_path)
