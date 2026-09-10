import re

from app.extraction.layout_engine import LayoutBlock
from app.schemas.resume import ExtractedSkill, SkillsCategorized

SKILL_TAXONOMY = {
    "software_tools": ["postman", "swagger", "trello", "figma", "erp", "sap", "tiger"],
    "programming_languages": [
        "python",
        "javascript",
        "typescript",
        "java",
        "c++",
        "c#",
        "go",
        "rust",
        "php",
        "sql",
        "html",
        "css",
    ],
    "frameworks": [
        "fastapi",
        "django",
        "flask",
        "react",
        "angular",
        "vue",
        "spring boot",
        "express",
        "next.js",
    ],
    "libraries": ["pydantic", "spacy", "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch"],
    "databases": ["postgresql", "mysql", "mongodb", "redis", "sqlite", "oracle", "elasticsearch"],
    "cloud": ["aws", "azure", "gcp", "digitalocean"],
    "devops": ["docker", "kubernetes", "ci/cd", "git", "github actions", "terraform"],
    "business_analysis": [
        "bpmn",
        "uml",
        "srs",
        "agile",
        "scrum",
        "jira",
        "brd",
        "frs",
        "requirements analysis",
        "use cases",
        "lucidchart",
        "excel",
        "power bi",
        "tableau",
        "confluence",
        "visio",
        "draw.io",
        "azure devops",
        "etl",
        "uat",
    ],
    "soft_skills": ["leadership", "communication", "problem solving", "teamwork", "critical thinking"],
}


class SkillExtractor:
    @staticmethod
    def section_text(blocks: list[LayoutBlock]) -> str:
        items: list[str] = []
        previous = None
        for block in blocks:
            if (
                previous
                and block.page_num == previous.page_num
                and abs(block.x0 - previous.x0) < 10
                and 0 <= block.y0 - previous.y1 <= 3
            ):
                items[-1] += " " + block.text
            else:
                items.append(block.text)
            previous = block
        return "\n".join("• " + item for item in items)

    def extract_skills(self, text: str, explicit_section: str = "") -> SkillsCategorized:
        result = SkillsCategorized()
        known = set()
        for category, items in SKILL_TAXONOMY.items():
            for skill in items:
                pattern = r"\s+".join(re.escape(word) for word in skill.split())
                match = re.search(rf"(?<![\w+#]){pattern}(?![\w+#])", text, re.I)
                if match:
                    getattr(result, category).append(
                        ExtractedSkill(
                            name=" ".join(match[0].split()),
                            category=category,
                            source_text=match[0],
                            confidence=0.95,
                        )
                    )
                    known.add(skill.casefold())
        # Wrapped bullet text is one item; explanatory parentheses are not skills.
        section = re.sub(r"\([^)]*\)", "", explicit_section, flags=re.S)
        if "•" in section:
            section = section.replace("\n", " ")
        for item in re.split(r"[,;•\n]", section):
            item = item.strip()
            if ":" in item:
                item = item.split(":", 1)[1].strip()
            if item.casefold() in {"business & soft skills", "technical skills", "soft skills"}:
                continue
            if any(re.search(rf"(?<!\w){re.escape(k)}(?!\w)", item, re.I) for k in known):
                continue
            if item and len(item) <= 60 and item.casefold() not in known:
                result.other_skills.append(
                    ExtractedSkill(name=item, category="other_skills", source_text=item, confidence=0.7)
                )
                known.add(item.casefold())
        return result
