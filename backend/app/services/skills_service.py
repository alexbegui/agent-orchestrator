"""
Serviço de descoberta e catalogação de Skills do Antigravity / Superpowers.
Aplica o princípio de Progressive Disclosure: extrai apenas o sumário
(nome e descrição) das skills disponíveis, evitando inflar a janela de contexto.
O corpo da skill só é aberto pelo agente via ferramentas de leitura se necessário.
"""
import os
import re
from typing import List, Dict, Optional


class SkillsService:
    def __init__(self, custom_paths: Optional[List[str]] = None):
        self.custom_paths = custom_paths

    def _default_paths(self, project_root: Optional[str] = None) -> List[str]:
        if self.custom_paths is not None:
            return self.custom_paths

        paths = []
        if project_root:
            for sub in [".agents/skills", ".agent/skills", "skills"]:
                p = os.path.join(project_root, sub)
                if os.path.isdir(p):
                    paths.append(p)

        global_skills = os.path.expanduser("~/.gemini/config/skills")
        if os.path.isdir(global_skills):
            paths.append(global_skills)

        return paths

    @staticmethod
    def _parse_frontmatter(content: str) -> Dict[str, str]:
        """Extrai name e description do frontmatter YAML sem depender de pyyaml."""
        if not content.startswith("---"):
            return {}

        partes = content.split("---", 2)
        if len(partes) < 3:
            return {}

        front = partes[1]
        meta = {}
        
        name_match = re.search(r"^name:\s*['\"]?(.*?)['\"]?$", front, re.MULTILINE)
        if name_match:
            meta["name"] = name_match.group(1).strip()

        desc_match = re.search(r"^description:\s*>?-?\s*['\"]?(.*?)['\"]?$", front, re.MULTILINE)
        if desc_match:
            desc = desc_match.group(1).strip()
            # Se for descrição multi-linha (> ou >-), pega linhas subsequentes indentadas
            if not desc or desc in (">", ">-", "|"):
                linhas = []
                capturando = False
                for linha in front.splitlines():
                    if re.match(r"^description:", linha):
                        capturando = True
                        continue
                    if capturando:
                        if linha.startswith("  ") or linha.startswith("\t"):
                            linhas.append(linha.strip())
                        else:
                            break
                desc = " ".join(linhas).strip()
            meta["description"] = desc

        return meta

    def list_skills(self, project_root: Optional[str] = None) -> List[Dict[str, str]]:
        paths = self._default_paths(project_root)
        skills = {}

        for base_path in paths:
            if not os.path.isdir(base_path):
                continue
            for item in os.listdir(base_path):
                skill_dir = os.path.join(base_path, item)
                if not os.path.isdir(skill_dir):
                    continue
                skill_md = os.path.join(skill_dir, "SKILL.md")
                if os.path.isfile(skill_md):
                    try:
                        with open(skill_md, "r", encoding="utf-8") as f:
                            content = f.read(4096)
                        meta = self._parse_frontmatter(content)
                        nome = meta.get("name") or item
                        desc = meta.get("description") or "Sem descrição"
                        if nome not in skills:
                            skills[nome] = {
                                "name": nome,
                                "description": desc,
                                "path": skill_md
                            }
                    except OSError:
                        continue

        return sorted(skills.values(), key=lambda s: s["name"])

    def filter_skills_for_context(self, skills: List[Dict[str, str]], prompt_text: str = "") -> List[Dict[str, str]]:
        """
        Filtra skills para evitar inflar o prompt com ferramentas de domínio desconexo.
        Skills puramente visuais/mídia (slides, banners, brandkit) são omitidas quando a
        tarefa é de backend, infra ou testes, economizando milhares de tokens de contexto.
        """
        if not prompt_text:
            return skills

        texto = prompt_text.lower()
        palavras_visuais = {
            "ui", "ux", "frontend", "front-end", "design", "layout", "css", "html",
            "banner", "slide", "apresentacao", "apresentação", "estilo", "cor",
            "mockup", "figma", "tailwind", "react", "componente", "visual"
        }
        tem_interesse_visual = any(re.search(rf"\b{p}\b", texto) for p in palavras_visuais)

        skills_visuais = {
            "banner-design", "brand", "brandkit", "design", "design-system",
            "design-taste-frontend", "design-taste-frontend-v1", "gpt-taste",
            "high-end-visual-design", "imagegen-frontend-mobile", "imagegen-frontend-web",
            "industrial-brutalist-ui", "minimalist-ui", "slides", "stitch-design-taste"
        }

        if not tem_interesse_visual:
            return [s for s in skills if s["name"] not in skills_visuais]

        return skills

    def format_summary(self, skills: List[Dict[str, str]], prompt_text: Optional[str] = None) -> str:
        if not skills:
            return ""

        filtradas = self.filter_skills_for_context(skills, prompt_text or "")
        if not filtradas:
            return ""

        linhas = [
            "## Available Skills (Progressive Disclosure - Read via tool only if needed):"
        ]
        for s in filtradas:
            linhas.append(f"- **{s['name']}**: {s['description']}")
        return "\n".join(linhas)


skills_service = SkillsService()

