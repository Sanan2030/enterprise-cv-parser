import re
from dataclasses import replace
from functools import lru_cache
from typing import Any
from urllib.parse import unquote, urlsplit

import phonenumbers

from app.core.config import settings
from app.extraction.hyperlink_extractor import Hyperlink
from app.extraction.layout_engine import LayoutBlock
from app.intelligence.provenance import provenance, sourced
from app.normalization.url_normalizer import URLNormalizer
from app.parsing.section_classifier import SectionClassifier
from app.schemas.resume import FieldWithMetadata, PersonalInformation

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
URL_REGEX = re.compile(r"(?:https?://|www\.|(?:github|linkedin)\.com/)[^\s<>]+", re.I)


@lru_cache(maxsize=1)
def nlp_model() -> Any | None:
    if not settings.SPACY_MODEL:
        return None
    try:
        import spacy
    except ImportError:
        return None
    return spacy.load(settings.SPACY_MODEL)


class EntityExtractor:
    @staticmethod
    def extract_contact_info(text: str, links: list[Hyperlink]) -> dict[str, str | None]:
        annotated = "\n".join(unquote(link.url) for link in links)
        emails = EMAIL_REGEX.findall(text + "\n" + annotated)
        phones = list(phonenumbers.PhoneNumberMatcher(text, settings.DEFAULT_PHONE_REGION))
        if not phones:
            phones = list(phonenumbers.PhoneNumberMatcher(annotated, settings.DEFAULT_PHONE_REGION))
        result = {
            "email": emails[0] if emails else None,
            "phone": phonenumbers.format_number(phones[0].number, phonenumbers.PhoneNumberFormat.E164)
            if phones
            else None,
            "linkedin": None,
            "github": None,
            "website": None,
        }
        for raw in [*URL_REGEX.findall(text), *(link.url for link in links)]:
            url = URLNormalizer.normalize(raw)
            if not url:
                continue
            parsed = urlsplit(url)
            host = parsed.hostname.removeprefix("www.")
            key = (
                "linkedin"
                if host == "linkedin.com" and parsed.path.startswith("/in/")
                else "github"
                if host == "github.com" and parsed.path.strip("/")
                else "website"
            )
            if result[key] is None:
                result[key] = url
        if result["github"] is None:
            match = re.search(
                r"(?im)\bgithub\s*:\s*([a-z0-9](?:[a-z0-9-]{0,37}[a-z0-9])?)[_ ]*(?=\n|$)", text
            )
            if match:
                result["github"] = "https://github.com/" + match[1]
        return result

    def extract(
        self, header: list[LayoutBlock], blocks: list[LayoutBlock], links: list[Hyperlink]
    ) -> PersonalInformation:
        link_blocks = [LayoutBlock(link.bbox, unquote(link.url), link.page) for link in links]
        contact_blocks = header or blocks
        contact_text = "\n".join(b.text for b in contact_blocks)
        contacts = self.extract_contact_info(contact_text, links)
        # Social links can also appear in a dedicated section or project entry.
        all_contacts = self.extract_contact_info("\n".join(b.text for b in blocks), links)
        for key in ("linkedin", "github", "website"):
            contacts[key] = contacts[key] or all_contacts[key]
        model = nlp_model()
        name = None
        # Large names can wrap onto two lines. Preserve their combined evidence.
        header = list(header)
        for first, second in zip(header[:8], header[1:9]):
            if (
                first.page_num == second.page_num
                and first.font_size >= 16
                and abs(first.font_size - second.font_size) < 1
                and abs(first.x0 - second.x0) < 5
                and 0 < second.y0 - first.y0 <= first.font_size * 1.6
                and first.text.isalpha()
                and second.text.isalpha()
            ):
                header.insert(
                    0,
                    replace(
                        first,
                        text=first.text + " " + second.text,
                        bbox=(first.x0, first.y0, max(first.x1, second.x1), second.y1),
                    ),
                )
                break
        for block in sorted(header[:12], key=lambda b: -b.font_size):
            candidate = block.text.strip()
            if SectionClassifier.classify_block(candidate)[0] or not 2 <= len(candidate.split()) <= 5:
                continue
            if re.search(r"[\d@:/|]", candidate) or re.search(
                r"\b(developer|engineer|analyst|manager|resume|curriculum|university|baku|bachelor|skills)\b",
                candidate,
                re.I,
            ):
                continue
            if not all(word.replace("-", "").replace("'", "").isalpha() for word in candidate.split()):
                continue
            if model:
                person = next(
                    (ent.text for ent in model(candidate).ents if ent.label_ in {"PERSON", "PER"}), None
                )
                if person:
                    name = sourced(person, header, 0.85)
                    break
            if candidate.istitle() or candidate.isupper():
                name = sourced(candidate, header, 0.65)
                break
        personal = PersonalInformation(
            full_name=name,
            email=sourced(contacts["email"], blocks + link_blocks, 0.98),
            linkedin=contacts["linkedin"],
            github=contacts["github"],
            website=contacts["website"],
        )
        if name:
            parts = name.value.split()
            personal.first_name = sourced(parts[0], header, name.confidence)
            personal.last_name = sourced(parts[-1], header, name.confidence)
            if len(parts) > 2:
                personal.middle_name = sourced(" ".join(parts[1:-1]), header, name.confidence)
        labels = {
            "full_name": r"full name|name|ad soyad",
            "first_name": r"first name|given name",
            "last_name": r"last name|surname|family name",
            "middle_name": r"middle name|ata adı",
            "date_of_birth": r"date of birth|dob|doğum tarixi|дата рождения",
            "gender": r"gender|sex|cins|пол",
            "nationality": r"nationality|vətəndaşlıq|гражданство",
            "location": r"address|location|ünvan|adres|адрес",
        }
        for field, aliases in labels.items():
            match = re.search(rf"(?:^|[\n|;])\s*(?:{aliases})\s*:\s*([^\n|;]+)", contact_text, re.I)
            if match:
                setattr(personal, field, sourced(match[1].strip(), contact_blocks, 0.9))
        if personal.full_name and not personal.first_name:
            parts = personal.full_name.value.split()
            personal.first_name = sourced(parts[0], contact_blocks, 0.9)
            personal.last_name = sourced(parts[-1], contact_blocks, 0.9) if len(parts) > 1 else None
            personal.middle_name = (
                sourced(" ".join(parts[1:-1]), contact_blocks, 0.9) if len(parts) > 2 else None
            )
        if not personal.full_name and personal.first_name and personal.last_name:
            personal.full_name = FieldWithMetadata(
                value=" ".join(
                    f.value for f in (personal.first_name, personal.middle_name, personal.last_name) if f
                ),
                confidence=0.9,
                provenance=personal.first_name.provenance,
            )
        numbers = list(
            dict.fromkeys(
                phonenumbers.format_number(m.number, phonenumbers.PhoneNumberFormat.E164)
                for m in phonenumbers.PhoneNumberMatcher(contact_text, settings.DEFAULT_PHONE_REGION)
            )
        )
        if len(numbers) > 1:
            phone_block = next(
                b
                for b in contact_blocks
                if any(
                    phonenumbers.format_number(m.number, phonenumbers.PhoneNumberFormat.E164) == numbers[1]
                    for m in phonenumbers.PhoneNumberMatcher(b.text, settings.DEFAULT_PHONE_REGION)
                )
            )
            personal.alternative_phone = FieldWithMetadata(
                value=numbers[1], confidence=0.9, provenance=provenance(phone_block, 0.9)
            )
        portfolio = re.search(r"(?im)^\s*portfolio\s*:\s*(\S+)", contact_text)
        if portfolio:
            personal.portfolio = URLNormalizer.normalize(portfolio[1])
        for block in header:
            match = re.search(r"(?:^|[|;])\s*(?:nationality|vətəndaşlıq)\s*:\s*([^|;]+)", block.text, re.I)
            if match:
                personal.nationality = sourced(match[1].strip(), header, 0.9)
        if contacts["phone"]:
            for block in blocks + link_blocks:
                matches = list(phonenumbers.PhoneNumberMatcher(block.text, settings.DEFAULT_PHONE_REGION))
                if any(
                    phonenumbers.format_number(m.number, phonenumbers.PhoneNumberFormat.E164)
                    == contacts["phone"]
                    for m in matches
                ):
                    personal.phone = FieldWithMetadata(
                        value=contacts["phone"], confidence=0.95, provenance=provenance(block, 0.95)
                    )
                    break
        for block in header:
            match = re.match(
                r"(?:location|address|ünvan|yaşayış yeri|adres|адрес)\s*:\s*(.+)", block.text, re.I
            )
            if match:
                personal.location = sourced(match[1], header, 0.85)
                break
        if personal.location is None:
            # An unlabeled location immediately below an email/phone line.
            for previous, block in zip(header, header[1:]):
                if (
                    EMAIL_REGEX.search(previous.text)
                    and len(block.text.split()) <= 6
                    and re.fullmatch(r"[^\W\d_]+(?:[ ,'-]+[^\W\d_]+)*", block.text)
                    and not SectionClassifier.classify_block(block.text)[0]
                ):
                    personal.location = sourced(block.text, header, 0.65)
                    break
        return personal
