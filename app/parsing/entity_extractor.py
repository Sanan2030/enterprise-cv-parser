import re
from functools import lru_cache
from urllib.parse import unquote, urlsplit

import phonenumbers
import spacy
from spacy.language import Language

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
def nlp_model() -> Language | None:
    return spacy.load(settings.SPACY_MODEL) if settings.SPACY_MODEL else None


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
        return result

    def extract(
        self, header: list[LayoutBlock], blocks: list[LayoutBlock], links: list[Hyperlink]
    ) -> PersonalInformation:
        link_blocks = [LayoutBlock(link.bbox, unquote(link.url), link.page) for link in links]
        contacts = self.extract_contact_info("\n".join(b.text for b in blocks), links)
        model = nlp_model()
        name = None
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
        return personal
