#!/usr/bin/env python3
"""Quote mermaid kanban card labels so (…) and em-dashes survive strict
lexers — GitHub's included (task tooling/50 rework). Cards are the
8-space-indented lines of `jear board`; section titles (4-space) parse
unquoted and stay untouched. Reads stdin, writes stdout:

    jear board | python3 examples/quote_mermaid_labels.py
"""
import re
import sys

_CARD = re.compile(r"^(\s{8})(\w+)\[([^\]]+)\]\s*$")

for line in sys.stdin:
    m = _CARD.match(line)
    if m:
        print(f'{m.group(1)}{m.group(2)}["{m.group(3)}"]')
    else:
        sys.stdout.write(line)
