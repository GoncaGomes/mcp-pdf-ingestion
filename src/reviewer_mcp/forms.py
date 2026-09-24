"""Venue form files: `forms/<venue_id>.md` identifies a venue and lists the fields of its review web form.

A form file holds a VENUE block, an optional CONTEXT and the FORM section:

    VENUE:
    name: IEEE Transactions on Automation Science and Engineering
    kind: journal
    acronym: T-ASE
    publisher: IEEE
    aliases: IEEE TASE
    identifiers: T-ASE-#-#
    doi: 10.1109/TASE
    url: https://www.ieee-ras.org/publications/t-ase
    CONTEXT: optional extra guidance for the reviewer (may span lines)
    ---
    FORM:
    Recommendation
      choose: Accept | Conditionally Accept | Revise and Resubmit | Reject
    Comments to the Authors
      text: 1-3 paragraphs

VENUE keys:
    name         required  official name of the journal, publisher or platform
    kind         required  journal | publisher | platform
    acronym      optional  short name used in manuscript ids and headers
    publisher    optional  publisher or operator
    aliases      optional  other names or traces printed in submitted PDFs
    identifiers  optional  manuscript/download id patterns; '#' matches a run of digits
    doi          optional  DOI prefixes of the venue (e.g. 10.1109/ACCESS)
    url          optional  venue home page, for maintainers
List values are separated by '|'.

FORM grammar: a field is a label line (not indented) followed by indented `key: value` lines. Each field is answered
by one choice -- `choose` (one option), `choose any` (one or more options) or `scale` (a whole number from low to
high) -- or by `text` (plain text whose size is stated as a sentence, a paragraph or `N-M paragraphs`). A choice may
carry a `text` size as well, for the explanation that follows it, and `explain` names the options that must carry it:

    Rate the references
      choose: Satisfactory | Unsatisfactory
      text: 1 paragraph
      explain: Unsatisfactory

`explain: always` asks for it after every option. A name may leave out an aside a web form prints after an option,
so `Unsatisfactory` also names `Unsatisfactory (explain)`. Without `explain` the text is accepted after any option
but never required; either way it is held to the stated size. `help` is guidance shown to the agent in the report
skeleton only and is never parsed; `optional: yes` allows an empty answer. Options are separated by `|`; blank lines
are ignored and `#` starts a comment line.

Only the VENUE metadata is kept in memory. The guideline given to the agent is composed on request: `base_review.md`
with {{JOURNAL_CONTEXT}} replaced by a sentence generated from the VENUE block (plus CONTEXT). The fields are read
separately for the report skeleton and the validator, so the form reaches the agent once. A form file with a malformed
VENUE block or FORM section is rejected: the agent would otherwise improvise the review form.

In a report each field is answered once, as `Label: answer` on one line, or for `text` as `Label:` followed by the
answer paragraphs. A choice that carries an explanation is answered with the option first, then the explanation.
Nothing else goes in the form section: no instructions, options or help text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

KINDS = ("choose", "choose any", "scale", "text")
CHOICES = ("choose", "choose any", "scale")
KEYS = (*KINDS, "explain", "help", "optional")
ALWAYS = ("always", "all")  # 'explain: always' asks for the explanation after every option
BRACKET_RE = re.compile(r"\s*\([^)]*\)\s*$")  # a printed aside after an option, as in 'No (explain)'
PARAGRAPHS_RE = re.compile(r"\b(?:(\d+)\s*-\s*)?(\d+)\s+paragraphs?\b", re.IGNORECASE)
SCALE_RE = re.compile(r"^(\d+)\s*-\s*(\d+)$")
KEY_RE = re.compile(r"^\s+([a-z][a-z ]*?)\s*:\s*(.*)$")


class FormError(ValueError):
    """A form file that cannot be used: malformed VENUE block or FORM section."""


@dataclass(frozen=True)
class Field:
    label: str
    kind: str
    options: tuple[str, ...] = ()
    low: int = 0
    high: int = 0
    size: str = ""
    explain: tuple[str, ...] = ()  # options whose answer must carry the explanation
    help: str = ""
    optional: bool = False

    @property
    def max_paragraphs(self) -> int | None:
        """Most paragraphs the stated size allows ('1-3 paragraphs' -> 3, 'short paragraph' -> 1), if stated."""
        match = PARAGRAPHS_RE.search(self.size)
        if match:
            return int(match.group(2))
        return 1 if re.search(r"\b(?:paragraph|sentence)\b", self.size, re.IGNORECASE) else None

    @property
    def explains(self) -> bool:
        """Whether a chosen option is followed by an explanation."""
        return self.kind in CHOICES and bool(self.size)

    def wants_explanation(self, option: str) -> bool:
        """Whether the form requires the explanation after this option ('explain:' names it)."""
        return option in self.explain

    def hint(self) -> str:
        """What the skeleton asks for in this field's placeholder."""
        described = {
            "choose": f"one of: {' | '.join(self.options)}",
            "choose any": f"one or more of: {' | '.join(self.options)}",
            "scale": f"a whole number from {self.low} to {self.high}",
            "text": self.size,
        }[self.kind]
        if self.explains:
            after = "it" if len(self.explain) == len(self.options) else f"{' or '.join(self.explain)}"
            described += f", then {self.size} explaining {after}" if self.explain else f"; {self.size} may follow it"
        extras = [described, self.help, "optional" if self.optional else ""]
        return "; ".join(extra for extra in extras if extra)


def _explained(values: dict[str, str], options: tuple[str, ...], label: str, line: int, source: str) -> tuple[str, ...]:
    """Options the form requires an explanation after: every one for 'explain: always', else those it names.
    A name may leave out an option's printed aside, so 'explain: No' names the option 'No (explain)'."""
    spec = values.get("explain", "")
    if not spec:
        return ()
    if "text" not in values:
        raise FormError(
            f"{source}: field {label!r} (line {line}) gives 'explain' without a 'text' size for the explanation"
        )
    if spec.casefold() in ALWAYS:
        return options
    named: list[str] = []
    for wanted in (part.strip() for part in spec.split("|") if part.strip()):
        folded = BRACKET_RE.sub("", wanted).casefold()
        match = next((option for option in options if BRACKET_RE.sub("", option).casefold() == folded), None)
        if match is None:
            raise FormError(
                f"{source}: field {label!r} (line {line}) explains {wanted!r}, which is not one of its "
                f"options: {' | '.join(options)}"
            )
        named.append(match)
    return tuple(dict.fromkeys(named))


def parse_form(text: str, source: str) -> tuple[Field, ...]:
    """Fields of a FORM section; raises FormError with the line number of the first problem."""
    fields: list[Field] = []
    label = ""
    values: dict[str, str] = {}
    start = 0

    def close() -> None:
        if not label:
            return
        chosen = [kind for kind in CHOICES if kind in values]
        if len(chosen) > 1 or not (chosen or "text" in values):
            raise FormError(
                f"{source}: field {label!r} (line {start}) needs one of {list(CHOICES)} or 'text', "
                f"and a choice may carry a 'text' size for the explanation after it"
            )
        kind = chosen[0] if chosen else "text"
        size = values.get("text", "")
        if "text" in values and not size:
            raise FormError(f"{source}: field {label!r} (line {start}) needs the size after 'text:'")
        help_text, optional = values.get("help", ""), values.get("optional", "no") == "yes"
        spec = values[kind]
        if kind in ("choose", "choose any"):
            options = tuple(option.strip() for option in spec.split("|") if option.strip())
            if len(options) < 2 and kind == "choose":
                raise FormError(f"{source}: field {label!r} (line {start}) needs at least two options")
            field = Field(
                label,
                kind,
                options,
                size=size,
                explain=_explained(values, options, label, start, source),
                help=help_text,
                optional=optional,
            )
        elif kind == "scale":
            match = SCALE_RE.match(spec)
            if not match or int(match.group(1)) >= int(match.group(2)):
                raise FormError(f"{source}: field {label!r} (line {start}) needs 'scale: low-high', got {spec!r}")
            field = Field(
                label,
                kind,
                low=int(match.group(1)),
                high=int(match.group(2)),
                size=size,
                explain=_explained(values, (), label, start, source),
                help=help_text,
                optional=optional,
            )
        else:
            if "explain" in values:
                raise FormError(
                    f"{source}: field {label!r} (line {start}) is a text field, so 'explain' has "
                    f"nothing to name; drop it"
                )
            field = Field(label, kind, size=size, help=help_text, optional=optional)
        if values.get("optional", "no") not in ("yes", "no"):
            raise FormError(f"{source}: field {label!r} (line {start}) has 'optional' other than yes or no")
        fields.append(field)

    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            close()
            label, values, start = " ".join(line.split()), {}, number
            if label in {field.label for field in fields}:
                raise FormError(f"{source}: field {label!r} (line {number}) is defined twice")
            continue
        match = KEY_RE.match(line)
        if not label or not match or match.group(1) not in KEYS:
            raise FormError(f"{source}: line {number} is not a label or an indented '{' | '.join(KEYS)}: value' line")
        if match.group(1) in values:
            raise FormError(f"{source}: field {label!r} gives {match.group(1)!r} twice (line {number})")
        values[match.group(1)] = " ".join(match.group(2).split())
    close()
    if not fields:
        raise FormError(f"{source}: the FORM section has no fields")
    return tuple(fields)


def skeleton(fields: tuple[Field, ...]) -> str:
    """The form section of the report skeleton: every label with a placeholder for its answer."""
    blocks = [f"{field.label}:{chr(10) if field.kind == 'text' else ' '}<to fill: {field.hint()}>" for field in fields]
    return "\n\n".join(blocks)


def field_at(line: str, fields: tuple[Field, ...]) -> Field | None:
    """The field whose label starts the line ('Label: ...'), preferring the longest label."""
    folded = line.strip().casefold()
    longest_first = sorted(fields, key=lambda field: -len(field.label))
    return next((field for field in longest_first if folded.startswith(f"{field.label.casefold()}:")), None)


def split_answers(section: str, fields: tuple[Field, ...]) -> tuple[dict[str, str], list[str]]:
    """The answer of each field found in a report's form section, and the problems of its layout."""
    answers: dict[str, str] = {}
    problems: list[str] = []
    current: Field | None = None
    for line in section.splitlines():
        field = field_at(line, fields)
        if field is not None:
            if field.label in answers:
                problems.append(f"The field {field.label!r} is answered twice.")
            answers[field.label] = line.strip()[len(field.label) + 1 :].strip()
            current = field
        elif current is not None:
            answers[current.label] += "\n" + line.rstrip()
        elif line.strip():
            problems.append(
                f"Text outside the form fields: {line.strip()[:60]!r}. The form section holds only 'Label: answer' "
                "entries, without instructions, options or help text."
            )
    return {label: value.strip() for label, value in answers.items()}, problems


def _chosen(field: Field, answer: str) -> tuple[str, str] | None:
    """The option an answer opens with and the explanation after it, longest option first."""
    folded = answer.strip().casefold()
    for option in sorted(field.options, key=len, reverse=True):
        for written in (option, BRACKET_RE.sub("", option).strip()):
            head = written.casefold()
            if folded.startswith(head) and (len(folded) == len(head) or not folded[len(head)].isalnum()):
                return option, answer.strip()[len(written) :].strip(" .:;,-\n")
    return None


def answer_problems(field: Field, answer: str) -> list[str]:
    """Problems of one answer against its field."""
    name = f"the field {field.label!r}"
    if not answer:
        return [] if field.optional else [f"Answer {name}; it is empty."]
    problems: list[str] = []
    value = answer.strip().rstrip(".").strip()
    folded = value.casefold()
    if field.kind == "choose" and field.explains:
        picked = _chosen(field, answer)
        if picked is None:
            problems.append(f"Open the answer to {name} with one of: {' | '.join(field.options)} (got {value[:60]!r}).")
        else:
            option, explanation = picked
            if not explanation and field.wants_explanation(option):
                problems.append(
                    f"The option {option!r} of {name} asks for an explanation; "
                    f"write it after the option, {field.size} of it."
                )
            problems.extend(_size_problems(field, name, explanation))
    elif field.kind == "choose" and folded not in {option.casefold() for option in field.options}:
        problems.append(f"Answer {name} with exactly one of: {' | '.join(field.options)} (got {value[:60]!r}).")
    elif field.kind == "choose any":
        rest = folded
        found = 0
        for option in sorted(field.options, key=len, reverse=True):
            if option.casefold() in rest:
                found += 1
                rest = rest.replace(option.casefold(), " ")
        if not found or re.sub(r"[\s,;]+|\band\b", "", rest):
            options = " | ".join(field.options)
            problems.append(f"Answer {name} with one or more of: {options}, separated by commas (got {value[:60]!r}).")
    elif field.kind == "scale" and not (value.isdigit() and field.low <= int(value) <= field.high):
        problems.append(f"Answer {name} with a whole number from {field.low} to {field.high} (got {value[:20]!r}).")
    elif field.kind == "text":
        problems.extend(_size_problems(field, name, answer))
    return problems


def _size_problems(field: Field, name: str, text: str) -> list[str]:
    """Whether a written answer keeps to the size the form states."""
    if field.max_paragraphs is None or not text.strip():
        return []
    paragraphs = len([block for block in re.split(r"\n\s*\n", text) if block.strip()])
    if paragraphs <= field.max_paragraphs:
        return []
    return [
        f"The answer to {name} has {paragraphs} paragraphs; the form asks for {field.size} "
        f"(at most {field.max_paragraphs})."
    ]


def labels_elsewhere(section: str, own: tuple[Field, ...], other_labels: set[str]) -> list[str]:
    """Lines that start with the label of a field of another venue's form. One-word labels ('Title', 'Results') are
    ignored: an answer line may start with such a word."""
    mine = {field.label.casefold() for field in own}
    foreign = sorted(
        (label for label in other_labels if " " in label and label.casefold() not in mine), key=len, reverse=True
    )
    found = []
    for line in section.splitlines():
        folded = line.strip().casefold()
        label = next((label for label in foreign if folded.startswith(f"{label.casefold()}:")), None)
        if label and not field_at(line, own):
            found.append(label)
    return [f"The field {label!r} belongs to another venue's form; remove it." for label in dict.fromkeys(found)]


VENUE_KINDS = ("journal", "publisher", "platform")
REQUIRED_KEYS = ("name", "kind")
SCALAR_KEYS = ("name", "kind", "acronym", "publisher", "url")
LIST_KEYS = ("aliases", "identifiers", "doi")
PLACEHOLDERS = ("{{JOURNAL_CONTEXT}}",)
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9._#-]+$")
DOI_RE = re.compile(r"^10\.\d{4,9}(/\S+)?$")
VENUE_ID_RE = re.compile(r"^[a-z0-9_-]{2,64}$")


@dataclass(frozen=True)
class VenueForm:
    """VENUE metadata of a form file; the context and fields stay on disk until they are needed."""

    venue_id: str
    path: Path
    name: str
    kind: str
    acronym: str = ""
    publisher: str = ""
    url: str = ""
    aliases: tuple[str, ...] = ()
    identifiers: tuple[str, ...] = ()
    doi: tuple[str, ...] = ()

    def describe(self) -> dict[str, str]:
        return {"venue_id": self.venue_id, "name": self.name, "kind": self.kind}


def split_form_file(content: str) -> tuple[str, str]:
    """Split a form file into (head, form); the head holds the VENUE block and CONTEXT."""
    if "FORM:" in content:
        head, form = content.split("FORM:", 1)
        return head.strip().rstrip("- \n\r"), form.strip()
    if "---" in content:
        head, form = content.split("---", 1)
        return head.strip(), form.strip()
    return content.strip(), ""


def parse_venue_block(head: str, source: str) -> tuple[dict[str, Any], str]:
    """Parse the VENUE block and the optional CONTEXT text of a form file head."""
    lines = head.splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip() == "VENUE:"]
    if not starts:
        raise FormError(f"{source}: no 'VENUE:' block before the form")

    fields: dict[str, Any] = {}
    extra: list[str] = []
    in_context = False
    for line in lines[starts[0] + 1 :]:
        stripped = line.strip()
        if in_context:
            extra.append(line)
            continue
        if stripped.upper().startswith("CONTEXT:"):
            in_context = True
            extra.append(stripped[len("CONTEXT:") :])
            continue
        if not stripped:
            continue
        m = re.match(r"^([a-z_]+)\s*:\s*(.*)$", stripped)
        if not m:
            raise FormError(f"{source}: VENUE line is not 'key: value': {stripped!r}")
        key, value = m.group(1), m.group(2).strip()
        if key not in SCALAR_KEYS + LIST_KEYS:
            raise FormError(f"{source}: unknown VENUE key {key!r}")
        if key in fields:
            raise FormError(f"{source}: VENUE key {key!r} given twice")
        if key in LIST_KEYS:
            fields[key] = tuple(item.strip() for item in value.split("|") if item.strip())
        elif value:
            fields[key] = value

    for key in REQUIRED_KEYS:
        if not fields.get(key):
            raise FormError(f"{source}: VENUE block is missing {key!r}")
    if fields["kind"] not in VENUE_KINDS:
        raise FormError(f"{source}: VENUE kind must be one of {VENUE_KINDS}, got {fields['kind']!r}")
    for pattern in fields.get("identifiers", ()):
        if not IDENTIFIER_RE.match(pattern) or "#" not in pattern or not re.search(r"[A-Za-z]", pattern):
            raise FormError(
                f"{source}: identifier {pattern!r} must use letters, digits, '.', '_', '-' "
                f"and at least one '#' digit placeholder"
            )
    for prefix in fields.get("doi", ()):
        if not DOI_RE.match(prefix):
            raise FormError(f"{source}: DOI prefix {prefix!r} must look like 10.NNNN or 10.NNNN/suffix")

    return fields, "\n".join(extra).strip()


def context_sentence(fields: dict[str, Any], extra: str) -> str:
    """Build the reviewer-facing context from the VENUE block."""
    name = fields["name"]
    acronym = fields.get("acronym", "")
    publisher = fields.get("publisher", "")
    label = f"{name} ({acronym})" if acronym and acronym.lower() not in name.lower() else name

    if fields["kind"] == "journal":
        text = f"Review the academic paper in attachment, submitted to the journal {label}"
        if publisher and publisher.lower() not in name.lower():
            text += f", published by {publisher}"
        text += "."
    elif fields["kind"] == "publisher":
        text = (
            f"Review the academic paper in attachment, submitted to a journal published by {label}. "
            f"The review form below is shared by all {name} journals; take the specific journal name "
            f"from the manuscript."
        )
    else:
        text = (
            f"Review the academic paper in attachment, submitted to a conference or journal that manages "
            f"its peer review on the {label} platform"
        )
        if publisher and publisher.lower() not in name.lower():
            text += f" (operated by {publisher})"
        text += (
            ". The review form below is the platform's standard form; take the specific event or journal "
            "name from the manuscript."
        )

    return f"{text}\n\n{extra}" if extra else text


def _read_parts(path: Path) -> tuple[dict[str, Any], str, str]:
    """Read and validate a venue_form: (VENUE fields, context sentence, form)."""
    head, form = split_form_file(path.read_text(encoding="utf-8"))
    fields, extra = parse_venue_block(head, path.name)
    if not form:
        raise FormError(
            f"{path.name}: FORM section is empty or absent; declare the venue form after a 'FORM:' or '---' delimiter"
        )
    parse_form(form, path.name)
    return fields, context_sentence(fields, extra), form


def parse_venue_form(path: Path) -> VenueForm:
    """Validate one form file and keep only its VENUE metadata."""
    venue_id = path.stem
    if not VENUE_ID_RE.match(venue_id):
        raise FormError(f"{path.name}: file name must be a venue id matching {VENUE_ID_RE.pattern}")
    fields, _, _ = _read_parts(path)
    return VenueForm(
        venue_id=venue_id,
        path=path,
        name=fields["name"],
        kind=fields["kind"],
        acronym=fields.get("acronym", ""),
        publisher=fields.get("publisher", ""),
        url=fields.get("url", ""),
        aliases=fields.get("aliases", ()),
        identifiers=fields.get("identifiers", ()),
        doi=fields.get("doi", ()),
    )


def compose_guideline(base_text: str, venue_form: VenueForm) -> str:
    """Merge a form file's context, read from disk now, into the base review template."""
    _, context, _ = _read_parts(venue_form.path)
    text = base_text.replace("{{JOURNAL_CONTEXT}}", context)
    leftover = sorted(set(re.findall(r"\{\{[A-Z_]+\}\}", text)))
    if leftover:
        raise FormError(f"{venue_form.path.name}: unsubstituted placeholders remain: {leftover}")
    return text


def read_fields(venue_form: VenueForm) -> tuple[Field, ...]:
    """The fields of a form file's venue form, read from disk now (see forms.py for the grammar)."""
    return parse_form(_read_parts(venue_form.path)[2], venue_form.path.name)
