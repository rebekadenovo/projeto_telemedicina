"""Finalização da consulta: fecha o ciclo do atendimento nos três bancos.

Ordem das gravações ao finalizar:
1. MongoDB: consulta, receita em PDF, diagnósticos no prontuário e status do agendamento.
2. Neo4j: atendimento, diagnósticos e medicamentos no grafo clínico.
3. Redis: encerra a sessão, registra o paciente entre os atendidos do dia e limpa o cache da agenda.

O atendimento_id sai do token da sessão aberta na recepção. Por isso, se uma etapa falhar,
o botão pode ser clicado de novo: o MongoDB e o Neo4j não duplicam nada e a sessão só
é encerrada no fim, depois que os outros dois bancos gravaram.
"""
import os
from datetime import date, datetime, timezone
from time import time

import streamlit as st
from neo4j.exceptions import DriverError, Neo4jError
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

from grafo import (LISTAR_DIAGNOSTICOS, LISTAR_MEDICAMENTOS, LISTAR_MEDICOS, consultar, conectar_neo4j,
                   mostrar_alerta, registrar_atendimento, verificar_prescricao)
from recepcao import chave_sessao, conectar_redis

PREFIXO_SESSAO = chave_sessao("")
DOIS_DIAS = 2 * 24 * 60 * 60


def chave_atendidos(dia):
    return f"telemedicina:recepcao:atendidos:{dia}"


def chave_agenda(dia):
    return f"telemedicina:recepcao:agenda:{dia}"


def sessoes_ativas(redis):
    """Pacientes com atendimento iniciado na recepção: {paciente_id: token}."""
    ativos = {}
    for chave in redis.scan_iter(match=f"{PREFIXO_SESSAO}*"):
        token = redis.get(chave)
        if token:
            ativos[chave.removeprefix(PREFIXO_SESSAO)] = token
    return ativos


# ---------------------------------------------------------------------------
# Receita em PDF (gerada sem biblioteca extra, com as fontes padrão do PDF)
# ---------------------------------------------------------------------------
def _texto_pdf(texto):
    texto = texto.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return texto.encode("cp1252", errors="replace")


def gerar_pdf(linhas):
    """Monta um PDF de uma página. linhas = [(tamanho_da_fonte, texto), ...]."""
    conteudo = [b"BT", b"56 790 Td"]
    for tamanho, texto in linhas:
        conteudo.append(f"/F1 {tamanho} Tf".encode())
        conteudo.append(b"(" + _texto_pdf(texto) + b") Tj")
        conteudo.append(f"0 -{int(tamanho * 1.6)} Td".encode())
    conteudo.append(b"ET")
    fluxo = b"\n".join(conteudo)

    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Length " + str(len(fluxo)).encode() + b" >>\nstream\n" + fluxo + b"\nendstream",
    ]
    pdf = b"%PDF-1.4\n"
    posicoes = []
    for numero, objeto in enumerate(objetos, start=1):
        posicoes.append(len(pdf))
        pdf += f"{numero} 0 obj\n".encode() + objeto + b"\nendobj\n"
    inicio_xref = len(pdf)
    pdf += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    pdf += b"".join(f"{posicao:010d} 00000 n \n".encode() for posicao in posicoes)
    pdf += (f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\n"
            f"startxref\n{inicio_xref}\n%%EOF\n").encode()
    return pdf


def gerar_receita(consulta, paciente):
    linhas = [
        (18, "Receita médica"),
        (10, f"Atendimento {consulta['_id']}  ·  {consulta['data']}"),
        (10, ""),
        (12, f"Paciente: {paciente.get('nome', consulta['paciente_id'])} ({consulta['paciente_id']})"),
        (12, f"Profissional: {consulta['profissional_nome']} · {consulta['profissional_id']}"),
        (10, ""),
        (13, "Diagnósticos"),
    ]
    linhas += [(11, f"  {d['cid']}  {d['nome']}") for d in consulta["diagnosticos"]] or [(11, "  Nenhum")]
    linhas += [(10, ""), (13, "Prescrição")]
    linhas += [(11, f"  {m['nome']}: {m['posologia']}") for m in consulta["prescricao"]] \
        or [(11, "  Nenhum medicamento prescrito")]
    if consulta["anotacoes"]:
        linhas += [(10, ""), (13, "Anotações"), (11, f"  {consulta['anotacoes'][:110]}")]
    linhas += [(10, ""), (9, "Documento fictício gerado para a demonstração do projeto. Sem validade clínica.")]
    return gerar_pdf(linhas)


# ---------------------------------------------------------------------------
# Gravação nos três bancos
# ---------------------------------------------------------------------------
def finalizar(banco, driver, redis, consulta, paciente, token):
    hoje = consulta["data"]
    paciente_id = consulta["paciente_id"]
    agora = datetime.now(timezone.utc)

    # 1. MongoDB. Tudo com chave fixa ou filtro por atendimento_id, para repetir sem duplicar.
    banco.consultas.update_one(
        {"_id": consulta["_id"]}, {"$setOnInsert": {**consulta, "finalizada_em": agora}}, upsert=True
    )
    banco.laudos.update_one(
        {"_id": f"{consulta['_id']}-receita"},
        {"$setOnInsert": {
            "paciente_id": paciente_id,
            "nome": f"receita-{consulta['_id']}.pdf",
            "conteudo": gerar_receita(consulta, paciente),
            "registrado_em": agora,
        }},
        upsert=True,
    )
    if consulta["diagnosticos"]:
        banco.pacientes.update_one(
            {"paciente_id": paciente_id, "diagnosticos.atendimento_id": {"$ne": consulta["_id"]}},
            {"$push": {"diagnosticos": {"$each": [{
                "descricao": f"{d['cid']} · {d['nome']}",
                "registrado_em": agora,
                "atendimento_id": consulta["_id"],
            } for d in consulta["diagnosticos"]]}}},
        )
    banco.agendamentos.update_one(
        {"data": hoje, "paciente_id": paciente_id},
        {"$set": {"status": "realizado", "atendimento_id": consulta["_id"]}},
    )

    # 2. Neo4j
    registrar_atendimento(
        driver, paciente_id, paciente.get("nome", paciente_id), consulta["profissional_id"],
        consulta["_id"], hoje, [d["cid"] for d in consulta["diagnosticos"]],
        [{"codigo": m["codigo"], "posologia": m["posologia"], "em_uso": True}
         for m in consulta["prescricao"]],
    )

    # 3. Redis, por último: só encerra a sessão se ela ainda for a deste atendimento.
    sessao = chave_sessao(paciente_id)
    with redis.pipeline() as operacao:
        operacao.watch(sessao)
        if operacao.get(sessao) != token:
            return
        operacao.multi()
        operacao.delete(sessao)
        operacao.zadd(chave_atendidos(hoje), {paciente_id: int(time() * 1000)})
        operacao.expire(chave_atendidos(hoje), DOIS_DIAS)
        operacao.delete(chave_agenda(hoje))
        operacao.execute()


# ---------------------------------------------------------------------------
# Tela
# ---------------------------------------------------------------------------
def mostrar_finalizacao(cadastros, banco):
    url = os.getenv("REDIS_URL")
    uri = os.getenv("NEO4J_URI")
    usuario = os.getenv("NEO4J_USERNAME")
    senha = os.getenv("NEO4J_PASSWORD")
    if not url or not (uri and usuario and senha):
        st.info("Preencha REDIS_URL e as variáveis NEO4J_* no arquivo .env do projeto.")
        return

    resumo = st.session_state.pop("finalizacao_concluida", None)
    if resumo:
        st.success(f"Consulta de {resumo['nome']} finalizada nos três bancos.")
        st.download_button("Baixar receita em PDF", data=resumo["pdf"],
                           file_name=resumo["arquivo"], mime="application/pdf")

    hoje = date.today().isoformat()
    try:
        redis = conectar_redis(url)
        ativos = sessoes_ativas(redis)
        atendidos = redis.zrange(chave_atendidos(hoje), 0, -1)
    except (RedisError, ValueError):
        st.error("Não foi possível acessar o Redis. Confira a REDIS_URL e a conexão.")
        return

    principal, lado = st.columns([3, 2], gap="medium")
    with lado.container(border=True):
        st.subheader("Atendimentos de hoje")
        em_andamento, finalizados = st.columns(2)
        em_andamento.metric("Em andamento", len(ativos))
        finalizados.metric("Finalizados", len(atendidos))
        if atendidos:
            st.table([{"Paciente": cadastros.get(c, {}).get("nome", c)} for c in atendidos])

    with principal:
        if not ativos:
            st.info("Nenhum atendimento em andamento. Inicie um na Recepção Virtual.")
            return
        mostrar_formulario(cadastros, banco, redis, ativos, uri, usuario, senha, hoje)


def mostrar_formulario(cadastros, banco, redis, ativos, uri, usuario, senha, hoje):
    paciente_id = st.selectbox(
        "Paciente em atendimento",
        options=sorted(ativos),
        format_func=lambda codigo: f"{cadastros.get(codigo, {}).get('nome', codigo)} · {codigo}",
    )
    paciente = cadastros.get(paciente_id, {"paciente_id": paciente_id})
    token = ativos[paciente_id]
    atendimento_id = f"ATD-{hoje}-{paciente_id}-{token[:6]}"

    try:
        driver = conectar_neo4j(uri, usuario, senha)
        catalogo_diag = {d["cid"]: d["nome"] for d in consultar(driver, LISTAR_DIAGNOSTICOS)}
        catalogo_med = {m["codigo"]: m["nome"] for m in consultar(driver, LISTAR_MEDICAMENTOS)}
        # Só entra quem existe nos dois bancos: o registro no grafo depende do nó Medico.
        no_grafo = {m["profissional_id"] for m in consultar(driver, LISTAR_MEDICOS)}
        profissionais = {p["_id"]: p["nome"] for p in banco.profissionais.find().sort("_id", 1)
                         if p["_id"] in no_grafo}
    except (DriverError, Neo4jError, ValueError):
        st.error("Não foi possível acessar o Neo4j. Confira as variáveis NEO4J_* e a conexão.")
        return
    except PyMongoError:
        st.error("Não foi possível consultar os profissionais no MongoDB.")
        return
    if not profissionais:
        st.info("Nenhum profissional cadastrado nos dois bancos. "
                "Execute carregar_mongodb.py e carregar_neo4j.py.")
        return

    with st.container(border=True):
        st.caption(atendimento_id)
        opcoes = list(profissionais)
        escolhida = paciente.get("especialidade_escolhida")
        profissional_id = st.selectbox(
            "Profissional", options=opcoes,
            index=opcoes.index(escolhida) if escolhida in opcoes else 0,
            format_func=lambda codigo: f"{profissionais[codigo]} · {codigo}",
            key=f"fin_prof_{atendimento_id}",
        )
        anotacoes = st.text_area("Anotações da consulta", max_chars=500,
                                 key=f"fin_notas_{atendimento_id}")
        cids = st.multiselect(
            "Diagnósticos (CID-10)", options=list(catalogo_diag),
            format_func=lambda cid: f"{cid} · {catalogo_diag[cid]}",
            placeholder="Escolha um ou mais", key=f"fin_cids_{atendimento_id}",
        )
        codigos = st.multiselect(
            "Medicamentos prescritos", options=list(catalogo_med),
            format_func=lambda codigo: catalogo_med[codigo],
            placeholder="Escolha um ou mais", key=f"fin_meds_{atendimento_id}",
        )
        posologias = {
            codigo: st.text_input(f"Posologia de {catalogo_med[codigo]}", max_chars=120,
                                  key=f"fin_pos_{atendimento_id}_{codigo}")
            for codigo in codigos
        }

        try:
            alertas = [a for a in verificar_prescricao(driver, paciente_id, codigos) if a["nova"]]
        except (DriverError, Neo4jError):
            st.error("Não foi possível conferir a prescrição no Neo4j.")
            return
        if codigos and alertas:
            st.markdown("**Alertas do grafo clínico**")
            for alerta in alertas:
                mostrar_alerta(alerta)
        elif codigos:
            st.success("Nenhuma incompatibilidade cadastrada para essa prescrição.")

        graves = [a for a in alertas if a["gravidade"] == "grave"]
        ciente = True
        if graves:
            ciente = st.checkbox("Revisei os alertas graves e mantenho a prescrição",
                                 key=f"fin_ciente_{atendimento_id}")

        finalizar_clicado = st.button("Finalizar consulta", type="primary")

    if not finalizar_clicado:
        return
    faltando = [catalogo_med[c] for c, texto in posologias.items() if not texto.strip()]
    if faltando:
        st.warning(f"Preencha a posologia de: {', '.join(faltando)}.")
        return
    if not ciente:
        st.warning("Confirme a revisão dos alertas graves antes de finalizar.")
        return

    consulta = {
        "_id": atendimento_id,
        "paciente_id": paciente_id,
        "profissional_id": profissional_id,
        "profissional_nome": profissionais[profissional_id],
        "data": hoje,
        "anotacoes": anotacoes.strip(),
        "diagnosticos": [{"cid": c, "nome": catalogo_diag[c]} for c in cids],
        "prescricao": [{"codigo": c, "nome": catalogo_med[c], "posologia": posologias[c].strip()}
                       for c in codigos],
        "alertas_revisados": [{"tipo": a["tipo"], "gravidade": a["gravidade"],
                               "descricao": a["descricao"]} for a in alertas],
        "status": "finalizada",
    }
    try:
        finalizar(banco, driver, redis, consulta, paciente, token)
    except PyMongoError:
        st.error("Falha ao gravar no MongoDB. Nada foi encerrado. Tente finalizar de novo.")
        return
    except (DriverError, Neo4jError):
        st.error("A consulta foi salva no MongoDB, mas o Neo4j falhou. "
                 "Clique em Finalizar de novo: nada será duplicado.")
        return
    except RedisError:
        st.error("A consulta foi salva no MongoDB e no Neo4j, mas a sessão não foi encerrada "
                 "no Redis. Clique em Finalizar de novo.")
        return

    st.session_state["finalizacao_concluida"] = {
        "nome": paciente.get("nome", paciente_id),
        "pdf": banco.laudos.find_one({"_id": f"{atendimento_id}-receita"})["conteudo"],
        "arquivo": f"receita-{atendimento_id}.pdf",
    }
    st.rerun()
