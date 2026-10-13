"""
Serviço de Decisão e Roteamento Jev (System 1 Decision Engine).
Inspirado e integrado com a arquitetura do Jev (TypeSafe AI): executa classificação rápida,
roteamento de modelos e guardrails de conformidade sem geração de texto aberta,
economizando de 2.000 a 10.000 tokens por tarefa.
"""
import re
import logging
from typing import List, Dict, Any, Optional
import httpx
from pydantic import BaseModel
from app.core.config import settings

logger = logging.getLogger(__name__)


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
    Avalia intenções, escopos e diffs determinísticos com zero output token overhead,
    integrando diretamente com a API da TypeSafe AI quando configurada.
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

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 10.0
    ):
        self.api_key = api_key if api_key is not None else settings.JEV_API_KEY
        self.endpoint = endpoint or settings.JEV_ENDPOINT
        self.model = model or settings.JEV_MODEL
        self.timeout = timeout

    def triage(self, prompt: str, context: Optional[str] = None) -> TriageResult:
        """
        Classifica a intenção do prompt (Route-First) para direcionar
        ao modelo ótimo (flash vs pro) economizando tokens.
        Tenta a API oficial do Jev (TypeSafe AI) se configurada; caso contrário,
        utiliza o motor heurístico local.
        """
        if self.api_key:
            try:
                return self._remote_triage(prompt, context)
            except Exception as e:
                logger.warning(f"JEV API remota indisponivel ({e}). Aplicando fallback heuristico local.")

        return self._heuristic_triage(prompt, context)

    def _remote_triage(self, prompt: str, context: Optional[str] = None) -> TriageResult:
        state_content = f"Task Prompt: {prompt}"
        if context:
            state_content += f"\nContext: {context}"

        payload = {
            "model": self.model,
            "state": state_content,
            "questions": {
                "is_complex": {
                    "type": "noul",
                    "instructions": "Is this task complex, architectural, multi-module, or high-effort?"
                },
                "task_type": {
                    "type": "choice",
                    "instructions": "Categorize the software engineering task",
                    "criteria": {
                        "FEATURE": "Adding new functionality or feature",
                        "BUGFIX": "Fixing a bug, error or regression",
                        "REFACTOR": "Refactoring code or restructuring architecture",
                        "EXPLORATION": "Reading code, asking questions, or exploring files"
                    }
                },
                "complexity_level": {
                    "type": "score",
                    "instructions": "Rate the complexity level of the task",
                    "criteria": ["Trivial", "Medium", "High"]
                }
            }
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(self.endpoint, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        answers = data.get("answers", {})
        task_choice = answers.get("task_type", {}).get("choice", "FEATURE")
        task_conf = answers.get("task_type", {}).get("confidence", 0.9)

        # score 0 (Trivial), 1 (Medium), 2 (High) -> normaliza para 0.0 - 1.0
        raw_score = answers.get("complexity_level", {}).get("score", 1.0)
        norm_score = min(max(raw_score / 2.0, 0.0), 1.0)
        is_complex_prob = answers.get("is_complex", {}).get("noul", 0.5)

        if norm_score >= 0.6 or is_complex_prob >= 0.65 or task_choice == "REFACTOR":
            recommended_model = "pro"
            tokens_saved = 0
            reason = f"Classificado via Jev System 1 ({data.get('model', 'jev')}): Tarefa complexa. Roteamento para modelo Pro."
        elif task_choice == "EXPLORATION" or norm_score <= 0.3:
            recommended_model = "flash"
            tokens_saved = 3500
            reason = f"Classificado via Jev System 1 ({data.get('model', 'jev')}): Consulta/tarefa leve. Roteamento para Flash."
        else:
            recommended_model = "flash"
            tokens_saved = 2500
            reason = f"Classificado via Jev System 1 ({data.get('model', 'jev')}): Tarefa de escopo moderado. Roteamento para Flash."

        return TriageResult(
            task_type=task_choice,
            complexity_score=round(norm_score, 2),
            recommended_model=recommended_model,
            estimated_tokens_saved=tokens_saved,
            confidence=round(task_conf, 2),
            reasoning=reason
        )

    def _heuristic_triage(self, prompt: str, context: Optional[str] = None) -> TriageResult:
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
            reason = "Tarefa arquitetural/complexa identificada. Requer raciocinio profundo (Pro)."
        elif is_trivial and not is_complex:
            task_type = "EXPLORATION"
            complexity = 0.2
            model = "flash"
            tokens_saved = 3500
            conf = 0.95
            reason = "Consulta ou tarefa leve. Roteamento para modelo rapido e economico (Flash)."
        else:
            # Caso padrão: tarefas de porte médio
            task_type = "BUGFIX" if "erro" in texto or "bug" in texto or "corr" in texto else "FEATURE"
            complexity = 0.4
            model = "flash"
            tokens_saved = 2500
            conf = 0.85
            reason = "Tarefa atomica/padrao. Atendida com excelencia pelo Flash."

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
                    "description": "Possivel vazamento de segredo ou chave privada no diff adicionado."
                })

        passed = len(violations) == 0
        return GuardrailResult(
            passed=passed,
            violations=violations,
            confidence=0.99
        )


jev_service = JevService()
