import os
import unittest
from pathlib import Path

from reviewer_mcp import forms
from reviewer_mcp.forms import FormError, parse_form
from reviewer_mcp.validator import explicit_venue_id_from_report, plain_text_problem, validate_report
from reviewer_mcp.venues import load_index

REAL_WORKSPACE = os.environ.get("REVIEWER_WORKSPACE", "")

FORM = """\
# maintainers' comment
Recommendation
  choose: Accept | Minor Revision | Major Revision | Reject
Overall Rating (1-100)
  scale: 1-100
Contribution type
  choose any: Theoretical | Methodological | Evidence used, but could be improved
Question 1: The subject is worthy of investigation
  choose: Disagree | Neutral | Agree
Comments to the Author
  text: 1-3 paragraphs
  help: main issues first
Suggested references
  text: short paragraph
  optional: yes
"""
MATRIX = "\n".join(
    f"| {name} | 3 | Checked. | Validated |"
    for name in ("Novelty", "Technical Soundness", "Evaluation Rigor", "Clarity", "Impact")
)
ANSWERS = """\
Recommendation: Major Revision

Overall Rating (1-100): 55

Contribution type: Methodological, Evidence used, but could be improved

Question 1: The subject is worthy of investigation: Agree

Comments to the Author:
The bound <math><mi>n</mi></math> is loose.

The baselines [12] are weak.
"""


def report(answers=ANSWERS, resolution="Resolved from metadata.", matrix=MATRIX):
    return (
        f"# Review Report\n## Venue Resolution\n{resolution}\n## Extraction Summary & Limitations\nAll pages.\n"
        f"## Paper Quality Matrix\n| Criterion | Score (1-5) | Evidence | Status |\n{matrix}\n"
        f"## Venue Review Form Answers\n{answers}"
    )


class TestFormGrammar(unittest.TestCase):
    def setUp(self):
        self.fields = parse_form(FORM, "test.md")

    def test_fields_and_skeleton(self):
        kinds = [(field.label, field.kind) for field in self.fields]
        self.assertEqual(kinds[0], ("Recommendation", "choose"))
        self.assertEqual(self.fields[1].low, 1)
        self.assertEqual(self.fields[4].max_paragraphs, 3)
        self.assertEqual(self.fields[5].max_paragraphs, 1)
        self.assertTrue(self.fields[5].optional)
        skeleton = forms.skeleton(self.fields)
        self.assertIn("Recommendation: <to fill: one of: Accept | Minor Revision | Major Revision | Reject>", skeleton)
        self.assertIn("Comments to the Author:\n<to fill: 1-3 paragraphs; main issues first>", skeleton)
        self.assertNotIn("maintainers", skeleton)

    def test_grammar_errors_name_the_line(self):
        cases = {
            "Q1 [Yes, No]\n": "needs one of",
            "Q1\n  choose: A | B\n  scale: 1-5\n": "needs one of",
            "Q1\n  choose: Yes\n": "at least two options",
            "Q1\n  text:\n": "needs the size",
            "  choose: A | B\n": "line 1 is not a label",
            "Q1\n  optional: maybe\n  text: short sentence\n": "optional",
            "Q1\n  choose: A | B\n  explain: A\n": "without a 'text' size",
            "Q1\n  choose: A | B\n  text: 1 paragraph\n  explain: C\n": "not one of its options",
            "Q1\n  text: 1 paragraph\n  explain: always\n": "'explain' has nothing to name",
        }
        for text, message in cases.items():
            with self.assertRaises(FormError, msg=text) as ctx:
                parse_form(text, "x.md")
            self.assertIn(message, str(ctx.exception))


EXPLAINED = """Rate the references
  choose: Satisfactory | Unsatisfactory (explain)
  text: 1 paragraph
  explain: Unsatisfactory
"""
EXPLAINED_ALWAYS = """How would you rate the novelty?
  choose: Very Novel | Novel Enough | Not Novel
  text: 1 paragraph
  explain: always
"""
EXPLAINED_OFFERED = """Rate the references
  choose: Satisfactory | Unsatisfactory
  text: 1 paragraph
"""


class TestChoiceWithExplanation(unittest.TestCase):
    """A choice may be followed by an explanation; 'explain' names the options that must carry it."""

    def setUp(self):
        self.field = parse_form(EXPLAINED, "x.md")[0]

    def test_parsed_as_a_choice_that_explains(self):
        self.assertEqual((self.field.kind, self.field.size), ("choose", "1 paragraph"))
        self.assertTrue(self.field.explains)
        # 'explain: Unsatisfactory' names the option printed as 'Unsatisfactory (explain)'
        self.assertEqual(self.field.explain, ("Unsatisfactory (explain)",))
        self.assertTrue(self.field.wants_explanation("Unsatisfactory (explain)"))
        self.assertFalse(self.field.wants_explanation("Satisfactory"))
        self.assertIn("then 1 paragraph explaining Unsatisfactory (explain)", forms.skeleton((self.field,)))

    def test_explain_always_covers_every_option(self):
        field = parse_form(EXPLAINED_ALWAYS, "x.md")[0]
        self.assertEqual(field.explain, ("Very Novel", "Novel Enough", "Not Novel"))
        self.assertIn("then 1 paragraph explaining it", forms.skeleton((field,)))
        self.assertTrue(forms.answer_problems(field, "Not Novel"))
        self.assertEqual(forms.answer_problems(field, "Not Novel. The DSL is prior art."), [])

    def test_without_explain_the_text_is_offered_not_required(self):
        field = parse_form(EXPLAINED_OFFERED, "x.md")[0]
        self.assertEqual(field.explain, ())
        self.assertIn("1 paragraph may follow it", forms.skeleton((field,)))
        self.assertEqual(forms.answer_problems(field, "Unsatisfactory"), [])
        self.assertEqual(forms.answer_problems(field, "Unsatisfactory. Three reviews are missing."), [])
        self.assertTrue(forms.answer_problems(field, "Unsatisfactory. One.\n\nTwo.\n\nThree."))

    def test_answers(self):
        good = [
            "Satisfactory",                                     # no explanation asked for
            "Unsatisfactory. Three 2025 reviews of the same scope are missing.",
            "Unsatisfactory (explain) Three 2025 reviews are missing.",
            "Satisfactory. The coverage is current.",           # an explanation is welcome anyway
        ]
        for answer in good:
            self.assertEqual(forms.answer_problems(self.field, answer), [], answer)
        bad = {
            "Unsatisfactory": "asks for an explanation",
            "Unsatisfactory (explain)": "asks for an explanation",
            "Excellent": "Open the answer",
            "Unsatisfactory. One.\n\nTwo.\n\nThree.": "3 paragraphs",
        }
        for answer, message in bad.items():
            problems = forms.answer_problems(self.field, answer)
            self.assertTrue(problems, answer)
            self.assertIn(message, problems[0])


class TestValidator(unittest.TestCase):
    def setUp(self):
        self.fields = parse_form(FORM, "test.md")

    def errors(self, text, other_labels=frozenset()):
        return validate_report(text, self.fields, other_labels)["errors"]

    def test_explicit_venue_id_from_report(self):
        self.assertEqual(explicit_venue_id_from_report("| **Venue ID** | ieee_t-ase |"), "ieee_t-ase")
        self.assertEqual(explicit_venue_id_from_report("no metadata"), "")

    def test_valid_answers(self):
        self.assertEqual(self.errors(report()), [])

    def test_answers_must_match_their_field(self):
        cases = {
            "Recommendation: Major Revision": ("Recommendation: Maybe", "exactly one of"),
            "Overall Rating (1-100): 55": ("Overall Rating (1-100): 150", "whole number from 1 to 100"),
            "Contribution type: Methodological, Evidence used, but could be improved": (
                "Contribution type: Methodological and Philosophical", "one or more of"),
            "The baselines [12] are weak.": ("Second.\n\nThird.\n\nFourth.", "has 4 paragraphs"),
            "Question 1: The subject is worthy of investigation: Agree": ("", "'Question 1: The subject is worthy"),
        }
        for old, (new, message) in cases.items():
            errors = self.errors(report(ANSWERS.replace(old, new)))
            self.assertTrue(any(message in error for error in errors), (message, errors))

    def test_form_section_holds_only_answers(self):
        copied = "Answer the following questions.\n" + ANSWERS
        self.assertTrue(any("Text outside the form fields" in e for e in self.errors(report(copied))))
        twice = ANSWERS + "\nRecommendation: Reject\n"
        self.assertTrue(any("answered twice" in e for e in self.errors(report(twice))))
        foreign = ANSWERS.replace("Comments to the Author:", "Strong Aspects: none\n\nComments to the Author:")
        self.assertTrue(any("another venue" in e for e in self.errors(report(foreign), frozenset({"Strong Aspects"}))))
        unfilled = ANSWERS.replace(": Agree", ": <to fill: one of: Disagree | Neutral | Agree>")
        self.assertFalse(any("Question 1" in e for e in self.errors(report(unfilled))))

    def test_plain_text_allows_only_text_and_mathml(self):
        plain = [
            "The baselines [12], [15] are weak (p < 0.05); accuracy rose 3.5% at 25 °C, see Table II.",
            "Speed-up of 480×–1740× and R² ≈ 0.93, ∑ over i ≤ n; Reviewer #2 on ieee_access.",
            "It holds: <math><msub><mi>x</mi><mn>2</mn></msub><mo>≤</mo><mn>1</mn></math>.",
            "First paragraph.\n\nSecond paragraph, as in 2021. and 3.5.",
            "At δ=10⁻⁵ the bound ‖g‖₂ ≤ 1 gives ε≈11.6, x′ = σ·x, k → ∞ ⇒ ⌈k/d⌉ and ⟨u, v⟩ ⩽ 1.",
        ]
        for text in plain:
            self.assertEqual(plain_text_problem(text), "", text)
        not_plain = {
            "list item": "Fine.\n- bullet", "bullet sign": "• bullet", "numbered line": "Intro.\n2) Second point.",
            "numbered paragraph": "1. The baselines are weak.", "heading": "## Heading", "bold": "This is **bold**.",
            "italic star": "This is *italic*.", "italic underscore": "This is _italic_.", "emoji": "Good 👍",
            "dingbat": "Checked ✓", "html": "<b>bold</b>", "latex": "Use $x^2$ here.", "code": "code `x`",
            "table": "a | b",
        }
        for rule, text in not_plain.items():
            self.assertNotEqual(plain_text_problem(text), "", rule)
        self.assertIn("👍", plain_text_problem("A long sentence that goes on and on before the emoji 👍 here"))

    def test_plain_text_applies_to_everything_the_agent_writes(self):
        bullets = self.errors(report(resolution="Resolved:\n- from the file name"))
        self.assertTrue(any(e.startswith("Not plain text in Venue Resolution") for e in bullets))
        bold = self.errors(report(ANSWERS.replace("is loose", "is **loose**")))
        self.assertTrue(any("answer to 'Comments to the Author'" in e for e in bold))
        emoji = self.errors(report(matrix=MATRIX.replace("| Impact | 3 | Checked. |", "| Impact | 3 | Checked ✅ |")))
        self.assertTrue(any("Quality Matrix row 'impact'" in e for e in emoji))

    @unittest.skipUnless(REAL_WORKSPACE and (Path(REAL_WORKSPACE) / "forms").is_dir(),
                         "set REVIEWER_WORKSPACE to a workspace with forms/")
    def test_every_real_form_accepts_a_filled_skeleton(self):
        index = load_index(Path(REAL_WORKSPACE) / "forms", Path(REAL_WORKSPACE) / "base_review.md")
        self.assertEqual(index.problems, [])
        example = {"choose": lambda f: f.options[-1], "choose any": lambda f: f.options[0],
                   "scale": lambda f: str(f.high), "text": lambda f: "Plain answer."}
        for venue_id in sorted(index.venues):
            fields = index.form_fields(venue_id)
            answers = "\n\n".join(
                f"{f.label}:\n{example[f.kind](f)}" if f.kind == "text" else f"{f.label}: {example[f.kind](f)}"
                for f in fields
            )
            result = validate_report(report(answers + "\n"), fields, index.other_labels(venue_id))
            self.assertTrue(result["valid"], f"{venue_id}: {result['errors']}")


if __name__ == "__main__":
    unittest.main()
