"""
Serviço de Decisão e Roteamento Jev (System 1 Decision Engine).
Inspirado na arquitetura do Jev (TypeSafe AI): executa classificação rápida,
roteamento de modelos e guardrails de conformidade sem geração de texto aberta,
economizando de 2.000 a 10.000 tokens por tarefa.
"""
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel


class TriageResult(BaseModel):
    task_type: str
    complexity_score: float
    recommended_model: str
    estimated_tokens_saved: int
    confidence: float
    reasoning: str


class GuardrailResult(BaseModel):
    passed: bool
    violations: List[Dict[str, Any]]
    confidence: float


class JevService:
    """
    Camada de decisão de alta velocidade (System 1).
    Avalia intenções, escopos e diffs determinísticos com zero output token overhead.
    """

    COMPLEXITY_TRIGGERS = [
        r"\brefator", r"\bmigra", r"\barquitet", r"\bmulti", r"\bseguran",
        r"\bperformance", r"\bconcorr", r"\bnovo m[oó]dulo", r"\bcompleto",
        r"\breescrev", r"\bintegra[çc]"
    ]

    TRIVIAL_TRIGGERS = [
        r"\bonde fica\b", r"\bcomo rodo\b", r"\bqual [eé]\b", r"\blistar\b",
        r"\bmostrar\b", r"\bver\b", r"\bprocurar\b", r"\bexplicar\b", r"\bstatus\b",
        r"\bporta\b", r"\bconfigura[çc][aã]o\b"
    ]

    def __init__(self, api_key: Optional[str] = None, endpoint: Optional[str] = None):
        self.api_key = api_key
        self.endpoint = endpoint

    def triage(self, prompt: str, context: Optional[str] = None) -> TriageResult:
        """
        Classifica a intenção do prompt (Route-First) para direcionar
        ao modelo ótimo (flash vs pro) economizando tokens.
        """
        texto = prompt.lower()

        # Heurística rápida System 1
        is_complex = any(re.search(pat, texto) for pat in self.COMPLEXITY_TRIGGERS)
        is_trivial = any(re.search(pat, texto) for pat in self.TRIVIAL_TRIGGERS)

        if is_complex and not is_trivial:
            task_type = "FEATURE" if "novo" in texto or "criar" in texto else "REFACTOR"
            complexity = 0.85
            model = "pro"
            tokens_saved = 0
            conf = 0.92
            reason = "Tarefa arquitetural/complexa identificada. Requer raciocínio profundo (Pro)."
        elif is_trivial and not is_complex:
            task_type = "EXPLORATION"
            complexity = 0.2
            model = "flash"
            tokens_saved = 3500
            conf = 0.95
            reason = "Consulta ou tarefa leve. Roteamento para modelo rápido e econômico (Flash)."
        else:
            # Caso padrão: tarefas de porte médio
            task_type = "BUGFIX" if "erro" in texto or "bug" in texto or "corr" in texto else "FEATURE"
            complexity = 0.4
            model = "flash"
            tokens_saved = 2500
            conf = 0.85
            reason = "Tarefa atômica/padrão. Atendida com excelência pelo Flash."

        return TriageResult(
            task_type=task_type,
            complexity_score=complexity,
            recommended_model=model,
            estimated_tokens_saved=tokens_saved,
            confidence=conf,
            reasoning=reason
        )

    def verify_diff(self, diff: str, rules: Optional[List[str]] = None) -> GuardrailResult:
        """
        Avalia o diff gerado contra guardrails de conformidade do projeto
        (Verify-After) sem pagar o imposto de tokens de um LLM.
        """
        active_rules = rules or ["no_prisma_migrate_dev", "check_sensitive_keys"]
        violations = []

        if "no_prisma_migrate_dev" in active_rules:
            # Detecta adições de prisma migrate dev (proibido no SIGMA)
            if re.search(r"^\s*\+.*prisma\s+migrate\s+dev", diff, re.MULTILINE | re.IGNORECASE):
                violations.append({
                    "rule": "no_prisma_migrate_dev",
                    "severity": "CRITICAL",
                    "description": "Uso de 'prisma migrate dev' detectado no diff. No SIGMA deve-se usar nova-migration.mjs."
                })

        if "check_sensitive_keys" in active_rules:
            if re.search(r"^\s*\+.*(api_key|secret_key|private_key)\s*[:=]\s*['\"][A-Za-z0-9_-]{16,}['\"]", diff, re.MULTILINE | re.IGNORECASE):
                violations.append({
                    "rule": "check_sensitive_keys",
                    "severity": "CRITICAL",
                    "description": "Possível vazamento de segredo ou chave privada no diff adicionado."
                })

        passed = len(violations) == 0
        return GuardrailResult(
            passed=passed,
            violations=violations,
            confidence=0.99
        )


jev_service = JevService()
