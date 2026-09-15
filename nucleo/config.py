import os

from dotenv import load_dotenv

# load_dotenv le o arquivo .env e joga as variaveis pro ambiente.
load_dotenv()

# os.getenv(nome, padrao): pega a variavel; se faltar, usa o padrao.
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.1")

# Sem padrao aqui de proposito: se faltar a chave, paramos com um
# erro claro, em vez de quebrar la na frente sem explicacao.
if not os.getenv("ANTHROPIC_API_KEY"):
    raise RuntimeError("Falta ANTHROPIC_API_KEY no .env")
if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError("Falta OPENAI_API_KEY no .env")
