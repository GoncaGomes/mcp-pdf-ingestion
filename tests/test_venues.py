import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pymupdf as fitz

from reviewer_mcp.forms import FormError, compose_guideline, parse_venue_form, read_fields
from reviewer_mcp.profile import build_profile
from reviewer_mcp.store import close_all
from reviewer_mcp.venues import load_index

REAL_WORKSPACE = os.environ.get("REVIEWER_WORKSPACE", "")

BASE = "# Review academic paper\n\n## Context\n\n{{JOURNAL_CONTEXT}}\n"
FORM = "Recommendation\n  choose: Accept | Reject"


def write_form(cdir: Path, venue_id: str, form: str = FORM, extra: str = "", **fields) -> Path:
    lines = ["VENUE:"]
    for key, value in fields.items():
        lines.append(f"{key}: {' | '.join(value) if isinstance(value, list) else value}")
    if extra:
        lines.append(f"CONTEXT: {extra}")
    path = cdir / f"{venue_id}.md"
    path.write_text("\n".join(lines) + "\n---\nFORM:\n" + form + "\n", encoding="utf-8")
    return path


def profile(stem="submission", stamps=(), dois=()):
    return {
        "file": {"stem": stem},
        "stamps": [{"text": text, "source": source, "pages": [1]} for source, text in stamps],
        "dois": [{"doi": doi, "source": "footer"} for doi in dois],
    }


def make_pdf(path: Path, header: str = "", body: str = "", footer: str = "") -> None:
    doc = fitz.open()
    page = doc.new_page()
    if header:
        page.insert_text((50, 30), header, fontsize=9)
    if body:
        page.insert_text((50, 300), body, fontsize=11)
    if footer:
        page.insert_text((50, 820), footer, fontsize=9)
    doc.save(str(path))
    doc.close()


class TestForms(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cdir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_and_compose(self):
        path = write_form(self.cdir, "ieee_t-ase", name="IEEE Transactions on Automation Science and Engineering",
                               kind="journal", acronym="T-ASE", publisher="IEEE", aliases=["IEEE TASE"],
                               identifiers=["T-ASE-#-#"], doi=["10.1109/TASE"])
        venue_form = parse_venue_form(path)
        self.assertEqual(venue_form.venue_id, "ieee_t-ase")
        self.assertEqual(venue_form.identifiers, ("T-ASE-#-#",))
        guideline = compose_guideline(BASE, venue_form)
        self.assertIn(
            "Review the academic paper in attachment, submitted to the journal "
            "IEEE Transactions on Automation Science and Engineering (T-ASE).",
            guideline,
        )
        self.assertNotIn("Recommendation", guideline)
        (field,) = read_fields(venue_form)
        self.assertEqual((field.label, field.kind, field.options), ("Recommendation", "choose", ("Accept", "Reject")))
        self.assertNotIn("{{", guideline)

    def test_composition_reads_the_venue_form_when_requested(self):
        path = write_form(self.cdir, "x_venue", name="X", kind="journal")
        venue_form = parse_venue_form(path)
        changed = path.read_text(encoding="utf-8").replace(FORM, "Decision\n  choose: Yes | No")
        path.write_text(changed, encoding="utf-8")
        self.assertEqual([field.label for field in read_fields(venue_form)], ["Decision"])

    def test_context_sentence_by_kind(self):
        publisher = parse_venue_form(write_form(self.cdir, "springer_nature", name="Springer Nature",
                                                    kind="publisher"))
        self.assertIn("shared by all Springer Nature journals", compose_guideline(BASE, publisher))
        platform = parse_venue_form(write_form(self.cdir, "insticc", name="PRIMORIS", kind="platform",
                                                   publisher="INSTICC", extra="Reviews are for workshops."))
        guideline = compose_guideline(BASE, platform)
        self.assertIn("on the PRIMORIS platform (operated by INSTICC)", guideline)
        self.assertIn("name from the manuscript.\n\nReviews are for workshops.", guideline)

    def test_invalid_forms_fail_loudly(self):
        cases = {
            "old_style": ("CONTEXT: old\n---\nFORM:\nQ1\n", "no 'VENUE:' block"),
            "bad_kind": ("VENUE:\nname: X\nkind: conference\n---\nFORM:\nQ1\n", "kind must be one of"),
            "bad_ident": (
                "VENUE:\nname: X\nkind: journal\nidentifiers: X-2026\n---\nFORM:\nQ1\n",
                "identifier 'X-2026'",
            ),
            "bad_key": ("VENUE:\nname: X\nkind: journal\ncolour: red\n---\nFORM:\nQ1\n", "unknown VENUE key 'colour'"),
            "twice": ("VENUE:\nname: X\nname: Y\nkind: journal\n---\nFORM:\nQ1\n", "given twice"),
            "no_name": ("VENUE:\nkind: platform\n---\nFORM:\nQ1\n", "missing 'name'"),
            "bad_doi": ("VENUE:\nname: X\nkind: journal\ndoi: 11.1/x\n---\nFORM:\nQ1\n", "DOI prefix"),
            "no_form": ("VENUE:\nname: X\nkind: journal\n---\nFORM:\n\n", "FORM section is empty"),
            "free_text_form": ("VENUE:\nname: X\nkind: journal\n---\nFORM:\nQ1 [Yes, No]\n", "needs one of"),
            "bad_key_form": ("VENUE:\nname: X\nkind: journal\n---\nFORM:\nQ1\n  pick: A | B\n", "not a label"),
            "bad_scale": ("VENUE:\nname: X\nkind: journal\n---\nFORM:\nQ1\n  scale: 5-1\n", "scale: low-high"),
            "twice_form": ("VENUE:\nname: X\nkind: journal\n---\nFORM:\nQ1\n  text: short sentence\n"
                           "Q1\n  text: short sentence\n", "defined twice"),
        }
        for venue_id, (content, message) in cases.items():
            path = self.cdir / f"{venue_id}.md"
            path.write_text(content, encoding="utf-8")
            with self.assertRaises(FormError, msg=venue_id) as ctx:
                parse_venue_form(path)
            self.assertIn(message, str(ctx.exception))

    def test_file_name_must_be_a_venue_id(self):
        path = self.cdir / "Bad Name.md"
        path.write_text("VENUE:\nname: X\nkind: journal\n---\nFORM:\nQ1\n", encoding="utf-8")
        with self.assertRaises(FormError):
            parse_venue_form(path)

    def test_compose_rejects_leftover_placeholders(self):
        venue_form = parse_venue_form(write_form(self.cdir, "x_venue", name="X", kind="journal"))
        with self.assertRaises(FormError):
            compose_guideline("{{JOURNAL_CONTEXT}} {{OTHER}}", venue_form)


class TestVenueIndex(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        # profiles are read from paper stores: keep them inside the temporary directory
        scratch = mock.patch.dict(os.environ, {"REVIEWER_SCRATCH_BASE": str(self.root / "scratch")})
        scratch.start()
        self.addCleanup(scratch.stop)
        self.addCleanup(close_all)
        self.cdir = self.root / "forms"
        self.cdir.mkdir()
        self.base = self.root / "base_review.md"
        self.base.write_text(BASE, encoding="utf-8")
        write_form(self.cdir, "ieee_access", name="IEEE Access", kind="journal", publisher="IEEE",
                        identifiers=["Access-#-#"], doi=["10.1109/ACCESS"])
        write_form(self.cdir, "ieee_tvt", name="IEEE Transactions on Vehicular Technology", kind="journal",
                        acronym="TVT", identifiers=["VT-#-#"], doi=["10.1109/TVT"])
        write_form(self.cdir, "elsevier_jii", name="Journal of Industrial Information Integration",
                        kind="journal", acronym="JII", identifiers=["JII-D-#-#"])
        write_form(self.cdir, "sparcly", name="Sparcly", kind="platform")
        write_form(self.cdir, "springer_nature", name="Springer Nature", kind="publisher",
                        aliases=["Springer"], doi=["10.1007"])
        self.index = load_index(self.cdir, self.base)

    def tearDown(self):
        self.tmp.cleanup()

    def test_loads_forms_and_composes_guidelines(self):
        self.assertEqual(
            sorted(self.index.venues), ["elsevier_jii", "ieee_access", "ieee_tvt", "sparcly", "springer_nature"]
        )
        self.assertEqual(self.index.problems, [])
        guideline = self.index.guideline("ieee_access")
        self.assertTrue(guideline.startswith("# Review academic paper"))
        self.assertIn("submitted to the journal IEEE Access.", guideline)
        self.assertEqual([f.label for f in self.index.form_fields("ieee_access")], ["Recommendation"])

    def test_reloads_when_sources_change(self):
        write_form(self.cdir, "mdpi", name="MDPI", kind="publisher", doi=["10.3390"])
        self.assertIn("mdpi", load_index(self.cdir, self.base).venues)
        self.base.write_text("# Changed template\n" + BASE, encoding="utf-8")
        self.assertTrue(load_index(self.cdir, self.base).guideline("ieee_access").startswith("# Changed template"))

    def test_reports_invalid_forms_and_collisions(self):
        (self.cdir / "legacy.md").write_text("CONTEXT: old style\n---\nFORM:\nQ1\n", encoding="utf-8")
        write_form(self.cdir, "ieee_tvt2", name="IEEE Transactions on Vehicular Technology", kind="journal")
        index = load_index(self.cdir, self.base)
        problems = " ".join(index.problems)
        self.assertIn("legacy.md: no 'VENUE:' block", problems)
        self.assertIn("claimed by ['ieee_tvt', 'ieee_tvt2']", problems)
        self.assertNotIn("legacy", index.venues)
        self.assertEqual(index.resolve(profile(), explicit="legacy")["status"], "unresolved")

    def test_missing_base_template(self):
        index = load_index(self.cdir, self.root / "missing.md")
        self.assertIn("Base review template not found", " ".join(index.problems))
        self.assertEqual(index.resolve(profile(stem="VT-2026-1"))["venue_id"], "ieee_tvt")
        with self.assertRaises(FileNotFoundError):
            index.guideline("ieee_tvt")

    def test_file_name_manuscript_id(self):
        r = self.index.resolve(profile(stem="VT-2026-05173_Proof_hi"))
        self.assertEqual((r["status"], r["venue_id"], r["confidence"]), ("resolved", "ieee_tvt", "high"))

    def test_file_name_acronym(self):
        r = self.index.resolve(profile(stem="TVT-2026-0001"))
        self.assertEqual((r["status"], r["venue_id"]), ("resolved", "ieee_tvt"))

    def test_cover_manuscript_number(self):
        r = self.index.resolve(profile(stamps=[("cover", "Manuscript Number: JII-D-26-00489R2")]))
        self.assertEqual((r["status"], r["venue_id"]), ("resolved", "elsevier_jii"))

    def test_header_names_journal(self):
        r = self.index.resolve(profile(stamps=[("header", "For consideration in IEEE Access Page 2 of 17")]))
        self.assertEqual((r["status"], r["venue_id"]), ("resolved", "ieee_access"))

    def test_platform_takes_precedence_over_journal_template(self):
        r = self.index.resolve(profile(stamps=[("header", "IEEE Transactions on Vehicular Technology"),
                                               ("footer", "Submitted via Sparcly")]))
        self.assertEqual((r["status"], r["venue_id"], r["kind"]), ("resolved", "sparcly", "platform"))
        self.assertTrue(r["conflicts"])

    def test_doi_longest_prefix(self):
        self.assertEqual(self.index.resolve(profile(dois=["10.1109/ACCESS.2024.0429000"]))["venue_id"], "ieee_access")
        self.assertEqual(self.index.resolve(profile(dois=["10.1007/s10479-024-1"]))["venue_id"], "springer_nature")

    def test_two_journals_are_ambiguous(self):
        r = self.index.resolve(profile(stamps=[("header", "IEEE Access"),
                                               ("footer", "Journal of Industrial Information Integration")]))
        self.assertEqual(r["status"], "ambiguous")
        self.assertEqual([c["venue_id"] for c in r["candidates"]], ["elsevier_jii", "ieee_access"])

    def test_acronym_in_stamp_is_medium(self):
        r = self.index.resolve(profile(stamps=[("header", "TVT special issue")]))
        self.assertEqual((r["status"], r["venue_id"], r["confidence"]), ("resolved", "ieee_tvt", "medium"))

    def test_nothing_matches(self):
        self.assertEqual(self.index.resolve(profile(stem="paper"))["status"], "unresolved")

    def test_explicit_venue(self):
        r = self.index.resolve(profile(stem="VT-2026-1"), explicit="ieee_access")
        self.assertEqual((r["status"], r["venue_id"], r["confidence"]), ("resolved", "ieee_access", "explicit"))
        self.assertTrue(r["conflicts"])
        self.assertEqual(self.index.resolve(None, explicit="x" * 5000)["status"], "unresolved")
        self.assertEqual(self.index.resolve(None, explicit="../../etc/passwd")["status"], "unresolved")

    def test_body_text_never_selects_a_venue(self):
        pdf = self.root / "paper.pdf"
        make_pdf(pdf, body="Multiple access algorithms, statistical tests, Springer Nature, IEEE Access, Sparcly\n"
                           "Submitted to IEEE Transactions on Vehicular Technology last year\n"
                           "Journal of Industrial Information Integration papers\n"
                           "Conference Sparcly workflows")
        self.assertEqual(self.index.resolve(build_profile(pdf))["status"], "unresolved")

    def test_labelled_cover_fields_are_stamps(self):
        pdf = self.root / "cover.pdf"
        make_pdf(pdf, body="Journal: Journal of Industrial Information Integration\n"
                           "Manuscript submitted to IEEE Access")
        texts = [s["text"] for s in build_profile(pdf)["stamps"]]
        self.assertIn("Journal: Journal of Industrial Information Integration", texts)
        self.assertIn("Manuscript submitted to IEEE Access", texts)

    def test_profile_reads_margins_and_dois(self):
        pdf = self.root / "proof.pdf"
        make_pdf(pdf, header="For consideration in IEEE Access", body="Body text",
                 footer="DOI 10.1109/ACCESS.2024.0429000")
        prof = build_profile(pdf)
        self.assertIn("For consideration in IEEE Access", [s["text"] for s in prof["stamps"]])
        self.assertEqual(prof["dois"][0]["doi"], "10.1109/ACCESS.2024.0429000")
        self.assertEqual(prof["pdf"]["pages"], 1)
        self.assertEqual(len(prof["file"]["sha256"]), 16)
        self.assertEqual(self.index.resolve(prof)["venue_id"], "ieee_access")


@unittest.skipUnless(REAL_WORKSPACE and (Path(REAL_WORKSPACE) / "forms").is_dir(),
                     "set REVIEWER_WORKSPACE to a workspace with forms/")
class TestRealWorkspace(unittest.TestCase):
    def setUp(self):
        root = Path(REAL_WORKSPACE)
        self.index = load_index(root / "forms", root / "base_review.md")
        self.form_count = len(list((root / "forms").glob("*.md")))

    def test_every_form_is_valid_without_problems(self):
        self.assertEqual(self.index.problems, [])
        self.assertEqual(len(self.index.venues), self.form_count)
        for venue_id in self.index.venues:
            self.assertNotIn("{{", self.index.guideline(venue_id))

    def test_access_proof_resolves_to_ieee_access(self):
        pdf = Path(REAL_WORKSPACE) / "papers" / "Access-2026-41373_Proof_hi.pdf"
        if not pdf.is_file():
            self.skipTest("Access-2026-41373_Proof_hi.pdf not present")
        r = self.index.resolve(build_profile(pdf))
        self.assertEqual((r["status"], r["venue_id"], r["confidence"]), ("resolved", "ieee_access", "high"))


if __name__ == "__main__":
    unittest.main()
