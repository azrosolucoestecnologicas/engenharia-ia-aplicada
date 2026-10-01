"""Aula 0.6 - A resposta final como contrato, nao como texto livre.

Texto livre e otimo para humanos e pessimo para sistemas. Quando o
Nucleo estiver atras de uma API na Fase 4, alimentando um CRM real,
alguem vai precisar de {"status": "qualificado", "pontuacao": 85}, nao
de um paragrafo simpatico.

DECISAO DE PROJETO, e ela e deliberada:

Os dois providers tem mecanismos NATIVOS de saida estruturada, com
nomes, garantias e assinaturas diferentes, e que mudam com frequencia.
Em vez de amarrar o Nucleo a eles, implementamos o padrao portavel:
pedir o JSON pelo prompt, validar com Pydantic e, se falhar, devolver
o erro de validacao ao modelo para ele corrigir.

O que isso nos da: funciona igual nos dois providers, usa a chat() da
aula 0.1 sem nenhuma mudanca, e e testavel sem rede. O que custa: uma
chamada a mais quando o modelo erra o formato. Quando voce for para
producao com um provider so, vale conferir o mecanismo nativo dele na
documentacao e trocar ESTE arquivo. O resto do Nucleo nao muda.
"""

import json

from pydantic import ValidationError

from nucleo.providers import chat


def _instrucao(modelo_pydantic):
    """Monta a instrucao de sistema a partir do proprio contrato.

    O JSON Schema sai do Pydantic: o contrato continua sendo fonte
    unica da verdade, como o registro da aula 0.4.
    """
    esquema = json.dumps(modelo_pydantic.model_json_schema(),
                         ensure_ascii=False, indent=2)
    return (
        "Responda APENAS com um objeto JSON valido que satisfaca o "
        "schema abaixo. Sem markdown, sem crase, sem texto antes ou "
        "depois.\n\n" + esquema
    )


def _limpar(texto):
    """Remove cercas de markdown que o modelo as vezes insiste em por."""
    t = texto.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t.strip()


def extrair_estruturado(texto_bruto, modelo_pydantic, provider="anthropic",
                        tentativas=2):
    """Converte a resposta final do agente num objeto validado.

    texto_bruto -> a resposta em linguagem natural do agente
    modelo_pydantic -> a classe do contrato (ex.: QualificacaoLead)

    Se a validacao falhar, o ERRO volta para o modelo como instrucao de
    correcao. E o mesmo principio da resiliencia de ferramenta: falha
    vira informacao, nao excecao.
    """
    mensagens = [{
        "role": "user",
        "content": ("Extraia os dados estruturados do relato abaixo.\n\n"
                    + texto_bruto),
    }]

    ultimo_erro = None

    for _ in range(tentativas):
        resposta = chat(provider, mensagens,
                        system=_instrucao(modelo_pydantic))
        bruto = _limpar(resposta)

        try:
            return modelo_pydantic.model_validate_json(bruto)

        except ValidationError as e:
            ultimo_erro = e
            # Devolve ao modelo o que ele produziu e o que esta errado.
            mensagens.append({"role": "assistant", "content": bruto})
            mensagens.append({
                "role": "user",
                "content": ("O JSON acima nao passou na validacao:\n"
                            f"{e}\n\nCorrija e responda apenas com o "
                            "JSON valido."),
            })

        except (json.JSONDecodeError, ValueError) as e:
            ultimo_erro = e
            mensagens.append({"role": "assistant", "content": bruto})
            mensagens.append({
                "role": "user",
                "content": (f"Isso nao e JSON valido ({e}). Responda "
                            "apenas com o objeto JSON, sem markdown."),
            })

    # Esgotou as tentativas: AQUI levantamos, porque quem chamou pediu
    # um contrato e nao recebeu. Devolver um objeto meia-boca seria
    # pior do que falhar.
    raise ValueError(
        f"Nao foi possivel extrair {modelo_pydantic.__name__} em "
        f"{tentativas} tentativas. Ultimo erro: {ultimo_erro}"
    )
