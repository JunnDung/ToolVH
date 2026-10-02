"""Local terminology policy. Names are protected before text leaves the app."""
from __future__ import annotations
import re
from collections import Counter, defaultdict

ORI_NAMES = (
    "Ori", "Ku", "Naru", "Gumo", "Kwolok", "Shriek", "Seir", "Baur", "Howl",
    "Lupo", "Tokk", "Opher", "Twillen", "Grom", "Tuley", "Mokk", "Moki", "Motay", "Kii", "Niwen", "Nibel", "Gorlek",
    "Horn Beetle", "Willow Stone", "Spirit Shard", "Spirit Shards", "Spirit Light", "Gorlek Ore",
    "Inkwater Marsh", "Kwolok's Hollow", "Wellspring Glades", "Wellspring",
    "Baur's Reach", "Silent Wood", "Silent Woods", "Luma Pools", "Mouldwood Depths", "Windswept Wastes",
    "Windtorn Ruins", "Midnight Burrows", "Weeping Ridge", "Steam", "Discord",
)
ORI_EXAMPLES = {
    "Fend off Howl": "Đẩy lùi Howl",
    "Defeat the Horn Beetle": "Đánh bại Horn Beetle",
    "Defeat the Willow Stone": "Đánh bại Willow Stone",
    "Reach the Wellspring Glades": "Đến Wellspring Glades",
    "New Spirit Shard!": "Nhận được Spirit Shard mới!",
    "Upgrade discovered!": "Phát hiện nâng cấp mới!",
    "You found a new quest item!": "Bạn đã tìm thấy vật phẩm nhiệm vụ mới!",
}

def ori_project(project):
    return any(e.locator.get("type") == "MoonTranslatedMessageProvider" for e in project.entries)

def inferred_names(project):
    # Require an explicit semantic name field; title case alone is not evidence.
    names = set(ORI_NAMES if ori_project(project) else ("Steam", "Discord"))
    if project.root.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1].casefold() == "childrenofmorta":
        names.update(("Barahut", "Caeldippo Caves", "Lucy", "Kevin", "Margaret", "Bergson"))
    name_table = re.compile(r"^(?:Locations|CharacterNames) / Dòng \d+ /", re.I)
    name_field = re.compile(r"(?<![A-Za-z])(?:location|area|region|character|npc|item|weapon|ability|shard)[_ /.-]*name(?:[_ /.-]|$)", re.I)
    for e in project.entries:
        speaker = e.locator.get("speaker_name")
        if isinstance(speaker, str) and 1 <= len(speaker.strip()) <= 70 and not re.search(r"[{}<>\n\r]", speaker):
            names.add(speaker.strip())
        text = e.source.strip()
        if (text.casefold() not in ("forest", "temple") and (name_field.search(e.context) or name_table.search(e.context)) and not re.search(r"description|achievement", e.context, re.I) and 1 <= len(text) <= 70
                and len(text.split()) <= 8 and not re.search(r"[{}<>\n\r.!?=]", text)
                and re.search(r"[A-Za-z]", text)):
            names.add(text)
    return sorted(names, key=lambda s: (-len(s), s.casefold()))

def term_policy(project):
    terms = {}
    if project.preserve_names:
        terms.update({n: n for n in inferred_names(project)})
        terms.update({n.strip(): n.strip() for n in project.protected_names if n.strip()})
    # Explicit user terminology wins over automatic preservation, including case variants.
    for source, target in project.glossary.items():
        for old in list(terms):
            if old.casefold() == source.casefold():
                del terms[old]
        terms[source] = target
    return terms

def term_pattern(terms):
    if not terms:
        return re.compile(r"(?!x)x")
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(s) for s in sorted(terms, key=len, reverse=True)) + r")(?!\w)", re.I)

def term_value(matched, terms):
    for source, target in terms.items():
        if source.casefold() == matched.casefold():
            return matched if source == target else target
    return matched

def requirements(source, terms):
    # Keep formatting payloads out of semantic checks (e.g. <sprite name="Ori">).
    from .translation import TOKENS
    plain = TOKENS.sub(" ", source)
    return Counter(term_value(m[0], terms) for m in term_pattern(terms).finditer(plain))

def validate_entry(project, entry, target, terms=None):
    from .translation import validate
    errors = validate(entry.source, target)
    if not isinstance(target, str):
        return errors
    terms = term_policy(project) if terms is None else terms
    from .translation import TOKENS
    plain = TOKENS.sub(" ", target)
    for expected, count in requirements(entry.source, terms).items():
        actual = len(re.findall(r"(?<!\w)" + re.escape(expected) + r"(?!\w)", plain, flags=re.I))
        if actual < count:
            errors.append(f"Tên riêng/thuật ngữ phải giữ: {expected} (cần {count} lần).")
    return errors


def repair_protected_names(project):
    """Restore standalone protected names/glossary entries; never replace prose by guessing."""
    from .translation import mask, unmask, normalize_translation
    terms = term_policy(project)
    repaired = 0
    for entry in project.entries:
        if not entry.enabled or not entry.translation:
            continue
        masked, prefix, values = mask(entry.source, terms)
        if re.search(r"\w", re.sub(re.escape(prefix) + r"\d+__", "", masked)):
            continue
        target = normalize_translation(unmask(masked, prefix, values))
        if target != entry.translation and not validate_entry(project, entry, target, terms):
            entry.translation, entry.error = target, ""
            repaired += 1
    return repaired


def audit(project):
    terms = term_policy(project)
    count = 0
    for e in project.entries:
        if e.translation:
            e.error = " ".join(validate_entry(project, e, e.translation, terms))
            count += bool(e.error)
    return count

def context_map(project):
    groups = defaultdict(list)
    for e in project.entries:
        # Never borrow dialogue from a different Unity object or localization table.
        scope = e.context.rsplit(" / ", 1)[0]
        if e.file.lower().endswith(".rpy"):
            # Dialogue changes speaker within a scene; keep neighbors in its label.
            scope = re.sub(r" / dòng \d+(?: / đoạn \d+)?$", "", e.context).split(" / ", 1)[0]
        scope = re.sub(r" / Dòng \d+(?= /)", "", scope, flags=re.I)
        key = (e.file, e.locator.get("object"), e.locator.get("container"), scope)
        groups[key].append(e)
    result = {}
    for group in groups.values():
        for i, e in enumerate(group):
            adjacent = [x.source[:240] for x in group[max(0, i-1):i+2] if x is not e]
            result[e.id] = {"previous_or_next": adjacent, "note": "Nearby strings are context only, not text to translate."}
    return result
