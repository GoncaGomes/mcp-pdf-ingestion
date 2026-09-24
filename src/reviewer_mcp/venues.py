"""Venue index built from forms, and venue resolution from submission profiles.

The index reads `forms/*.md` (see `forms.py`) and `base_review.md` directly and is
rebuilt whenever they change. Adding a venue needs only a new venue_form: there is no build
step, guidelines are composed in memory, and no venue knowledge lives in this package.

Resolution matches a submission profile (see `profile.py`) against the index.
Precedence is platform > journal > publisher: a paper written in a publisher's
template but reviewed through a conference platform gets the platform form.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from reviewer_mcp.forms import (
    PLACEHOLDERS,
    VENUE_ID_RE,
    Field,
    FormError,
    VenueForm,
    compose_guideline,
    parse_venue_form,
    read_fields,
)

KIND_RANK = {"platform": 0, "journal": 1, "publisher": 2}


def normalise(text: str) -> str:
    """Casefold, fold '&' to 'and' and punctuation to spaces; padded for word containment."""
    s = unicodedata.normalize("NFKC", text).casefold().replace("&", " and ")
    s = re.sub(r"[^0-9a-z]+", " ", s).strip()
    return f" {s} " if s else ""


def pattern_regex(pattern: str) -> str:
    """Translate an identifier pattern ('#' = digits, '-'/'_' interchangeable) to a regex body."""
    out: list[str] = []
    for ch in pattern:
        if ch == "#":
            out.append(r"\d+")
        elif ch in "-_":
            out.append(r"[-_ ]")
        elif ch == ".":
            out.append(r"[._]")
        else:
            out.append(re.escape(ch))
    return "".join(out)


class VenueIndex:
    """VENUE metadata of valid forms and the problems found while loading.

    Guideline text is never held here: it is merged from disk each time it is requested.
    """

    def __init__(self, venues: dict[str, VenueForm], base_path: Path, problems: list[str]) -> None:
        self.venues = venues
        self.base_path = base_path
        self.problems = problems

    @staticmethod
    def _base_problem(base_path: Path) -> str | None:
        if not base_path.is_file():
            return f"Base review template not found: {base_path}"
        text = base_path.read_text(encoding="utf-8")
        missing = [p for p in PLACEHOLDERS if p not in text]
        return f"{base_path.name}: missing placeholders {missing}" if missing else None

    @classmethod
    def load(cls, form_files: list[Path], base_path: Path) -> VenueIndex:
        problems: list[str] = []
        base_problem = cls._base_problem(base_path)
        if base_problem:
            problems.append(base_problem)

        venues: dict[str, VenueForm] = {}
        for path in form_files:
            try:
                venue_form = parse_venue_form(path)
            except FormError as e:
                problems.append(str(e))
                continue
            except OSError as e:
                problems.append(f"{path.name}: unreadable ({e})")
                continue
            venues[venue_form.venue_id] = venue_form
        problems.extend(cls._collisions(venues))
        return cls(venues, base_path, problems)

    @staticmethod
    def _collisions(venues: dict[str, VenueForm]) -> list[str]:
        claims: dict[tuple[str, str], set[str]] = {}
        for v in venues.values():
            for label in (v.name, *v.aliases, v.acronym):
                if label:
                    claims.setdefault(("name/alias/acronym", normalise(label)), set()).add(v.venue_id)
            for pattern in v.identifiers:
                claims.setdefault(("identifier", pattern.lower()), set()).add(v.venue_id)
            for prefix in v.doi:
                claims.setdefault(("doi", prefix.lower()), set()).add(v.venue_id)
        return [
            f"{what} {value.strip()!r} is claimed by {sorted(ids)}"
            for (what, value), ids in sorted(claims.items())
            if len(ids) > 1
        ]

    def get(self, venue_id: str | None) -> VenueForm | None:
        if not venue_id or not VENUE_ID_RE.match(venue_id.strip().lower()):
            return None
        return self.venues.get(venue_id.strip().lower())

    def guideline(self, venue_id: str) -> str:
        """Merge the guideline for a venue from disk (raises FileNotFoundError or FormError)."""
        venue = self.get(venue_id)
        if venue is None:
            raise FileNotFoundError(f"No valid form file for venue {venue_id[:64]!r}")
        problem = self._base_problem(self.base_path)
        if problem:
            raise FileNotFoundError(problem)
        return compose_guideline(self.base_path.read_text(encoding="utf-8"), venue)

    def form_fields(self, venue_id: str) -> tuple[Field, ...]:
        """The fields of the venue form, read from disk (raises FileNotFoundError or FormError)."""
        venue = self.get(venue_id)
        if venue is None:
            raise FileNotFoundError(f"No valid form file for venue {venue_id[:64]!r}")
        return read_fields(venue)

    def other_labels(self, venue_id: str) -> frozenset[str]:
        """Field labels of every other venue form, to catch a report that mixes in another venue's form."""
        labels: set[str] = set()
        for other in self.venues:
            if other != venue_id:
                try:
                    labels.update(field.label for field in self.form_fields(other))
                except (OSError, ValueError):
                    continue
        return frozenset(labels)

    # ------------------------------------------------------------------ resolution

    def evidence(self, profile: dict[str, Any]) -> list[dict[str, str]]:
        """Collect evidence linking the profile to venues."""
        stem = str(profile.get("file", {}).get("stem", ""))
        stamps = profile.get("stamps", [])
        found: list[dict[str, str]] = []

        def add(venue: VenueForm, strength: str, source: str, detail: str) -> None:
            item = {"venue_id": venue.venue_id, "strength": strength, "source": source, "detail": detail}
            if item not in found:
                found.append(item)

        venues = list(self.venues.values())
        for v in venues:
            for pattern in v.identifiers:
                if re.match(rf"^{pattern_regex(pattern)}(?!\d)", stem, re.IGNORECASE):
                    add(v, "strong", "file name", f"'{stem}' matches manuscript id pattern '{pattern}'")
            letters = re.sub(r"[^A-Za-z]", "", v.acronym)
            if len(letters) >= 3 and re.match(
                rf"^{pattern_regex(v.acronym)}[-_.](?:[A-Za-z]{{1,2}}[-_.])?\d", stem, re.IGNORECASE
            ):
                add(v, "strong", "file name", f"'{stem}' starts with the venue acronym '{v.acronym}'")

        for stamp in stamps:
            text = str(stamp.get("text", ""))
            norm = normalise(text)
            source = str(stamp.get("source", "stamp"))
            label_hits: list[tuple[VenueForm, str, str]] = []
            for v in venues:
                for pattern in v.identifiers:
                    if re.search(rf"(?<![0-9A-Za-z]){pattern_regex(pattern)}(?!\d)", text, re.IGNORECASE):
                        add(v, "strong", source, f"'{text}' contains manuscript id pattern '{pattern}'")
                for label in (v.name, *v.aliases):
                    label_norm = normalise(label)
                    if label_norm and label_norm in norm:
                        label_hits.append((v, label, label_norm))
                if v.acronym and normalise(v.acronym) in norm:
                    add(v, "medium", source, f"'{text}' mentions acronym '{v.acronym}'")
            for v, label, label_norm in label_hits:
                shadowed = any(
                    other.venue_id != v.venue_id and label_norm != other_norm and label_norm in other_norm
                    for other, _, other_norm in label_hits
                )
                if not shadowed:
                    add(v, "strong", source, f"'{text}' names '{label}'")

        for item in profile.get("dois", []):
            doi = str(item.get("doi", "")).lower()
            matches: list[tuple[int, VenueForm, str]] = []
            for v in venues:
                for prefix in v.doi:
                    p = prefix.lower()
                    if doi.startswith(p) and (len(doi) == len(p) or not doi[len(p)].isalnum()):
                        matches.append((len(p), v, prefix))
            if matches:
                longest = max(m[0] for m in matches)
                for length, v, prefix in matches:
                    if length == longest:
                        source = f"doi ({item.get('source', '')})"
                        add(v, "strong", source, f"DOI {item.get('doi')} has prefix {prefix}")
        return found

    def resolve(self, profile: dict[str, Any] | None, explicit: str | None = None) -> dict[str, Any]:
        """Resolve the venue; status is 'resolved', 'ambiguous' or 'unresolved'."""
        evidence = self.evidence(profile) if profile else []
        per_venue: dict[str, dict[str, int]] = {}
        for item in evidence:
            counts = per_venue.setdefault(item["venue_id"], {"strong": 0, "medium": 0})
            counts[item["strength"]] += 1

        result: dict[str, Any] = {
            "status": "unresolved",
            "venue_id": "",
            "name": "",
            "kind": "",
            "confidence": "",
            "evidence": evidence,
            "candidates": [],
            "conflicts": [],
            "index_problems": list(self.problems),
        }

        if explicit and explicit.strip():
            venue = self.get(explicit)
            if venue is None:
                result["conflicts"].append(f"Explicit venue {explicit.strip()[:64]!r} has no valid form file")
                return result
            others = sorted(vid for vid, c in per_venue.items() if c["strong"] and vid != venue.venue_id)
            if others:
                result["conflicts"].append(f"Explicit venue {venue.venue_id!r} differs from PDF evidence for {others}")
            result.update(venue.describe(), status="resolved", confidence="explicit")
            return result

        def candidates(ids: list[str]) -> list[dict[str, Any]]:
            return [dict(self.venues[vid].describe(), **per_venue[vid]) for vid in sorted(ids)]

        strong = [vid for vid, c in per_venue.items() if c["strong"]]
        if strong:
            best = min(KIND_RANK[self.venues[vid].kind] for vid in strong)
            top = [vid for vid in strong if KIND_RANK[self.venues[vid].kind] == best]
            if len(top) == 1:
                result.update(self.venues[top[0]].describe(), status="resolved", confidence="high")
                shadowed = sorted(set(strong) - set(top))
                if shadowed:
                    result["conflicts"].append(
                        f"Also matched {shadowed}; '{self.venues[top[0]].kind}' evidence takes precedence"
                    )
            else:
                result.update(status="ambiguous", candidates=candidates(top))
            return result

        medium = list(per_venue)
        if len(medium) == 1:
            result.update(self.venues[medium[0]].describe(), status="resolved", confidence="medium")
        elif medium:
            result.update(status="ambiguous", candidates=candidates(medium))
        return result


_INDEX_CACHE: dict[str, tuple[tuple[Any, ...], VenueIndex]] = {}


def _stat(path: Path) -> tuple[str, int, int]:
    try:
        st = path.stat()
    except OSError:
        return (str(path), 0, -1)
    return (str(path), st.st_mtime_ns, st.st_size)


def load_index(forms_dir: str | Path, base_review_path: str | Path) -> VenueIndex:
    """Load the venue index, rebuilding it only when forms or the base template change."""
    cdir = Path(forms_dir).resolve()
    base = Path(base_review_path).resolve()
    files = sorted(cdir.glob("*.md")) if cdir.is_dir() else []
    signature = tuple(_stat(f) for f in [*files, base])
    key = f"{cdir}|{base}"
    cached = _INDEX_CACHE.get(key)
    if cached and cached[0] == signature:
        return cached[1]
    index = VenueIndex.load(files, base)
    if not cdir.is_dir():
        index.problems.insert(0, f"Forms directory not found: {cdir}")
    _INDEX_CACHE[key] = (signature, index)
    return index
