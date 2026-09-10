# Engenharia de IA Aplicada

**Série pública: um agente de IA construído do zero ao deploy, em Python.**

Nesta série você constrói, em público e aula por aula, o **Núcleo de Agentes
Operacionais**: um agente de IA de qualificação e atendimento de leads B2B. Sem framework no começo, sem mágica: a
lógica vem antes, e o framework entra depois, quando você já entende o que ele
resolve e a que preço.

As aulas são publicadas no LinkedIn do
[Prof. Thiago Azeredo Rodrigues](https://www.linkedin.com/in/thiago-azeredo-rodrigues),
duas por semana durante a temporada. O programa completo da série está em
[`docs/Programa_Serie_Engenharia_IA_Aplicada.pdf`](docs/Programa_Serie_Engenharia_IA_Aplicada.pdf).

> **Status: a Aula 0.1 chega em 15/09/2026.** Dê watch no repositório para ser
> avisado.

---

## Como este repositório funciona

Este não é um repositório de exemplos soltos. É **um sistema único que cresce
em camadas**: todo código de toda aula constrói ou evolui o mesmo projeto.

O estado do projeto em cada aula fica registrado numa **tag Git**. Para entrar
na série em qualquer ponto, com o projeto exatamente como ele estava naquela
aula:

```bash
git clone https://github.com/thiagoazro/engenharia-ia-aplicada.git
cd engenharia-ia-aplicada
git checkout aula-0.3   # o projeto como está ao fim da aula 0.3
```

A branch `main` sempre aponta para a aula mais recente publicada.

## A temporada atual: Fase 0, o agente sem framework

Oito aulas construindo o loop de agente na mão, antes de qualquer abstração.
Ao final, um agente de ação com três ferramentas reais, agnóstico de provider,
resiliente a falha e rastreado com observabilidade.

| Aula | Tema | Tag | Status |
|------|------|-----|--------|
| 0.1 | Setup e a camada agnóstica de provider | `aula-0.1` | 15/09 |
| 0.2 | Tool use, o mecanismo cru | `aula-0.2` | em breve |
| 0.3 | O loop de agente | `aula-0.3` | em breve |
| 0.4 | Registro de ferramentas e schema portável | `aula-0.4` | em breve |
| 0.5 | As três ferramentas reais do domínio | `aula-0.5` | em breve |
| 0.6 | Saída estruturada e resiliência a erro | `aula-0.6` | em breve |
| 0.7 | Observabilidade desde o berço | `aula-0.7` | em breve |
| 0.8 | Consolidação: o primeiro tijolo do Núcleo | `fase-0` | em breve |

## O mapa completo da série

A Fase 0 é a primeira temporada. O programa inteiro, detalhado no
[PDF](docs/Programa_Serie_Engenharia_IA_Aplicada.pdf):

- **Fase 0.** O agente em código puro, sem framework
- **Fase 1.** Orquestração estruturada com LangGraph: estado durável e human-in-the-loop
- **Fase 2.** Multi-agente, MCP e interoperabilidade, com um MCP server próprio
- **Trilho R.** RAG em produção, do fundamento ao estado da arte
- **Fase 3.** Avaliação e observabilidade nível produção
- **Fase 4.** Deploy real: FastAPI, Docker, Kubernetes e canais como WhatsApp e Slack
- **Fase 5.** A blindagem do sênior: segurança, fine-tuning como decisão e red teaming

## Para quem é

Desenvolvedores Python de nível intermediário migrando para engenharia de IA
aplicada. Você não precisa saber nada sobre agentes. Precisa saber ler uma
stack trace, usar Git e não se assustar com um teste que quebra.

O que a série **não** é: não ensina a treinar modelos, não deduz matemática de
rede neural e não é uma introdução à programação.

## Requisitos

- Python 3.11 ou superior
- Chaves de API da Anthropic e da OpenAI (a série é agnóstica de provider e
  mostra os dois lado a lado)
- Git

As instruções de setup completas chegam com a Aula 0.1, e o arquivo
`.env.example` documentará as variáveis necessárias. Nenhum segredo é
versionado neste repositório.

## Os compromissos da série

1. **Código real, nunca pseudocódigo.** Todo bloco publicado roda, e este
   repositório é a prova.
2. **Agnóstico de fornecedor.** Tudo funciona com Claude e com GPT; onde os
   dois divergem, os dois aparecem lado a lado.
3. **Falhar alto, nunca em silêncio.** Sistema de agente que engole erro
   produz resposta plausível em cima de dado ruim, e esse é o bug mais caro da
   área.
4. **Medir, não achar.** Da Fase 3 em diante, toda escolha de padrão, modelo e
   prompt se defende com número.

## Licença

[MIT](LICENSE). Use, estude, adapte. Se este material te ajudar, uma estrela
no repositório ajuda a série a chegar em mais gente.

---

**Prof. Thiago Azeredo Rodrigues** · Engenheiro de IA · Instituto NTA
[LinkedIn](https://www.linkedin.com/in/thiago-azeredo-rodrigues)
