import re
from typing import Literal, TypedDict


Gender = Literal["male", "female", "unknown"]


class GenderPrediction(TypedDict):
    gender: Gender
    confidence: float
    reason: str


FEMALE_NAMES = {
    "nəzrin",
    "leyla",
    "aysel",
    "günel",
    "nərgiz",
    "fidan",
    "nigar",
    "sevinc",
    "aytən",
    "lamiyə",
    "lamiya",
    "aygün",
    "şəbnəm",
    "xədicə",
    "fatimə",
    "zəhra",
    "nərmin",
    "turanə",
    "turana",
    "ilhamə",
    "fərqanə",
    "mərziyə",
    "aydan",
    "təranə",
    "gülər",
    "sevil",
    "məleykə",
    "samirə",
    "xatın",
    "mədinə",
    "səbinə",
    "əfsanə",
    "rəna",
    "günay",
    "ləman",
    "aytac",
    "aynur",
    "zeynəb",
    "könül",
    "röya",
    "ülviyyə",
    "əminə",
    "ofeliya",
    "şəfəq",
    "şərqiyyə",
    "lalə",
    "bənövşə",
    "firuzə",
    "pərvanə",
    "dilara",
    "elmira",
    "gülnar",
    "humay",
    "iradə",
    "mehriban",
    "nəzakət",
    "rəsmiyyə",
    "səidə",
    "tahirə",
    "vüsalə",
    "yegənə",
    "zamirə",
    "maya",
    "tamilla",
    "svetlana",
    "natavan",
    "zülfiyyə",
    "həcər",
    "salatın",
    "mehri",
    "nərminə",
    "sevdagül",
    "aylin",
    "damla",
    "yağmur",
    "dəniz",
    "şəlalə",
    "sürəyya",
    "balaca",
    "gülxanım",
    "durru",
}

MALE_NAMES = {
    "tural",
    "əli",
    "eli",
    "elvin",
    "nicat",
    "vüsal",
    "vusal",
    "kənan",
    "kenan",
    "murad",
    "orxan",
    "orhan",
    "elşən",
    "elsen",
    "fərid",
    "ferid",
    "kamran",
    "rəşad",
    "resad",
    "şəhriyar",
    "ilqar",
    "bəxtiyar",
    "elnur",
    "mahir",
    "rəşid",
    "anar",
    "vüqar",
    "fuad",
    "zaur",
    "sənan",
    "senan",
    "cavid",
    "eyvaz",
    "rauf",
    "teymur",
    "rəsul",
    "eldar",
    "yunis",
    "yusif",
    "samir",
    "vəli",
    "məmməd",
    "rüstəm",
    "elçin",
    "şahin",
    "ramin",
    "famil",
    "asif",
    "vasif",
    "aqşin",
    "cahangir",
    "bayram",
    "məqsəd",
    "mirzə",
    "emin",
    "nurlan",
    "rəhim",
    "həsən",
    "hüseyn",
    "ibrahim",
    "ömər",
    "osman",
    "süleyman",
    "ismayıl",
    "cabbar",
    "toğrul",
    "ayxan",
    "əsgər",
    "bahadur",
    "ceyhun",
    "elmir",
    "faiq",
    "xəyyam",
    "namiq",
    "pərviz",
    "rövşən",
    "sabir",
    "tariyel",
    "yaşar",
    "ömer",
    "hamid",
    "həmid",
    "şamil",
    "ilham",
    "mübariz",
    "pənah",
}

UNISEX_NAMES = {
    "arzu",
    "ədalət",
    "edalet",
    "xəyal",
    "xeyal",
    "ümid",
    "umid",
    "dəniz",
    "deniz",
    "ismət",
    "ismet",
    "səfa",
    "sefa",
    "nur",
    "şahmar",
    "bəyan",
    "hikmət",
    "hikmet",
    "şirin",
    "tərlan",
    "terlan",
    "izzət",
    "izzet",
    "şöhrət",
    "soltan",
    "sultan",
    "bəxti",
}

FEMALE_SUFFIXES = ("ova", "eva", "skaya", "datter")
MALE_SUFFIXES = ("ov", "ev", "ski", "skiy", "son")
NEUTRAL_SUFFIXES = ("zadə", "li", "lu", "lü", "soy")

FEMALE_CONTEXT = (
    re.compile(r"(?iu)\bxanım\b"),
    re.compile(r"(?iu)\b(?:mrs|ms)\.?\s+[A-ZƏÖÜĞÇŞİ]"),
    re.compile(r"(?iu)\bshe\s*/\s*her\b"),
)
MALE_CONTEXT = (
    re.compile(r"(?iu)\bcənab\b"),
    re.compile(r"(?iu)\bmr\.?\s+[A-ZƏÖÜĞÇŞİ]"),
    re.compile(r"(?iu)\bhe\s*/\s*him\b"),
    re.compile(r"(?iu)\bhərbi\s+xidmət\b"),
    re.compile(r"(?iu)\bmilitary\s+service\b"),
    re.compile(r"(?iu)\baskerlik\b"),
    re.compile(r"(?iu)\bвоенная\s+служба\b"),
)


def _prediction(gender: Gender, confidence: float, reason: str) -> GenderPrediction:
    return {"gender": gender, "confidence": confidence, "reason": reason}


def _tokens(full_name: str) -> list[str]:
    return re.findall(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*", full_name.casefold(), flags=re.UNICODE)


def _context_prediction(cv_text: str) -> GenderPrediction | None:
    for pattern in FEMALE_CONTEXT:
        if pattern.search(cv_text):
            return _prediction("female", 0.78, f"CV context matched female indicator: {pattern.pattern}")
    for pattern in MALE_CONTEXT:
        if pattern.search(cv_text):
            return _prediction("male", 0.78, f"CV context matched male indicator: {pattern.pattern}")
    return None


def detect_gender(full_name: str | None, cv_text: str = "") -> GenderPrediction:
    if not full_name or not isinstance(full_name, str):
        return _prediction("unknown", 0.0, "Full name is missing.")

    tokens = _tokens(full_name)
    if not tokens:
        return _prediction("unknown", 0.0, "Full name does not contain usable name tokens.")

    first_name = tokens[0]
    last_name = tokens[-1]

    if "qızı" in tokens or "qizi" in tokens:
        return _prediction("female", 0.99, "Patronymic indicator qızı/qizi matched.")
    if "oğlu" in tokens or "oglu" in tokens:
        return _prediction("male", 0.99, "Patronymic indicator oğlu/oglu matched.")

    if last_name.endswith(FEMALE_SUFFIXES):
        return _prediction("female", 0.95, "Surname matched a female-coded suffix.")
    if last_name.endswith(MALE_SUFFIXES):
        return _prediction("male", 0.95, "Surname matched a male-coded suffix.")
    if first_name.endswith("gül"):
        return _prediction("female", 0.90, "First name matched the -gül female indicator.")

    # Neutral surnames such as -zadə/-li/-lu/-lü/-soy do not decide gender.
    # Ambiguous/unisex first names require contextual evidence.
    if first_name in UNISEX_NAMES:
        context = _context_prediction(cv_text)
        return context or _prediction(
            "unknown",
            0.20,
            "First name is ambiguous/unisex and no reliable CV context indicator was found.",
        )

    if first_name in FEMALE_NAMES:
        return _prediction("female", 0.92, "First name matched the Azerbaijani/Turkish female-name registry.")
    if first_name in MALE_NAMES:
        return _prediction("male", 0.92, "First name matched the Azerbaijani/Turkish male-name registry.")

    # Explicitly keep neutral surname suffixes from becoming evidence by themselves.
    if last_name.endswith(NEUTRAL_SUFFIXES):
        context = _context_prediction(cv_text)
        return context or _prediction(
            "unknown",
            0.18,
            "Surname suffix is gender-neutral and the first name/context is inconclusive.",
        )

    context = _context_prediction(cv_text)
    if context:
        return context

    return _prediction("unknown", 0.10, "No reliable name or CV context indicator matched.")


def normalize_explicit_gender(value: str | None) -> GenderPrediction:
    normalized = (value or "").strip().casefold()
    male_values = {"male", "m", "man", "kişi", "kisi", "erkek", "мужской", "мужчина"}
    female_values = {"female", "f", "woman", "qadın", "qadin", "kadın", "kadin", "женский", "женщина"}
    if normalized in male_values:
        return _prediction("male", 0.99, "Gender was explicitly stated in the CV.")
    if normalized in female_values:
        return _prediction("female", 0.99, "Gender was explicitly stated in the CV.")
    return _prediction("unknown", 0.25, "Explicit gender text was present but could not be normalized safely.")
