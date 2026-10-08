import re
from typing import Optional
from pydantic import BaseModel, Field


class RefinedSpec(BaseModel):
    objective: str = Field(description="Objetivo principal da tarefa")
    target_files: list[str] = Field(default_factory=list, description="Arquivos afetados")
    steps: list[str] = Field(default_factory=list, description="Passos atômicos de execução")
    acceptance_criteria: list[str] = Field(default_factory=list, description="Critérios de aceite e testes")


class PromptRefinerService:
    """
    Serviço de refinamento e lapidação de prompts.
    Converte ideias brutas em especificações técnicas atômicas e aplica context pruning
    para selecionar apenas os arquivos estritamente relevantes, economizando tokens.
    """

    def to_markdown(self, spec: RefinedSpec) -> str:
        files_str = "\n".join([f"- `{f}`" for f in spec.target_files]) if spec.target_files else "- A definir"
        steps_str = "\n".join([f"{i+1}. {s}" for i, s in enumerate(spec.steps)]) if spec.steps else "1. Implementar funcionalidade"
        criteria_str = "\n".join([f"- [ ] {c}" for c in spec.acceptance_criteria]) if spec.acceptance_criteria else "- [ ] Testes passando"

        return f"""## Objetivo
{spec.objective}

## Arquivos Alvo
{files_str}

## Passos de Execução
{steps_str}

## Critérios de Aceite
{criteria_str}
"""

    def refine(self, raw_prompt: str, available_files: Optional[list[str]] = None) -> RefinedSpec:
        files = available_files or []
        
        # 1. Extração de palavras-chave para Context Pruning
        keywords = re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", raw_prompt.lower())
        matched_files = []
        for f in files:
            f_lower = f.lower()
            if any(kw in f_lower for kw in keywords):
                matched_files.append(f)
                
        # Limita aos arquivos mais relevantes (máximo 4 para economia de tokens)
        if not matched_files and files:
            # Seleciona arquivos padrão caso nenhum case com as palavras
            matched_files = [f for f in files if "main" in f or "app" in f][:2]
        
        target_files = matched_files[:4]
        if not target_files:
            target_files = ["src/index.ts" if any(".ts" in x for x in files) else "app/main.py"]

        # 2. Construção estruturada do objetivo e passos
        objective = raw_prompt.strip()
        steps = [
            f"Analisar requisitos e contratos em {', '.join(target_files[:2])}",
            f"Implementar as alterações para: '{objective}'",
            "Executar suíte de testes unitários para validar a alteração"
        ]
        
        acceptance_criteria = [
            "Código implementado sem erros de compilação ou lint",
            "Cobertura de testes automatizados passando 100%",
            "Trabalho confinado na worktree isolada"
        ]

        return RefinedSpec(
            objective=objective,
            target_files=target_files,
            steps=steps,
            acceptance_criteria=acceptance_criteria
        )
