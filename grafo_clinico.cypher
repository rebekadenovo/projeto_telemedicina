// Carga do grafo clínico fictício (Neo4j)
// Pode ser executada pelo script carregar_neo4j.py ou colada no Neo4j Browser/AuraDB.
// Todos os comandos usam MERGE, então a carga pode ser repetida sem duplicar dados.
// Atenção: não use ponto e vírgula dentro de textos, porque o script separa os comandos por ele.

// ---------------------------------------------------------------------------
// 1. Restrições de unicidade (cada uma também cria um índice)
// ---------------------------------------------------------------------------
CREATE CONSTRAINT paciente_id IF NOT EXISTS FOR (p:Paciente) REQUIRE p.paciente_id IS UNIQUE;
CREATE CONSTRAINT prontuario_id IF NOT EXISTS FOR (pr:Prontuario) REQUIRE pr.prontuario_id IS UNIQUE;
CREATE CONSTRAINT profissional_id IF NOT EXISTS FOR (m:Medico) REQUIRE m.profissional_id IS UNIQUE;
CREATE CONSTRAINT diagnostico_cid IF NOT EXISTS FOR (d:Diagnostico) REQUIRE d.cid IS UNIQUE;
CREATE CONSTRAINT medicamento_codigo IF NOT EXISTS FOR (md:Medicamento) REQUIRE md.codigo IS UNIQUE;

// ---------------------------------------------------------------------------
// 2. Profissionais (mesmos da coleção profissionais do MongoDB)
//    profissional_id = _id do documento no MongoDB
// ---------------------------------------------------------------------------
UNWIND [
  {id: "Clínico geral",    nome: "Laura Teixeira"},
  {id: "Ginecologista",    nome: "Marina Farias"},
  {id: "Ortopedista",      nome: "André Seixas"},
  {id: "Endocrinologista", nome: "Renata Monteiro"}
] AS m
MERGE (medico:Medico {profissional_id: m.id})
SET medico.nome = m.nome, medico.especialidade = m.id;

// ---------------------------------------------------------------------------
// 3. Pacientes e prontuários (mesmos paciente_id do MongoDB)
//    O grafo guarda só o identificador e o nome. O cadastro completo fica no MongoDB.
// ---------------------------------------------------------------------------
UNWIND [
  {id: "PAC001", nome: "Helena Duarte Lima"},
  {id: "PAC002", nome: "Antônio Vieira Ramos"},
  {id: "PAC003", nome: "Camila Moura Alves"},
  {id: "PAC004", nome: "Rafael Nunes Costa"},
  {id: "PAC005", nome: "Beatriz Martins Rocha"},
  {id: "PAC006", nome: "Lucas Barreto Freire"},
  {id: "PAC007", nome: "Juliana Melo Cardoso"},
  {id: "PAC008", nome: "Marcos Pinto Azevedo"},
  {id: "PAC009", nome: "Larissa Gomes Brito"},
  {id: "PAC010", nome: "Diego Campos Ribeiro"}
] AS p
MERGE (paciente:Paciente {paciente_id: p.id})
SET paciente.nome = p.nome
MERGE (pr:Prontuario {prontuario_id: "PRT-" + p.id})
MERGE (paciente)-[:POSSUI]->(pr);

// ---------------------------------------------------------------------------
// 4. Diagnósticos (códigos CID-10 reais, nomes resumidos)
// ---------------------------------------------------------------------------
UNWIND [
  {cid: "I10", nome: "Hipertensão arterial"},
  {cid: "I48", nome: "Fibrilação atrial"},
  {cid: "I63", nome: "AVC isquêmico"},
  {cid: "I25", nome: "Doença coronariana crônica"},
  {cid: "E78", nome: "Dislipidemia"},
  {cid: "E11", nome: "Diabetes tipo 2"},
  {cid: "E66", nome: "Obesidade"},
  {cid: "N18", nome: "Doença renal crônica"},
  {cid: "E03", nome: "Hipotireoidismo"},
  {cid: "F32", nome: "Depressão"},
  {cid: "F41", nome: "Transtorno de ansiedade"},
  {cid: "J45", nome: "Asma"},
  {cid: "K21", nome: "Refluxo gastroesofágico"},
  {cid: "K25", nome: "Úlcera gástrica"},
  {cid: "M54", nome: "Dor nas costas"},
  {cid: "M17", nome: "Artrose de joelho"},
  {cid: "G43", nome: "Enxaqueca"},
  {cid: "N39", nome: "Infecção urinária"},
  {cid: "N94", nome: "Cólica menstrual"}
] AS d
MERGE (diag:Diagnostico {cid: d.cid})
SET diag.nome = d.nome;

// ---------------------------------------------------------------------------
// 5. Medicamentos
// ---------------------------------------------------------------------------
UNWIND [
  {codigo: "LOSARTANA",        nome: "Losartana 50 mg",              classe: "Anti-hipertensivo"},
  {codigo: "ENALAPRIL",        nome: "Enalapril 10 mg",              classe: "Anti-hipertensivo"},
  {codigo: "HIDROCLOROTIAZIDA",nome: "Hidroclorotiazida 25 mg",      classe: "Diurético"},
  {codigo: "ESPIRONOLACTONA",  nome: "Espironolactona 25 mg",        classe: "Diurético poupador de potássio"},
  {codigo: "VARFARINA",        nome: "Varfarina 5 mg",               classe: "Anticoagulante"},
  {codigo: "AAS",              nome: "AAS 100 mg",                   classe: "Antiagregante"},
  {codigo: "CLOPIDOGREL",      nome: "Clopidogrel 75 mg",            classe: "Antiagregante"},
  {codigo: "SINVASTATINA",     nome: "Sinvastatina 20 mg",           classe: "Estatina"},
  {codigo: "METFORMINA",       nome: "Metformina 850 mg",            classe: "Antidiabético"},
  {codigo: "LEVOTIROXINA",     nome: "Levotiroxina 50 mcg",          classe: "Hormônio tireoidiano"},
  {codigo: "CARBONATO_CALCIO", nome: "Carbonato de cálcio 500 mg",   classe: "Suplemento"},
  {codigo: "FLUOXETINA",       nome: "Fluoxetina 20 mg",             classe: "Antidepressivo"},
  {codigo: "AMITRIPTILINA",    nome: "Amitriptilina 25 mg",          classe: "Antidepressivo"},
  {codigo: "TRAMADOL",         nome: "Tramadol 50 mg",               classe: "Analgésico opioide"},
  {codigo: "IBUPROFENO",       nome: "Ibuprofeno 600 mg",            classe: "Anti-inflamatório"},
  {codigo: "NIMESULIDA",       nome: "Nimesulida 100 mg",            classe: "Anti-inflamatório"},
  {codigo: "PREDNISONA",       nome: "Prednisona 20 mg",             classe: "Corticoide"},
  {codigo: "PARACETAMOL",      nome: "Paracetamol 750 mg",           classe: "Analgésico"},
  {codigo: "DIPIRONA",         nome: "Dipirona 500 mg",              classe: "Analgésico"},
  {codigo: "OMEPRAZOL",        nome: "Omeprazol 20 mg",              classe: "Protetor gástrico"},
  {codigo: "CLARITROMICINA",   nome: "Claritromicina 500 mg",        classe: "Antibiótico"},
  {codigo: "CIPROFLOXACINO",   nome: "Ciprofloxacino 500 mg",        classe: "Antibiótico"},
  {codigo: "RIFAMPICINA",      nome: "Rifampicina 300 mg",           classe: "Antibiótico"},
  {codigo: "ANTICONCEPCIONAL", nome: "Anticoncepcional oral combinado", classe: "Hormonal"},
  {codigo: "SALBUTAMOL",       nome: "Salbutamol spray",             classe: "Broncodilatador"},
  {codigo: "PROPRANOLOL",      nome: "Propranolol 40 mg",            classe: "Betabloqueador"}
] AS m
MERGE (med:Medicamento {codigo: m.codigo})
SET med.nome = m.nome, med.classe = m.classe;

// ---------------------------------------------------------------------------
// 6. Interações medicamentosas SIMULADAS (exemplos didáticos, não usar como referência clínica)
//    A relação é simétrica: gravamos uma direção e consultamos sem seta.
// ---------------------------------------------------------------------------
UNWIND [
  {a: "VARFARINA",    b: "AAS",              gravidade: "grave",    motivo: "aumenta muito o risco de sangramento"},
  {a: "VARFARINA",    b: "IBUPROFENO",       gravidade: "grave",    motivo: "risco de sangramento gastrointestinal"},
  {a: "VARFARINA",    b: "NIMESULIDA",       gravidade: "grave",    motivo: "risco de sangramento"},
  {a: "SINVASTATINA", b: "CLARITROMICINA",   gravidade: "grave",    motivo: "risco de lesão muscular grave"},
  {a: "FLUOXETINA",   b: "TRAMADOL",         gravidade: "grave",    motivo: "risco de síndrome serotoninérgica"},
  {a: "AMITRIPTILINA",b: "TRAMADOL",         gravidade: "grave",    motivo: "risco de convulsão e síndrome serotoninérgica"},
  {a: "ENALAPRIL",    b: "ESPIRONOLACTONA",  gravidade: "moderada", motivo: "risco de potássio alto no sangue"},
  {a: "LOSARTANA",    b: "ESPIRONOLACTONA",  gravidade: "moderada", motivo: "risco de potássio alto no sangue"},
  {a: "LOSARTANA",    b: "IBUPROFENO",       gravidade: "moderada", motivo: "reduz o efeito do anti-hipertensivo"},
  {a: "ENALAPRIL",    b: "IBUPROFENO",       gravidade: "moderada", motivo: "reduz o efeito do anti-hipertensivo"},
  {a: "PREDNISONA",   b: "IBUPROFENO",       gravidade: "moderada", motivo: "aumenta o risco de úlcera"},
  {a: "CLOPIDOGREL",  b: "OMEPRAZOL",        gravidade: "moderada", motivo: "pode reduzir o efeito do clopidogrel"},
  {a: "RIFAMPICINA",  b: "ANTICONCEPCIONAL", gravidade: "moderada", motivo: "reduz a eficácia do anticoncepcional"},
  {a: "AAS",          b: "IBUPROFENO",       gravidade: "moderada", motivo: "reduz o efeito antiagregante do AAS"},
  {a: "LEVOTIROXINA", b: "CARBONATO_CALCIO", gravidade: "leve",     motivo: "reduz a absorção, tomar com 4 horas de intervalo"}
] AS i
MATCH (a:Medicamento {codigo: i.a}), (b:Medicamento {codigo: i.b})
MERGE (a)-[r:INTERAGE_COM]-(b)
SET r.gravidade = i.gravidade, r.motivo = i.motivo;

// ---------------------------------------------------------------------------
// 7. Contraindicações SIMULADAS (medicamento x diagnóstico)
// ---------------------------------------------------------------------------
UNWIND [
  {codigo: "PROPRANOLOL", cid: "J45", motivo: "pode causar broncoespasmo em pessoas com asma"},
  {codigo: "IBUPROFENO",  cid: "N18", motivo: "pode piorar a função dos rins"},
  {codigo: "IBUPROFENO",  cid: "K25", motivo: "agrava a úlcera"},
  {codigo: "NIMESULIDA",  cid: "K25", motivo: "agrava a úlcera"},
  {codigo: "AAS",         cid: "K25", motivo: "agrava a úlcera e o risco de sangramento"},
  {codigo: "METFORMINA",  cid: "N18", motivo: "risco de acidose lática com rins comprometidos"},
  {codigo: "PREDNISONA",  cid: "K25", motivo: "pode agravar a úlcera"}
] AS c
MATCH (med:Medicamento {codigo: c.codigo}), (d:Diagnostico {cid: c.cid})
MERGE (med)-[r:CONTRAINDICADO_EM]->(d)
SET r.motivo = c.motivo;

// ---------------------------------------------------------------------------
// 8. Diagnósticos correlacionados (fator de risco, complicação, comorbidade)
// ---------------------------------------------------------------------------
UNWIND [
  {a: "E66", b: "E11", tipo: "fator de risco"},
  {a: "E66", b: "I10", tipo: "fator de risco"},
  {a: "E11", b: "I10", tipo: "comorbidade frequente"},
  {a: "E11", b: "N18", tipo: "complicação"},
  {a: "I10", b: "N18", tipo: "complicação"},
  {a: "I10", b: "I25", tipo: "fator de risco"},
  {a: "E78", b: "I25", tipo: "fator de risco"},
  {a: "I10", b: "I63", tipo: "fator de risco"},
  {a: "I48", b: "I63", tipo: "complicação"},
  {a: "F32", b: "F41", tipo: "comorbidade frequente"},
  {a: "K21", b: "J45", tipo: "associação"},
  {a: "E03", b: "E78", tipo: "associação"},
  {a: "M54", b: "M17", tipo: "associação"},
  {a: "G43", b: "F41", tipo: "associação"}
] AS c
MATCH (a:Diagnostico {cid: c.a}), (b:Diagnostico {cid: c.b})
MERGE (a)-[r:CORRELACIONADO_COM]-(b)
SET r.tipo = c.tipo;

// ---------------------------------------------------------------------------
// 9. Histórico fictício de atendimentos
//    Cada item vira: Medico-ATENDEU->Paciente, Medico-REGISTRA->Prontuario,
//    Prontuario-CONTEM_DIAGNOSTICO->Diagnostico e Prontuario-REGISTRA_MEDICAMENTO->Medicamento.
//    em_uso = true para uso contínuo. Só esses entram nos alertas.
// ---------------------------------------------------------------------------
UNWIND [
  {atd: "HIST-001", pac: "PAC001", med: "Clínico geral",    data: "2026-05-10", cids: ["I10"],
   meds: [{codigo: "LOSARTANA", posologia: "1 comprimido pela manhã", em_uso: true}]},
  {atd: "HIST-002", pac: "PAC001", med: "Clínico geral",    data: "2026-08-22", cids: ["I48"],
   meds: [{codigo: "VARFARINA", posologia: "1 comprimido à noite", em_uso: true}]},
  {atd: "HIST-003", pac: "PAC002", med: "Endocrinologista", data: "2026-06-03", cids: ["E11", "I10"],
   meds: [{codigo: "METFORMINA", posologia: "1 comprimido 2 vezes ao dia", em_uso: true},
          {codigo: "ENALAPRIL",  posologia: "1 comprimido 2 vezes ao dia", em_uso: true}]},
  {atd: "HIST-004", pac: "PAC003", med: "Ginecologista",    data: "2026-07-15", cids: ["N94"],
   meds: [{codigo: "ANTICONCEPCIONAL", posologia: "1 comprimido ao dia", em_uso: true}]},
  {atd: "HIST-005", pac: "PAC004", med: "Clínico geral",    data: "2026-04-28", cids: ["F32"],
   meds: [{codigo: "FLUOXETINA", posologia: "1 cápsula pela manhã", em_uso: true}]},
  {atd: "HIST-006", pac: "PAC005", med: "Clínico geral",    data: "2026-09-02", cids: ["J45"],
   meds: [{codigo: "SALBUTAMOL", posologia: "2 jatos se falta de ar", em_uso: true}]},
  {atd: "HIST-007", pac: "PAC006", med: "Ortopedista",      data: "2026-10-05", cids: ["M54"],
   meds: [{codigo: "IBUPROFENO", posologia: "1 comprimido de 8 em 8 horas por 5 dias", em_uso: false}]},
  {atd: "HIST-008", pac: "PAC007", med: "Endocrinologista", data: "2026-03-19", cids: ["E03"],
   meds: [{codigo: "LEVOTIROXINA", posologia: "1 comprimido em jejum", em_uso: true}]},
  {atd: "HIST-009", pac: "PAC008", med: "Clínico geral",    data: "2026-02-11", cids: ["I25", "E78"],
   meds: [{codigo: "SINVASTATINA", posologia: "1 comprimido à noite", em_uso: true},
          {codigo: "AAS",          posologia: "1 comprimido após o almoço", em_uso: true},
          {codigo: "CLOPIDOGREL",  posologia: "1 comprimido ao dia", em_uso: true}]},
  {atd: "HIST-010", pac: "PAC008", med: "Clínico geral",    data: "2026-09-30", cids: ["K21"],
   meds: [{codigo: "OMEPRAZOL", posologia: "1 cápsula em jejum", em_uso: true}]},
  {atd: "HIST-011", pac: "PAC009", med: "Ginecologista",    data: "2026-08-08", cids: ["N39"],
   meds: [{codigo: "CIPROFLOXACINO", posologia: "1 comprimido de 12 em 12 horas por 3 dias", em_uso: false}]},
  {atd: "HIST-012", pac: "PAC009", med: "Clínico geral",    data: "2026-10-20", cids: ["G43"],
   meds: [{codigo: "AMITRIPTILINA", posologia: "1 comprimido à noite", em_uso: true}]},
  {atd: "HIST-013", pac: "PAC010", med: "Clínico geral",    data: "2026-07-01", cids: ["E66", "I10"],
   meds: [{codigo: "HIDROCLOROTIAZIDA", posologia: "1 comprimido pela manhã", em_uso: true}]}
] AS h
MATCH (m:Medico {profissional_id: h.med})
MATCH (p:Paciente {paciente_id: h.pac})-[:POSSUI]->(pr:Prontuario)
MERGE (m)-[a:ATENDEU]->(p)
  ON CREATE SET a.total = 0, a.atendimentos = []
FOREACH (_ IN CASE WHEN h.atd IN a.atendimentos THEN [] ELSE [1] END |
  SET a.total = a.total + 1, a.atendimentos = a.atendimentos + h.atd)
SET a.ultima_vez = h.data
MERGE (m)-[reg:REGISTRA {atendimento_id: h.atd}]->(pr)
SET reg.data = h.data
FOREACH (cid IN h.cids |
  MERGE (d:Diagnostico {cid: cid})
  MERGE (pr)-[cd:CONTEM_DIAGNOSTICO {atendimento_id: h.atd}]->(d)
  SET cd.data = h.data)
FOREACH (item IN h.meds |
  MERGE (md:Medicamento {codigo: item.codigo})
  MERGE (pr)-[rm:REGISTRA_MEDICAMENTO {atendimento_id: h.atd}]->(md)
  SET rm.data = h.data, rm.posologia = item.posologia, rm.em_uso = item.em_uso);
