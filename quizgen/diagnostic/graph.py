"""Turn a concept map into Graphviz DOT for st.graphviz_chart."""

from __future__ import annotations

import textwrap
from typing import Optional

from .schemas import ConceptMap


def _q(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _wrap(text: str, width: int = 22) -> str:
    return "\\n".join(textwrap.wrap(_q(text), width)) or _q(text)


def to_dot(cmap: ConceptMap, show_misconceptions: bool = True,
           highlight: Optional[set[str]] = None) -> str:
    """Arrows point from prerequisite to the concept that builds on it.

    `highlight` = concept ids that have at least one question (drawn solid);
    the rest are drawn dashed so coverage gaps jump out.
    """
    lines = [
        "digraph G {",
        # Left-to-right when misconceptions are shown keeps the many notes from
        # stretching the graph into one unreadable row.
        f'  rankdir={"LR" if show_misconceptions else "TB"}; bgcolor="transparent"; nodesep=0.3; ranksep=0.6;',
        '  node [fontname="Helvetica", fontsize=11, style="rounded,filled", shape=box, '
        'color="#3b6ea5", fillcolor="#e8f0fa", fontcolor="#1a1a1a"];',
        '  edge [color="#7a8a9a", arrowsize=0.7];',
    ]
    for c in cmap.concepts:
        style = "rounded,filled"
        if highlight is not None and c.id not in highlight:
            style = "rounded,filled,dashed"
        lines.append(f'  "{c.id}" [label="{_wrap(c.name)}", style="{style}", tooltip="{_q(c.description)}"];')
        if show_misconceptions:
            for m in c.misconceptions:
                lines.append(
                    f'  "{m.id}" [label="{_wrap(m.description, 26)}", shape=note, fontsize=9, '
                    f'color="#b5651d", fillcolor="#fdf1e6"];'
                )
                lines.append(f'  "{c.id}" -> "{m.id}" [style=dotted, color="#b5651d", arrowhead=none];')
    for c in cmap.concepts:
        for p in c.prerequisites:
            if cmap.concept(p):
                lines.append(f'  "{p}" -> "{c.id}";')
    lines.append("}")
    return "\n".join(lines)
