"""
Gerador de texto formatado para envio à equipe via WhatsApp,
a partir dos agendamentos de um dia ou período.
"""
from datetime import datetime


def _formatar_data_br(data_iso: str) -> str:
    try:
        return datetime.strptime(data_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return data_iso


def gerar_texto_whatsapp(agendamentos: list, titulo: str = None) -> str:
    """
    agendamentos: lista de dicts vindos de AgendaDAO.listar_por_periodo(),
    já ordenados por data / ordem_atendimento / hora.
    """
    if not agendamentos:
        return "Nenhum atendimento agendado para o período selecionado."

    linhas = []
    cabecalho = titulo or "📋 *Roteiro de Atendimentos*"
    linhas.append(cabecalho)
    linhas.append("")

    dia_atual = None
    for ag in agendamentos:
        if ag["data"] != dia_atual:
            dia_atual = ag["data"]
            linhas.append(f"🗓️ *{_formatar_data_br(dia_atual)}*")

        linhas.append(f"—")
        linhas.append(f"🔢 Ordem: {ag.get('ordem_atendimento', 1)}")
        linhas.append(f"👤 Cliente: {ag['cliente_nome']}")
        if ag.get("hora"):
            linhas.append(f"⏰ Horário: {ag['hora']}")
        if ag.get("endereco"):
            linhas.append(f"📍 Endereço: {ag['endereco']}")
        if ag.get("google_maps_link"):
            linhas.append(f"🗺️ Mapa: {ag['google_maps_link']}")
        if ag.get("observacoes"):
            linhas.append(f"📝 Obs: {ag['observacoes']}")
        linhas.append("")

    return "\n".join(linhas).strip()
