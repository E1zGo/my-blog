"""Conservative, offline PDF text cleanup. Original pages remain authoritative.

Keep the PDF extractor's reading order; never guess mathematical LaTeX. Separate
visual text from prose and split prose on sentence boundaries without overlaps.
"""
import re
import textwrap

PAPER_INDEX_VERSION = 2
LIGATURES = str.maketrans({"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"})
HEADING = re.compile(r"^(?:(?:\d{1,2}(?:\.\d{1,2})+\.?|\d{1,2}\.|[A-Z]\.)\s+[A-Z][^,\n]{2,90}|Abstract|References|Acknowledg(?:e)?ments|Appendix(?:\s+[A-Z])?)$")
MATH = re.compile(r"[∑∏√∇∫≈≤≥∼ϵθφΣαβ]|[\U0001d400-\U0001d7ff]")
CAPTION = re.compile(r"^(?:Figure|Fig\.|Table|Algorithm)\s+\d+[.:]?")


def normalize_prose(text):
    text = text.translate(LIGATURES).replace("\x00", "").replace("\u00ad", "")
    # Preserve common compound prefixes; heal typesetting line-end word breaks.
    def join_word(match):
        left, right = match.group(1), match.group(2)
        keep = left.lower() in {"non", "multi", "low", "high", "zero", "self", "patch", "single", "end"}
        keep |= (left + "-" + right).lower() in {"super-resolution", "state-of", "fine-tuning", "pre-trained", "pre-training", "pre-train", "pre-processing"}
        return left + ("-" if keep else "") + right
    text = re.sub(r"([A-Za-z]+)-\s*\n\s*([a-z]+)", join_word, text)
    return re.sub(r"[ \t\n]+", " ", text).strip()


def sentence_parts(text, size=1300):
    """Pack whole sentences; mark rare oversized sentences as continuations."""
    sentences = re.split(r"(?<=[.!?。！？])\s+(?=[A-Z\u3400-\u9fff])", text)
    pending = ""
    for sentence in sentences:
        if pending and len(pending) + len(sentence) + 1 > size:
            yield pending, False
            pending = ""
        if len(sentence) > size:
            if pending:
                yield pending, False
                pending = ""
            for part in textwrap.wrap(sentence, size, break_long_words=True, break_on_hyphens=False):
                yield part, True
        else:
            pending = (pending + " " + sentence).strip()
    if pending:
        yield pending, False


def page_blocks(text, page):
    lines = text.translate(LIGATURES).replace("\r\n", "\n").splitlines()
    footnotes = [line for line in lines if re.match(r"^[∗*†]\s*(?:Equal contribution|Corresponding author)", line.strip(), re.I)]
    # Drop only a recognizable page footer / arXiv side stamp, not numerical data.
    lines = [line for i, line in enumerate(lines) if not (
        (i >= len(lines) - 3 and line.strip() == str(page)) or line.strip().startswith("arXiv:") or line in footnotes
    )]
    types = []
    in_algorithm = False
    for line in lines:
        clean = line.strip()
        words = re.findall(r"[A-Za-z]{2,}", clean)
        if re.match(r"^Algorithm\s+\d+[.:]", clean):
            in_algorithm = True
        if in_algorithm:
            kind = "visual"
            if re.match(r"^return(?:\b|[xXyY][0-9₀-₉])", clean):
                in_algorithm = False
        elif not clean:
            kind = "break"
        elif HEADING.fullmatch(clean):
            kind = "heading"
        elif len(words) < 5 and (MATH.search(clean) or "=" in clean):
            kind = "visual"
        elif len(words) < 4 and len(re.findall(r"[\u3400-\u9fff]", clean)) < 12:
            kind = "short"
        else:
            kind = "prose"
        types.append(kind)
    # A single short wrapped line is prose. Runs of labels are kept separately.
    original_types = types[:]
    for i, kind in enumerate(original_types):
        if kind == "short":
            adjacent_short = (i > 0 and original_types[i-1] in {"short", "visual"}) or (i+1 < len(types) and original_types[i+1] in {"short", "visual"})
            types[i] = "visual" if adjacent_short else "prose"
    # Short labels surrounded by diagram text should stay with the diagram.
    for i in range(1, len(types)-1):
        if types[i] == "prose" and len(lines[i]) < 75 and types[i-1] == types[i+1] == "visual" and not CAPTION.match(lines[i]):
            types[i] = "visual"
    pending, category = [], None
    for line, kind in zip(lines, types):
        if kind != category or kind in {"break", "heading"} or CAPTION.match(line.strip()):
            if pending:
                yield category, "\n".join(pending)
            pending = []
        if kind not in {"break", "heading"}:
            pending.append(line.strip())
        elif kind == "heading":
            yield kind, line.strip()
        category = kind
    if pending:
        yield category, "\n".join(pending)
    if footnotes:
        yield "visual", "\n".join(footnotes)


def paper_fragments(pages):
    section = ""
    for page, text in pages:
        order = 0
        for kind, block in page_blocks(text, page):
            if kind == "heading":
                section = block
                continue
            normalized = normalize_prose(block) if kind != "visual" else block.strip()
            if not normalized:
                continue
            parts = sentence_parts(normalized) if kind != "visual" else ((p, False) for p in textwrap.wrap(normalized, 1800, replace_whitespace=False, drop_whitespace=False))
            for fragment, continued in parts:
                order += 1
                structure = {"type": kind, "section": section, "order": order,
                             "continued": continued, "math": bool(MATH.search(fragment) or kind == "visual")}
                if CAPTION.match(fragment) and kind != "visual":
                    structure["type"] = "caption"
                if kind == "prose" and (re.match(r"^[a-z]", fragment) or not re.search(r"[.!?。！？:：][\])\"']?$", fragment)):
                    structure["partial"] = True
                if fragment in footnote_text(text):
                    structure["section"] = ""
                yield page, fragment.strip(), structure


def footnote_text(text):
    return [line.strip() for line in text.splitlines() if re.match(r"^[∗*†]\s*(?:Equal contribution|Corresponding author)", line.strip(), re.I)]
