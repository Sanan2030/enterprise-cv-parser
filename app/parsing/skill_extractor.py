import re

from app.schemas.resume import ExtractedSkill, SkillsCategorized

SKILL_TAXONOMY = {
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
        "requirements analysis",
        "use cases",
        "lucidchart",
    ],
    "soft_skills": ["leadership", "communication", "problem solving", "teamwork", "critical thinking"],
}


class SkillExtractor:
    def extract_skills(self, text: str, explicit_section: str = "") -> SkillsCategorized:
        result = SkillsCategorized()
        known = set()
        for category, items in SKILL_TAXONOMY.items():
            for skill in items:
                match = re.search(rf"(?<![\w+#]){re.escape(skill)}(?![\w+#])", text, re.I)
                if match:
                    getattr(result, category).append(
                        ExtractedSkill(
                            name=match[0], category=category, source_text=match[0], confidence=0.95
                        )
                    )
                    known.add(skill.casefold())
        for item in re.split(r"[,;•\n]", explicit_section):
            item = item.strip()
            if item and len(item) <= 60 and item.casefold() not in known:
                result.other_skills.append(
                    ExtractedSkill(name=item, category="other_skills", source_text=item, confidence=0.7)
                )
                known.add(item.casefold())
        return result
