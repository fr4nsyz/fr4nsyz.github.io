import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build import convert


def page(body):
    return f"<html><body>{body}</body></html>"


class SectionHeadingTest(unittest.TestCase):
    def test_single_quoted_section_becomes_h2(self):
        raw = page("<h3 class='sectionHead'><a id='x1-1000'></a>community</h3>")
        self.assertEqual(convert(raw), "<h2>community</h2>")

    def test_double_quoted_section_becomes_h2(self):
        raw = page('<h3 class="sectionHead"><a \n id="x1-1000"></a>inventory</h3>')
        self.assertEqual(convert(raw), "<h2>inventory</h2>")


class ParagraphClassTest(unittest.TestCase):
    def test_double_quoted_paragraph_class_is_dropped(self):
        raw = page('<p class="noindent" >text</p><p class="indent" >more</p>')
        self.assertEqual(convert(raw), "<p>text</p><p>more</p>")


if __name__ == "__main__":
    unittest.main()
