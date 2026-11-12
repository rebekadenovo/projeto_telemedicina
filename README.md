# Plataforma de Telemedicina

Projeto final da disciplina **Implementação de Bancos de Dados NoSQL**. A aplicação em Python e Streamlit simula a recepção virtual e a gestão de prontuários com dados fictícios.

## Funcionalidades

| Módulo | O que já funciona |
| --- | --- |
| Recepção virtual | Fila por ordem de chegada, com prioridade para os dois idosos da demonstração. O início do atendimento retira o primeiro paciente da fila e cria uma sessão de uma hora. |
| Agenda do dia | Um agendamento por paciente e um por horário na agenda compartilhada. Os horários aceitam intervalos de 30 minutos. |
| Prontuário | Consulta ao cadastro, registro e edição de diagnósticos e envio e download de laudos em PDF de até 5 MB. |
| Grafo clínico | Mapa do paciente no Neo4j, diagnósticos relacionados em até 3 passos, histórico de medicamentos, simulação de prescrição com alertas de interação e contraindicação e lista de pacientes em risco. |

A finalização da consulta está prevista para a próxima etapa.

## Arquitetura

| Banco | Papel na aplicação |
| --- | --- |
| MongoDB Atlas | Armazena pacientes, profissionais, especialidades, diagnósticos, laudos e agendamentos. |
| Redis Cloud | Ordena a fila com um Sorted Set, mantém tokens de sessão e guarda a agenda do dia em cache por cinco minutos. |
| Neo4j AuraDB | Relaciona pacientes, prontuários, profissionais, diagnósticos e medicamentos e gera alertas com consultas Cypher. Guarda só identificadores e nomes, e o cadastro completo continua no MongoDB. |

## Executar no Windows

Clone o repositório e abra a pasta no PowerShell com Python 3.12 instalado.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Preencha `MONGODB_URI` com a string de conexão do MongoDB Atlas, `REDIS_URL` com a URL do Redis Cloud e `NEO4J_URI`, `NEO4J_USERNAME` e `NEO4J_PASSWORD` com os dados da instância do AuraDB. `NEO4J_DATABASE` é opcional. Use dados fictícios e mantenha as credenciais no arquivo local `.env`.

```powershell
.\.venv\Scripts\python.exe carregar_mongodb.py
.\.venv\Scripts\python.exe carregar_neo4j.py
.\.venv\Scripts\python.exe -m streamlit run app.py
```

No macOS ou no Linux, use `source .venv/bin/activate` e rode `python carregar_neo4j.py` e os demais comandos sem o caminho `.\.venv\Scripts\`.

A carga do Neo4j executa [grafo_clinico.cypher](grafo_clinico.cypher) e mostra no final quantos nós e relações existem. Ela usa `MERGE` e pode ser repetida sem duplicar dados. O arquivo também pode ser colado no Neo4j Browser.

A carga do MongoDB cria o índice único de `paciente_id` e insere os cadastros que faltam a partir de [pacientes.json](pacientes.json), além de profissionais e especialidades fictícios. Abra a **Local URL** exibida no terminal. Para encerrar, pressione **Ctrl + C**.

## Demonstração

1. Em **Recepção Virtual**, adicione Rafael (`PAC004`) e depois Helena (`PAC001`). Confira a prioridade da Helena e tente adicioná-la novamente para ver o bloqueio de duplicatas.
2. Clique em **Iniciar próximo atendimento**. A primeira pessoa sai da fila, e a sessão ativa impede que ela volte à espera.
3. Na **Agenda do dia**, agende um horário livre como **14:30**. Tente repetir o horário com outro paciente e marcar um segundo horário para o primeiro. A tela deve bloquear as duas tentativas. Clique em **Atualizar fila** para ver a consulta da agenda pelo cache do Redis.
4. Em **Prontuário**, selecione Helena, registre e edite um diagnóstico fictício. Anexe um PDF de teste e baixe o arquivo para conferir.
5. Em **Grafo Clínico**, sem selecionar paciente, veja Marcos (`PAC008`) na lista de risco: ele usa clopidogrel e omeprazol.
6. Selecione Helena (`PAC001`), que usa varfarina e losartana. Em **Simular prescrição**, escolha **Ibuprofeno**: aparecem um alerta grave e um moderado, e o remédio entra tracejado no mapa. Troque por **Paracetamol** e os alertas somem.
7. Confira os casos prontos: Rafael (`PAC004`) com **Tramadol**, Beatriz (`PAC005`, asma) com **Propranolol**, Antônio (`PAC002`) com **Espironolactona** e Camila (`PAC003`) com **Rifampicina**.
8. Abra **Diagnósticos relacionados** em Antônio ou Diego (`PAC010`) para ver as cadeias de até 3 passos, e a aba **Consultas Cypher** para mostrar o código. Use **Pesquisar por → Profissional** para ver os pacientes de cada médica.

## Modelo do grafo

| Relação | Propriedades | Significado |
| --- | --- | --- |
| `(Paciente)-[:POSSUI]->(Prontuario)` | — | Prontuário do paciente, com id `PRT-` + `paciente_id`. |
| `(Medico)-[:ATENDEU]->(Paciente)` | `total`, `ultima_vez`, `atendimentos` | Vínculo único entre profissional e paciente, com contador. |
| `(Medico)-[:REGISTRA]->(Prontuario)` | `atendimento_id`, `data` | Uma por consulta. |
| `(Prontuario)-[:CONTEM_DIAGNOSTICO]->(Diagnostico)` | `atendimento_id`, `data` | Diagnóstico com código CID-10. |
| `(Prontuario)-[:REGISTRA_MEDICAMENTO]->(Medicamento)` | `atendimento_id`, `data`, `posologia`, `em_uso` | Só remédios com `em_uso = true` entram nos alertas. |
| `(Medicamento)-[:INTERAGE_COM]-(Medicamento)` | `gravidade`, `motivo` | Interação simulada, consultada sem direção. |
| `(Medicamento)-[:CONTRAINDICADO_EM]->(Diagnostico)` | `motivo` | Contraindicação simulada. |
| `(Diagnostico)-[:CORRELACIONADO_COM]-(Diagnostico)` | `tipo` | Fator de risco, complicação ou comorbidade. |

`Medico.profissional_id` é o mesmo `_id` da coleção `profissionais` do MongoDB, como `Clínico geral`. As interações e contraindicações são exemplos didáticos e não servem como referência clínica.

Para a finalização da consulta, `grafo.py` oferece `verificar_prescricao(driver, paciente_id, codigos)`, que devolve os alertas, e `registrar_atendimento(...)`, que grava a consulta no grafo numa única transação. Repetir a gravação com o mesmo `atendimento_id` não duplica nada.

## Contribuir

Crie uma branch para sua tarefa e abra um pull request para `main`. Use `paciente_id` como referência entre os bancos. As quatro frentes são recepção, prontuário, grafo clínico e finalização da consulta.
