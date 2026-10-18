"""Split kb/help-center.md into one chunk per `## [Axx] Title` article."""
import re
from pathlib import Path

KB_PATH = Path(__file__).resolve().parent.parent / "kb" / "help-center.md"
_HEADING = re.compile(r"^## \[(A\d+)\] (.+)$", re.M)


def load_articles(path: Path = KB_PATH) -> list:
    parts = _HEADING.split(path.read_text())
    return [{"article_id": parts[i], "title": parts[i + 1].strip(), "content": parts[i + 2].strip()}
            for i in range(1, len(parts), 3)]
