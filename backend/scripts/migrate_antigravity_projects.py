import os
import sqlite3
import shutil
import datetime

def migrate():
    db_path = os.path.expanduser("~/.gemini/antigravity/conversation_summaries.db")
    if not os.path.exists(db_path):
        print(f"Banco {db_path} não encontrado.")
        return

    # Backup de segurança
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.bak_{timestamp}"
    shutil.copy2(db_path, backup_path)
    print(f"Backup criado em: {backup_path}")

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    patrimonio_workspace = '["file:///d%3A/Projetos/Patrimonio"]'
    patrimonio_project_id = "ac18ca3d-99c4-48fe-a717-6a80f9bafd86"

    sigma_workspace = '["file:///d%3A/Projetos/SIGMA"]'
    sigma_project_id = "9480da3d-dba1-4c26-bc92-c1e5e0d52a5b"

    # Conversas conhecidas de Patrimonio a migrar
    patrimonio_titles = [
        "Patrimonio - Ajuste de Tela",
        "Patrimonio - Inventario ADM",
        "Erro No Inventario Concluido",
        "Patrimonio - Lançamento de bens não encontrados ",
        "Patrimonio - Lanamento de bens no encontrados ",
        "Patrimonio - Exportação",
        "Patrimonio - Exportao",
        "Ajustes E Reordenação De Botões",
        "Ajustes E Reordenao De Botes",
        "Ajustes no Lançamento de Não Inventariados",
        "Ajustes no Lanamento de No Inventariados",
        "Simplificação de Inventário de Remanejamento",
        "Simplificao de Inventrio de Remanejamento",
        "Grid De Bens Do Inventário",
        "Grid De Bens Do Inventrio",
        "Impacto De Ajustes No Inventário",
        "Impacto De Ajustes No Inventrio"
    ]

    migrated_patrimonio = 0
    for title in patrimonio_titles:
        c.execute("""
            UPDATE conversation_summaries
            SET workspace_uris = ?, project_id = ?
            WHERE (title = ? OR preview = ?)
              AND (project_id != ? OR workspace_uris != ?)
        """, (patrimonio_workspace, patrimonio_project_id, title, title, patrimonio_project_id, patrimonio_workspace))
        migrated_patrimonio += c.rowcount

    # Sigma
    c.execute("""
        UPDATE conversation_summaries
        SET workspace_uris = ?, project_id = ?
        WHERE (title LIKE '%Sigma%' OR preview LIKE '%Sigma%')
          AND (project_id != ? OR workspace_uris != ?)
    """, (sigma_workspace, sigma_project_id, sigma_project_id, sigma_workspace))
    migrated_sigma = c.rowcount

    conn.commit()
    conn.close()

    print(f"Migração concluída com sucesso:")
    print(f"- Conversas migradas para Patrimonio: {migrated_patrimonio}")
    print(f"- Conversas migradas para SIGMA: {migrated_sigma}")

if __name__ == "__main__":
    migrate()
