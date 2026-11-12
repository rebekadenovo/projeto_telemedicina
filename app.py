import os
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from grafo import mostrar_grafo
from interface import mostrar_cabecalho
from recepcao import mostrar_recepcao

st.set_page_config(page_title="Telemedicina", layout="wide")
st.sidebar.title("Telemedicina")
pagina = st.sidebar.radio("Área", ("Prontuário", "Recepção Virtual", "Grafo Clínico"))


descricoes = {
    "Prontuário": "Consulte o cadastro, o histórico de diagnósticos e os laudos do paciente.",
    "Recepção Virtual": "Organize a fila de espera e os agendamentos do dia.",
    "Grafo Clínico": "Explore diagnósticos relacionados e simule alertas de interação entre medicamentos.",
}
mostrar_cabecalho(pagina, descricoes[pagina])


@st.cache_resource
def conectar_mongodb(uri):
    return MongoClient(uri, serverSelectionTimeoutMS=5000)


load_dotenv(Path(__file__).resolve().with_name(".env"))
uri = os.getenv("MONGODB_URI")
if not uri:
    st.info("Preencha MONGODB_URI no arquivo .env do projeto.")
    st.stop()

try:
    colecao = conectar_mongodb(uri).telemedicina.pacientes
    pacientes = list(
        colecao.find(
            {"paciente_id": {"$exists": True}},
            {"_id": 0, "paciente_id": 1, "nome": 1, "data_nascimento": 1,
             "telefone": 1, "endereco": 1, "especialidade_escolhida": 1},
        ).sort("nome", 1)
    )
except (PyMongoError, ValueError):
    st.error("Não foi possível consultar o Atlas. Confira a conexão e a configuração do .env.")
    st.stop()

if not pacientes:
    st.info("Nenhum paciente encontrado. Execute carregar_mongodb.py.")
    st.stop()

cadastros = {paciente["paciente_id"]: paciente for paciente in pacientes}
if pagina == 'Recepção Virtual':
    mostrar_recepcao(cadastros, colecao.database.agendamentos)
    st.stop()
if pagina == "Grafo Clínico":
    mostrar_grafo(cadastros)
    st.stop()

paciente_id = st.selectbox(
    "Paciente",
    options=list(cadastros),
    format_func=lambda codigo: f"{cadastros[codigo].get('nome', codigo)} · {codigo}",
    index=None,
    placeholder="Selecione um paciente",
)

if paciente_id:
    paciente = cadastros[paciente_id]
    with st.container(border=True):
        st.caption(paciente_id)
        st.subheader(paciente.get("nome", paciente_id))
        nascimento, contato, especialidade = st.columns(3)
        with nascimento:
            st.caption("Nascimento")
            st.text(paciente.get("data_nascimento") or "Não informado")
        with contato:
            st.caption("Telefone")
            st.text(paciente.get("telefone") or "Não informado")
        with especialidade:
            st.caption("Especialidade")
            st.text(paciente.get("especialidade_escolhida") or "Não informada")

        endereco = paciente.get("endereco") or {}
        if isinstance(endereco, dict):
            endereco = ", ".join(
                str(endereco[campo])
                for campo in ("logradouro", "numero", "bairro", "cidade", "uf")
                if endereco.get(campo)
            )
        st.caption("Endereço")
        st.write(endereco or "Não informado")

    st.subheader("Diagnósticos")
    with st.form(f"diagnostico_{paciente_id}", clear_on_submit=True):
        descricao = st.text_input("Diagnóstico fictício", max_chars=200)
        salvar = st.form_submit_button("Registrar diagnóstico", type="primary")

    try:
        if salvar:
            if not descricao.strip():
                st.warning("Digite um diagnóstico para registrar.")
            else:
                resultado = colecao.update_one(
                    {"paciente_id": paciente_id},
                    {"$push": {"diagnosticos": {
                        "descricao": descricao.strip(),
                        "registrado_em": datetime.now(timezone.utc),
                    }}},
                )
                if resultado.matched_count:
                    st.success("Diagnóstico registrado.")
                else:
                    st.warning("Paciente não encontrado. Atualize a página.")

        prontuario = colecao.find_one(
            {"paciente_id": paciente_id}, {"_id": 0, "diagnosticos": 1}
        )
    except PyMongoError:
        st.error("Falha ao acessar o histórico no MongoDB. Confira a conexão.")
        st.stop()

    st.subheader("Histórico de diagnósticos")
    if st.session_state.pop(f"diagnostico_editado_{paciente_id}", False):
        st.success("Diagnóstico atualizado.")
    historico = (prontuario or {}).get("diagnosticos", [])
    if not historico:
        st.info("Nenhum diagnóstico registrado.")
    for indice in reversed(range(len(historico))):
        registro = historico[indice]
        st.text(registro["descricao"])
        with st.expander(f"Editar diagnóstico {indice + 1}"):
            with st.form(f"editar_{paciente_id}_{indice}"):
                nova_descricao = st.text_input(
                    "Descrição", value=registro["descricao"], max_chars=200
                )
                atualizar = st.form_submit_button("Salvar alteração")

            if atualizar:
                nova_descricao = nova_descricao.strip()
                if not nova_descricao:
                    st.warning("Digite uma descrição para salvar.")
                else:
                    campo = f"diagnosticos.{indice}.descricao"
                    try:
                        resultado = colecao.update_one(
                            {"paciente_id": paciente_id, campo: registro["descricao"]},
                            {"$set": {campo: nova_descricao}},
                        )
                    except PyMongoError:
                        st.error("Não foi possível salvar a alteração no MongoDB.")
                    else:
                        if resultado.matched_count:
                            st.session_state[f"diagnostico_editado_{paciente_id}"] = True
                            st.rerun()
                        else:
                            st.warning("O registro mudou. Atualize a página e tente novamente.")

    st.subheader("Laudos em PDF")
    laudos = colecao.database.laudos
    with st.form(f"laudo_{paciente_id}", clear_on_submit=True):
        arquivo = st.file_uploader("Selecione um laudo fictício (até 5 MB)", type=["pdf"])
        anexar = st.form_submit_button("Anexar laudo")

    try:
        if anexar:
            if arquivo is None:
                st.warning("Selecione um PDF para anexar.")
            elif arquivo.size > 5 * 1024 * 1024:
                st.warning("O PDF precisa ter até 5 MB.")
            elif not arquivo.getvalue().startswith(b"%PDF-"):
                st.warning("Selecione um arquivo PDF válido.")
            else:
                laudos.insert_one({
                    "paciente_id": paciente_id,
                    "nome": arquivo.name,
                    "conteudo": arquivo.getvalue(),
                    "registrado_em": datetime.now(timezone.utc),
                })
                st.success("Laudo anexado.")

        anexos = list(laudos.find(
            {"paciente_id": paciente_id}, {"nome": 1}
        ).sort("registrado_em", -1))
    except PyMongoError:
        st.error("Não foi possível acessar os laudos no MongoDB.")
        st.stop()

    if not anexos:
        st.info("Nenhum laudo anexado.")
    for anexo in anexos:
        st.text(anexo["nome"])
        if st.button("Preparar download", key=f"preparar_{anexo['_id']}"):
            try:
                laudo = laudos.find_one(
                    {"_id": anexo["_id"], "paciente_id": paciente_id},
                    {"conteudo": 1},
                )
            except PyMongoError:
                st.error("Não foi possível buscar o PDF.")
                continue
            if laudo is None:
                st.warning("Laudo não encontrado.")
            else:
                st.download_button(
                    "Baixar PDF",
                    data=laudo["conteudo"],
                    file_name=anexo["nome"],
                    mime="application/pdf",
                    key=f"baixar_{anexo['_id']}",
                )
