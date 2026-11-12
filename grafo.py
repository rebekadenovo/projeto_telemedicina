"""Grafo clínico no Neo4j: consultas Cypher e a tela de Mapeamento Clínico.

O grafo guarda só identificadores e nomes. O cadastro completo continua no MongoDB,
e paciente_id é a mesma chave nos dois bancos.
"""
import os

import streamlit as st
from neo4j import GraphDatabase, RoutingControl
from neo4j.exceptions import DriverError, Neo4jError

# ---------------------------------------------------------------------------
# Consultas Cypher (sempre com parâmetros $...)
# ---------------------------------------------------------------------------
SUBGRAFO_PACIENTE = """
MATCH (p:Paciente {paciente_id: $paciente_id})
OPTIONAL MATCH c0 = (p)-[:POSSUI]->(:Prontuario)
OPTIONAL MATCH c1 = (p)-[:POSSUI]->(:Prontuario)-[:CONTEM_DIAGNOSTICO|REGISTRA_MEDICAMENTO]->()
OPTIONAL MATCH c2 = (:Medico)-[:ATENDEU]->(p)
OPTIONAL MATCH c3 = (p)-[:POSSUI]->(pr:Prontuario)-[r1:REGISTRA_MEDICAMENTO]->(:Medicamento)
                    -[:INTERAGE_COM]-(:Medicamento)<-[r2:REGISTRA_MEDICAMENTO]-(pr)
WHERE r1.em_uso AND r2.em_uso
OPTIONAL MATCH c4 = (p)-[:POSSUI]->(:Prontuario)-[:CONTEM_DIAGNOSTICO]->(:Diagnostico)
                    -[:CORRELACIONADO_COM]-(:Diagnostico)
WITH collect(c0) + collect(c1) + collect(c2) + collect(c3) + collect(c4) AS caminhos
UNWIND caminhos AS caminho
UNWIND relationships(caminho) AS r
WITH DISTINCT r, startNode(r) AS a, endNode(r) AS b
RETURN labels(a)[0] AS origem_tipo,
       coalesce(a.paciente_id, a.prontuario_id, a.profissional_id, a.cid, a.codigo) AS origem_chave,
       coalesce(a.nome, a.prontuario_id) AS origem_nome,
       type(r) AS relacao, r.em_uso AS em_uso,
       labels(b)[0] AS destino_tipo,
       coalesce(b.paciente_id, b.prontuario_id, b.profissional_id, b.cid, b.codigo) AS destino_chave,
       coalesce(b.nome, b.prontuario_id) AS destino_nome
"""

SUBGRAFO_MEDICO = """
MATCH (m:Medico {profissional_id: $profissional_id})
OPTIONAL MATCH c1 = (m)-[:ATENDEU]->(:Paciente)-[:POSSUI]->(:Prontuario)
OPTIONAL MATCH c2 = (m)-[reg:REGISTRA]->(pr:Prontuario)-[cd:CONTEM_DIAGNOSTICO]->(:Diagnostico)
WHERE cd.atendimento_id = reg.atendimento_id
WITH collect(c1) + collect(c2) AS caminhos
UNWIND caminhos AS caminho
UNWIND relationships(caminho) AS r
WITH DISTINCT r, startNode(r) AS a, endNode(r) AS b
RETURN labels(a)[0] AS origem_tipo,
       coalesce(a.paciente_id, a.prontuario_id, a.profissional_id, a.cid, a.codigo) AS origem_chave,
       coalesce(a.nome, a.prontuario_id) AS origem_nome,
       type(r) AS relacao, null AS em_uso,
       labels(b)[0] AS destino_tipo,
       coalesce(b.paciente_id, b.prontuario_id, b.profissional_id, b.cid, b.codigo) AS destino_chave,
       coalesce(b.nome, b.prontuario_id) AS destino_nome
"""

DIAGNOSTICOS_PACIENTE = """
MATCH (:Paciente {paciente_id: $paciente_id})-[:POSSUI]->(pr:Prontuario)-[cd:CONTEM_DIAGNOSTICO]->(d:Diagnostico)
OPTIONAL MATCH (m:Medico)-[:REGISTRA {atendimento_id: cd.atendimento_id}]->(pr)
RETURN cd.data AS data, d.cid AS cid, d.nome AS diagnostico, m.nome AS profissional
ORDER BY data DESC
"""

MEDICAMENTOS_PACIENTE = """
MATCH (:Paciente {paciente_id: $paciente_id})-[:POSSUI]->(pr:Prontuario)-[rm:REGISTRA_MEDICAMENTO]->(md:Medicamento)
OPTIONAL MATCH (m:Medico)-[:REGISTRA {atendimento_id: rm.atendimento_id}]->(pr)
RETURN rm.data AS data, md.codigo AS codigo, md.nome AS medicamento, rm.posologia AS posologia,
       rm.em_uso AS em_uso, m.nome AS profissional
ORDER BY data DESC
"""

# Diagnósticos ligados aos do paciente em até 3 saltos, com o caminho mais curto.
DIAGNOSTICOS_RELACIONADOS = """
MATCH (:Paciente {paciente_id: $paciente_id})-[:POSSUI]->(:Prontuario)-[:CONTEM_DIAGNOSTICO]->(d:Diagnostico)
MATCH caminho = (d)-[:CORRELACIONADO_COM*1..3]-(relacionado:Diagnostico)
WHERE NOT EXISTS {
  MATCH (:Paciente {paciente_id: $paciente_id})-[:POSSUI]->(:Prontuario)
        -[:CONTEM_DIAGNOSTICO]->(relacionado)
}
WITH relacionado, caminho ORDER BY length(caminho)
WITH relacionado, collect(caminho)[0] AS menor
RETURN relacionado.cid AS cid, relacionado.nome AS diagnostico, length(menor) AS distancia,
       [n IN nodes(menor) | n.nome] AS caminho,
       [r IN relationships(menor) | r.tipo] AS tipos
ORDER BY distancia, diagnostico
"""

MEDICAMENTOS_EM_USO = """
MATCH (:Paciente {paciente_id: $paciente_id})-[:POSSUI]->(:Prontuario)-[rm:REGISTRA_MEDICAMENTO]->(md:Medicamento)
WHERE rm.em_uso = true
RETURN DISTINCT md.codigo AS codigo
"""

# a.codigo < b.codigo evita devolver o mesmo par duas vezes (A-B e B-A).
INTERACOES_ENTRE = """
MATCH (a:Medicamento)-[r:INTERAGE_COM]-(b:Medicamento)
WHERE a.codigo IN $codigos AND b.codigo IN $codigos AND a.codigo < b.codigo
RETURN a.codigo AS codigo_a, a.nome AS medicamento_a, b.codigo AS codigo_b, b.nome AS medicamento_b,
       r.gravidade AS gravidade, r.motivo AS motivo
"""

CONTRAINDICACOES = """
MATCH (:Paciente {paciente_id: $paciente_id})-[:POSSUI]->(:Prontuario)-[:CONTEM_DIAGNOSTICO]->(d:Diagnostico)
MATCH (md:Medicamento)-[c:CONTRAINDICADO_EM]->(d)
WHERE md.codigo IN $codigos
RETURN DISTINCT md.codigo AS codigo, md.nome AS medicamento, d.nome AS diagnostico, c.motivo AS motivo
"""

PACIENTES_EM_RISCO = """
MATCH (p:Paciente)-[:POSSUI]->(pr:Prontuario)
MATCH (pr)-[r1:REGISTRA_MEDICAMENTO]->(a:Medicamento)-[i:INTERAGE_COM]-(b:Medicamento)
      <-[r2:REGISTRA_MEDICAMENTO]-(pr)
WHERE r1.em_uso AND r2.em_uso AND a.codigo < b.codigo
RETURN p.paciente_id AS paciente_id, p.nome AS paciente, a.nome AS medicamento_a,
       b.nome AS medicamento_b, i.gravidade AS gravidade, i.motivo AS motivo
ORDER BY CASE i.gravidade WHEN 'grave' THEN 0 WHEN 'moderada' THEN 1 ELSE 2 END, paciente
"""

PACIENTES_DO_MEDICO = """
MATCH (m:Medico {profissional_id: $profissional_id})-[a:ATENDEU]->(p:Paciente)
RETURN p.paciente_id AS paciente_id, p.nome AS paciente, a.total AS consultas,
       a.ultima_vez AS ultima_consulta
ORDER BY ultima_consulta DESC
"""

LISTAR_MEDICOS = """
MATCH (m:Medico) RETURN m.profissional_id AS profissional_id, m.nome AS nome ORDER BY nome
"""

LISTAR_MEDICAMENTOS = """
MATCH (m:Medicamento) RETURN m.codigo AS codigo, m.nome AS nome ORDER BY nome
"""

LISTAR_DIAGNOSTICOS = """
MATCH (d:Diagnostico) RETURN d.cid AS cid, d.nome AS nome ORDER BY nome
"""

# Usada pela finalização da consulta para gravar um atendimento novo no grafo.
# MERGE + atendimento_id torna a gravação idempotente: repetir não duplica nada.
REGISTRAR_ATENDIMENTO = """
MATCH (m:Medico {profissional_id: $profissional_id})
MERGE (p:Paciente {paciente_id: $paciente_id})
  ON CREATE SET p.nome = $paciente_nome
MERGE (pr:Prontuario {prontuario_id: 'PRT-' + $paciente_id})
MERGE (p)-[:POSSUI]->(pr)
MERGE (m)-[a:ATENDEU]->(p)
  ON CREATE SET a.total = 0, a.atendimentos = []
FOREACH (_ IN CASE WHEN $atendimento_id IN a.atendimentos THEN [] ELSE [1] END |
  SET a.total = a.total + 1, a.atendimentos = a.atendimentos + $atendimento_id)
SET a.ultima_vez = $data
MERGE (m)-[reg:REGISTRA {atendimento_id: $atendimento_id}]->(pr)
SET reg.data = $data
FOREACH (cid IN $cids |
  MERGE (d:Diagnostico {cid: cid})
  MERGE (pr)-[cd:CONTEM_DIAGNOSTICO {atendimento_id: $atendimento_id}]->(d)
  SET cd.data = $data)
FOREACH (item IN $medicamentos |
  MERGE (md:Medicamento {codigo: item.codigo})
  MERGE (pr)-[rm:REGISTRA_MEDICAMENTO {atendimento_id: $atendimento_id}]->(md)
  SET rm.data = $data, rm.posologia = item.posologia, rm.em_uso = item.em_uso)
"""

ORDEM_GRAVIDADE = {"grave": 0, "moderada": 1, "leve": 2}


# ---------------------------------------------------------------------------
# Conexão e funções reutilizáveis (também servem para a finalização da consulta)
# ---------------------------------------------------------------------------
@st.cache_resource
def conectar_neo4j(uri, usuario, senha):
    return GraphDatabase.driver(uri, auth=(usuario, senha), connection_timeout=10)


def banco_neo4j():
    return os.getenv("NEO4J_DATABASE") or None


def consultar(driver, consulta, **parametros):
    registros, _, _ = driver.execute_query(
        consulta, parametros, database_=banco_neo4j(), routing_=RoutingControl.READ
    )
    return [registro.data() for registro in registros]


def verificar_prescricao(driver, paciente_id, codigos_novos):
    """Alertas para uma prescrição: interações com os remédios em uso e entre os novos,
    e contraindicações com os diagnósticos do paciente. Grave aparece primeiro."""
    em_uso = [r["codigo"] for r in consultar(driver, MEDICAMENTOS_EM_USO, paciente_id=paciente_id)]
    todos = sorted(set(em_uso) | set(codigos_novos))
    novos = set(codigos_novos)

    alertas = []
    for i in consultar(driver, INTERACOES_ENTRE, codigos=todos):
        alertas.append({
            "tipo": "Interação",
            "gravidade": i["gravidade"],
            "descricao": f"{i['medicamento_a']} + {i['medicamento_b']}: {i['motivo']}",
            "codigos": [i["codigo_a"], i["codigo_b"]],
            "nova": bool(novos & {i["codigo_a"], i["codigo_b"]}),
        })
    if codigos_novos:
        for c in consultar(driver, CONTRAINDICACOES, paciente_id=paciente_id, codigos=codigos_novos):
            alertas.append({
                "tipo": "Contraindicação",
                "gravidade": "grave",
                "descricao": f"{c['medicamento']} em paciente com {c['diagnostico']}: {c['motivo']}",
                "codigos": [c["codigo"]],
                "nova": True,
            })
    return sorted(alertas, key=lambda a: ORDEM_GRAVIDADE.get(a["gravidade"], 9))


def registrar_atendimento(driver, paciente_id, paciente_nome, profissional_id, atendimento_id,
                          data, cids, medicamentos):
    """Grava um atendimento finalizado no grafo, numa única transação.

    medicamentos: lista de {"codigo": ..., "posologia": ..., "em_uso": True/False}
    """
    driver.execute_query(
        REGISTRAR_ATENDIMENTO,
        {"paciente_id": paciente_id, "paciente_nome": paciente_nome,
         "profissional_id": profissional_id, "atendimento_id": atendimento_id,
         "data": data, "cids": cids, "medicamentos": medicamentos},
        database_=banco_neo4j(),
    )


# ---------------------------------------------------------------------------
# Desenho do grafo (Graphviz já vem com o Streamlit, sem dependência extra)
# ---------------------------------------------------------------------------
CORES = {
    "Paciente": "#2F80C0",
    "Prontuario": "#6F8790",
    "Medico": "#17665F",
    "Diagnostico": "#C2504A",
    "Medicamento": "#D98A2B",
}
RELACOES_SEM_SETA = {"INTERAGE_COM", "CORRELACIONADO_COM"}


def _texto(valor):
    return str(valor).replace("\\", "\\\\").replace('"', '\\"')


def montar_dot(arestas, simulados=None, alertas=None):
    """Monta o texto DOT. simulados = {codigo: nome} de remédios da simulação."""
    linhas = [
        "graph G {",
        'bgcolor="transparent"; rankdir=LR; pad=0.3; nodesep=0.35; ranksep=0.9;',
        'node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11, '
        'fontcolor="white", color="transparent", margin="0.18,0.08"];',
        'edge [fontname="Helvetica", fontsize=8, color="#8A9BA0", fontcolor="#8A9BA0"];',
    ]
    vistos, ligacoes = set(), set()

    def no(tipo, chave, nome, extra=""):
        ident = f"{tipo}:{chave}"
        if ident not in vistos:
            vistos.add(ident)
            linhas.append(f'"{_texto(ident)}" [label="{_texto(nome)}", '
                          f'fillcolor="{CORES.get(tipo, "#888888")}"{extra}];')
        return ident

    for a in arestas:
        extra = ""
        if a["destino_tipo"] == "Medicamento" and a.get("em_uso") is False:
            extra = ', fillcolor="#A9B4B7"'  # remédio que não está mais em uso
        origem = no(a["origem_tipo"], a["origem_chave"], a["origem_nome"])
        destino = no(a["destino_tipo"], a["destino_chave"], a["destino_nome"], extra)
        chave = (origem, a["relacao"], destino)
        if chave in ligacoes:
            continue  # mesmo diagnóstico em duas consultas: desenha uma vez só
        ligacoes.add(chave)
        estilo = 'color="#D64541", fontcolor="#D64541", penwidth=2' \
            if a["relacao"] == "INTERAGE_COM" else ""
        seta = "dir=none" if a["relacao"] in RELACOES_SEM_SETA else "dir=forward"
        linhas.append(f'"{_texto(origem)}" -- "{_texto(destino)}" '
                      f'[label="{a["relacao"]}", {seta}{", " + estilo if estilo else ""}];')

    for codigo, nome in (simulados or {}).items():
        no("Medicamento", codigo, f"{nome} (simulado)", ', style="rounded,filled,dashed", '
           'color="#D98A2B", fillcolor="#D98A2B55", fontcolor="#D98A2B"')
    for alerta in alertas or []:
        if alerta["tipo"] == "Interação" and alerta["nova"]:
            a, b = (f"Medicamento:{c}" for c in alerta["codigos"])
            if a in vistos and b in vistos:
                linhas.append(f'"{_texto(a)}" -- "{_texto(b)}" [label="INTERAGE_COM", '
                              'style=dashed, color="#D64541", fontcolor="#D64541", penwidth=2];')
    linhas.append("}")
    return "\n".join(linhas)


def mostrar_legenda():
    st.markdown(" ".join(
        f'<span style="color:{cor}; font-size:1.1rem">■</span> {tipo}&nbsp;&nbsp;'
        for tipo, cor in CORES.items()
    ) + '<span style="color:#D64541; font-size:1.1rem">━</span> Interação', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Tela
# ---------------------------------------------------------------------------
def mostrar_alerta(alerta):
    texto = f"**{alerta['tipo']} {alerta['gravidade']}** · {alerta['descricao']}"
    if alerta["gravidade"] == "grave":
        st.error(texto, icon="🚨")
    elif alerta["gravidade"] == "moderada":
        st.warning(texto, icon="⚠️")
    else:
        st.info(texto, icon="ℹ️")


def mostrar_grafo(cadastros):
    uri = os.getenv("NEO4J_URI")
    usuario = os.getenv("NEO4J_USERNAME")
    senha = os.getenv("NEO4J_PASSWORD")
    if not (uri and usuario and senha):
        st.info("Preencha NEO4J_URI, NEO4J_USERNAME e NEO4J_PASSWORD no arquivo .env do projeto.")
        return

    try:
        driver = conectar_neo4j(uri, usuario, senha)
        medicos = consultar(driver, LISTAR_MEDICOS)
        catalogo = consultar(driver, LISTAR_MEDICAMENTOS)
    except (DriverError, Neo4jError, ValueError):
        st.error("Não foi possível acessar o Neo4j. Confira as variáveis NEO4J_* e a conexão.")
        return

    if not catalogo:
        st.info("O grafo está vazio. Execute carregar_neo4j.py.")
        return

    modo = st.segmented_control("Pesquisar por", ["Paciente", "Profissional"], default="Paciente")
    try:
        if modo == "Profissional":
            mostrar_profissional(driver, medicos)
        else:
            mostrar_paciente(driver, cadastros, catalogo)
    except (DriverError, Neo4jError):
        st.error("Falha ao consultar o Neo4j. Tente novamente em alguns segundos.")


def mostrar_paciente(driver, cadastros, catalogo):
    paciente_id = st.selectbox(
        "Paciente",
        options=list(cadastros),
        format_func=lambda codigo: f"{cadastros[codigo].get('nome', codigo)} · {codigo}",
        index=None,
        placeholder="Selecione um paciente",
        key="grafo_paciente",
    )
    if not paciente_id:
        risco = consultar(driver, PACIENTES_EM_RISCO)
        with st.container(border=True):
            st.subheader("Pacientes com interação entre remédios em uso")
            if risco:
                st.table([{
                    "Paciente": r["paciente"], "Medicamentos": f"{r['medicamento_a']} + {r['medicamento_b']}",
                    "Gravidade": r["gravidade"], "Motivo": r["motivo"],
                } for r in risco])
            else:
                st.info("Nenhum paciente com interação entre remédios em uso.")
        return

    nomes = {m["codigo"]: m["nome"] for m in catalogo}
    diagnosticos = consultar(driver, DIAGNOSTICOS_PACIENTE, paciente_id=paciente_id)
    medicamentos = consultar(driver, MEDICAMENTOS_PACIENTE, paciente_id=paciente_id)
    relacionados = consultar(driver, DIAGNOSTICOS_RELACIONADOS, paciente_id=paciente_id)
    alertas_atuais = verificar_prescricao(driver, paciente_id, [])

    total_diag, total_uso, total_alertas = st.columns(3)
    total_diag.metric("Diagnósticos no grafo", len({d["cid"] for d in diagnosticos}))
    total_uso.metric("Remédios em uso", len({m["codigo"] for m in medicamentos if m["em_uso"]}))
    total_alertas.metric("Alertas atuais", len(alertas_atuais))

    grafo_painel, lado = st.columns([3, 2], gap="medium")

    with lado.container(border=True):
        st.subheader("Simular prescrição")
        simulados = st.multiselect(
            "Medicamentos que o médico pretende receitar",
            options=list(nomes),
            format_func=lambda codigo: nomes[codigo],
            placeholder="Escolha um ou mais",
            key=f"simulacao_{paciente_id}",
        )
        alertas = verificar_prescricao(driver, paciente_id, simulados)
        if simulados:
            novos = [a for a in alertas if a["nova"]]
            if novos:
                for alerta in novos:
                    mostrar_alerta(alerta)
            else:
                st.success("Nenhuma incompatibilidade cadastrada para essa prescrição.")
        st.caption("Alertas simulados com dados fictícios. Não use como referência clínica.")

        st.subheader("Alertas do tratamento atual")
        atuais = [a for a in alertas if not a["nova"]]
        if atuais:
            for alerta in atuais:
                mostrar_alerta(alerta)
        else:
            st.success("Os remédios em uso não têm interações cadastradas.")

    with grafo_painel.container(border=True):
        st.subheader("Mapa clínico")
        arestas = consultar(driver, SUBGRAFO_PACIENTE, paciente_id=paciente_id)
        if len(arestas) <= 1:
            st.info("Esse paciente ainda não tem atendimentos registrados no grafo.")
        mostrar_legenda()
        st.graphviz_chart(montar_dot(arestas, {c: nomes[c] for c in simulados}, alertas))

    relacionados_aba, remedios_aba, diagnosticos_aba, cypher_aba = st.tabs(
        ["Diagnósticos relacionados", "Histórico de medicamentos", "Diagnósticos registrados",
         "Consultas Cypher"])
    with relacionados_aba:
        if relacionados:
            st.caption("Diagnósticos ligados aos do paciente por CORRELACIONADO_COM, em até 3 passos.")
            st.table([{
                "Diagnóstico": f"{r['diagnostico']} ({r['cid']})",
                "Distância": r["distancia"],
                "Caminho no grafo": " → ".join(r["caminho"]),
                "Tipo de relação": " / ".join(r["tipos"]),
            } for r in relacionados])
        else:
            st.info("Nenhum diagnóstico relacionado.")
    with remedios_aba:
        if medicamentos:
            st.table([{
                "Data": m["data"], "Medicamento": m["medicamento"], "Posologia": m["posologia"],
                "Em uso": "Sim" if m["em_uso"] else "Não", "Profissional": m["profissional"] or "—",
            } for m in medicamentos])
        else:
            st.info("Nenhum medicamento registrado.")
    with diagnosticos_aba:
        if diagnosticos:
            st.table([{
                "Data": d["data"], "CID": d["cid"], "Diagnóstico": d["diagnostico"],
                "Profissional": d["profissional"] or "—",
            } for d in diagnosticos])
        else:
            st.info("Nenhum diagnóstico registrado no grafo.")
    with cypher_aba:
        st.caption("Interações entre os remédios em uso e os simulados")
        st.code(INTERACOES_ENTRE.strip(), language="cypher")
        st.caption("Diagnósticos relacionados em até 3 passos")
        st.code(DIAGNOSTICOS_RELACIONADOS.strip(), language="cypher")
        st.caption("Contraindicações com os diagnósticos do paciente")
        st.code(CONTRAINDICACOES.strip(), language="cypher")


def mostrar_profissional(driver, medicos):
    if not medicos:
        st.info("Nenhum profissional no grafo. Execute carregar_neo4j.py.")
        return
    nomes = {m["profissional_id"]: m["nome"] for m in medicos}
    profissional_id = st.selectbox(
        "Profissional",
        options=list(nomes),
        format_func=lambda codigo: f"{nomes[codigo]} · {codigo}",
        key="grafo_profissional",
    )
    pacientes = consultar(driver, PACIENTES_DO_MEDICO, profissional_id=profissional_id)
    grafo_painel, lado = st.columns([3, 2], gap="medium")
    with grafo_painel.container(border=True):
        st.subheader("Pacientes e diagnósticos registrados")
        mostrar_legenda()
        arestas = consultar(driver, SUBGRAFO_MEDICO, profissional_id=profissional_id)
        st.graphviz_chart(montar_dot(arestas))
    with lado.container(border=True):
        st.subheader("Pacientes atendidos")
        if pacientes:
            st.table([{
                "Paciente": p["paciente"], "Consultas": p["consultas"],
                "Última consulta": p["ultima_consulta"],
            } for p in pacientes])
        else:
            st.info("Nenhum atendimento registrado para esse profissional.")
