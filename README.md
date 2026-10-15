# Engenharia de IA Aplicada

**Série pública: um agente de IA construído do zero ao deploy, em Python.**

Nesta série você constrói, em público e aula por aula, o **Núcleo de Agentes
Operacionais**: um agente de IA de qualificação e atendimento de leads B2B.
Sem framework no começo, sem mágica: a lógica vem antes, e o framework entra
depois, quando você já entende o que ele resolve e a que preço.

As aulas são publicadas no LinkedIn do
[Prof. Thiago Azeredo Rodrigues](https://www.linkedin.com/in/thiago-azeredo-rodrigues),
**toda terça e quinta**. O programa completo está em
[`docs/Programa_Serie_Engenharia_IA_Aplicada.pdf`](docs/Programa_Serie_Engenharia_IA_Aplicada.pdf),
e a apostila de cada aula em [`docs/aulas/`](docs/aulas).

> **Fase 1 em andamento** (13/10 a 05/11): o agente vira grafo de estado, com
> persistência e human-in-the-loop. A **Fase 0 está completa** (tag `fase-0`).

---

## Rodando em dois minutos

```bash
git clone https://github.com/azrosolucoestecnologicas/engenharia-ia-aplicada.git
cd engenharia-ia-aplicada

python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env     # preencha com as suas chaves

python exemplos/qualificar_lead.py
```

A demo consulta o CRM, decide entre abrir ticket e agendar reunião, e imprime
a resposta, a árvore da execução, o custo em tokens e o contrato estruturado
final.

Para rodar os testes, que não usam rede nem gastam API:

```bash
pytest -v                 # a suíte rápida
pytest -m integration     # os testes que chamam a API de verdade
```

## Como este repositório funciona

Este não é um repositório de exemplos soltos. É **um sistema único que cresce
em camadas**: todo código de toda aula constrói ou evolui o mesmo projeto.

O estado do projeto em cada aula fica registrado numa **tag Git**. Para entrar
na série em qualquer ponto, com o projeto exatamente como ele estava naquela
aula:

```bash
git checkout aula-0.3     # o projeto como está ao fim da aula 0.3
```

A branch `main` sempre aponta para a aula mais recente publicada.

## Fase 0 · O agente em código puro *(completa)*

Oito aulas construindo o loop de agente na mão, antes de qualquer abstração.
Ao final, um agente de ação com três ferramentas reais, agnóstico de provider,
resiliente a falha e rastreado, sem uma linha de framework.

| Aula | Tema | Tag | Publicada |
|------|------|-----|-----------|
| 0.1 | Setup e a camada agnóstica de provider | `aula-0.1` | 15/09 |
| 0.2 | Tool use, o mecanismo cru | `aula-0.2` | 17/09 |
| 0.3 | O loop de agente | `aula-0.3` | 22/09 |
| 0.4 | Registro de ferramentas e schema portável | `aula-0.4` | 24/09 |
| 0.5 | As três ferramentas reais do domínio | `aula-0.5` | 29/09 |
| 0.6 | Saída estruturada e resiliência a erro | `aula-0.6` | 01/10 |
| 0.7 | Observabilidade desde o berço | `aula-0.7` | 06/10 |
| 0.8 | Consolidação: o primeiro tijolo do Núcleo | `aula-0.8` · `fase-0` | 08/10 |

## Fase 1 · Orquestração com estado *(em andamento)*

Do loop artesanal ao grafo de estado: persistência, human-in-the-loop e os
padrões de orquestração. A regra que organiza a fase: **comece pelo padrão
mais simples que resolve o problema, e só suba para autonomia quando ele
exigir.**

| Aula | Tema | Tag | Publicada |
|------|------|-----|-----------|
| 1.1 | Do laço ao grafo de estado | `aula-1.1` | 13/10 |
| 1.2 | Workflows I: prompt chaining e routing | `aula-1.2` | 15/10 |
| 1.3 | Workflows II: parallelization e orchestrator-workers | `aula-1.3` | 20/10 |
| 1.4 | Evaluator-optimizer: reflexão entre papéis | `aula-1.4` | 22/10 |
| 1.5 | Padrões autônomos: ReAct contra plan-and-execute | `aula-1.5` | 27/10 |
| 1.6 | Estado durável e checkpointing | `aula-1.6` | 29/10 |
| 1.7 | Human-in-the-loop | `aula-1.7` | 03/11 |
| 1.8 | Consolidação: escolher o padrão certo | `aula-1.8` · `fase-1` | 05/11 |

## Arquitetura

```
nucleo/
├── __init__.py          a API pública do pacote
│
│   # Fase 0 — o motor, agnóstico de framework
├── config.py            nomes de modelo, lidos do .env        (0.1)
├── providers.py         a camada agnóstica de provider        (0.1, 0.3, 0.7)
├── agente.py            o laço: decisão, ação, observação      (0.3, 0.7)
├── registro.py          o decorator que gera os schemas        (0.4, 0.5)
├── banco.py             o CRM mockado em SQLite                (0.5)
├── ferramentas.py       as três ferramentas do domínio         (0.5)
├── modelos.py           os contratos Pydantic                  (0.6)
├── resiliencia.py       erro de ferramenta como observação     (0.6)
├── estruturado.py       a saída final validada                 (0.6)
├── observabilidade.py   trace, span e generation               (0.7)
│
│   # Fase 1 — a orquestração, sobre o motor acima
├── grafo.py             o laço como grafo de estado            (1.1)
├── fluxos.py            chaining e routing em Python puro      (1.2)
└── grafo_fluxos.py      os mesmos padrões como grafo           (1.2)
```

Repare na divisão: a Fase 1 **acrescenta** orquestração sem alterar uma linha
do motor da Fase 0. Se adotar um framework exigisse reescrever o motor, o
motor estaria acoplado ao laço desde o começo.

Duas fronteiras organizam o projeto, e as duas importam mais do que a
organização em si:

**Motor e domínio são separados.** Importar `nucleo` não registra as
ferramentas do FlowDesk; quem quer o domínio pede por ele explicitamente
(`from nucleo import ferramentas`). É isso que torna o Núcleo replicável: outro
cliente pluga a própria base e as próprias integrações sem herdar as nossas. Há
um teste que falha se alguém quebrar essa separação.

**Regra de negócio mora no prompt, capacidade mora na ferramenta.** A
ferramenta não decide *quando* abrir um ticket: ela sabe abrir. Quem decide é o
agente, orientado pela instrução de sistema. Trocar a política comercial é
trocar um texto, não editar Python.

## O que é portável e o que vira framework

Esta é a pergunta que a Fase 0 existe para responder, e saber apontar essa
fronteira é o que separa quem usa framework de quem escolhe framework.

**Conhecimento que você leva para qualquer stack:** o ciclo de quatro etapas do
tool use (você declara, o modelo pede, você executa, você devolve); a ideia de
que o agente é o laço, não o modelo; as condições de parada; a separação entre
definição e execução de ferramenta; descrição de ferramenta é prompt; erro como
observação; o vocabulário de trace, span e generation.

**O que a Fase 1 substitui por framework:** o `while` artesanal vira
`StateGraph`; a lista de mensagens vira estado explícito; a persistência, que
na Fase 0 não existia, vira *checkpointer*; e a interrupção humana, que era só
um comentário no código, vira primitivo.

Note o que **não** está na segunda lista. O registro de ferramentas, o domínio,
a resiliência e a observabilidade atravessaram a fronteira intactos. Não é
acaso: foi o motivo de construí-los desacoplados.

## O que o sistema ainda não faz

Um README honesto sobre os limites vale mais, para quem avalia, do que um que
promete demais. Hoje o Núcleo **não** tem persistência de estado em banco (o
processo cai, a conversa se perde), não tem aprovação humana antes de ação
sensível, não tem RAG, não é multi-agente e não está no ar.

As duas primeiras lacunas fecham ainda nesta fase, nas aulas 1.6 e 1.7. As
outras três são, nesta ordem, as Fases 2 a 4.

## Requisitos

- Python 3.11 ou superior
- Chaves de API da Anthropic e da OpenAI (a série é agnóstica de provider e
  mostra os dois lado a lado)
- Opcional: credenciais do Langfuse. Sem elas, o tracing local continua
  funcionando e nada quebra.

Nenhum segredo é versionado neste repositório.

## O mapa completo da série

- **Fase 0.** O agente em código puro, sem framework *(completa)*
- **Fase 1.** Orquestração com LangGraph: estado durável e human-in-the-loop *(em andamento)*
- **Fase 2.** Multi-agente, MCP e interoperabilidade
- **Trilho R.** RAG em produção, do fundamento ao estado da arte
- **Fase 3.** Avaliação e observabilidade nível produção
- **Fase 4.** Deploy real: FastAPI, Docker, Kubernetes e canais
- **Fase 5.** A blindagem do sênior: segurança, fine-tuning como decisão

## Licença

[MIT](LICENSE). Use, estude, adapte. Se este material te ajudar, uma estrela no
repositório ajuda a série a chegar em mais gente.

---

**Prof. Thiago Azeredo Rodrigues** · Engenheiro de IA · Instituto NTA
[LinkedIn](https://www.linkedin.com/in/thiago-azeredo-rodrigues)
