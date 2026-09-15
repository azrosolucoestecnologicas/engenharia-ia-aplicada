import os

# setdefault so define se a variavel ainda nao existe: nao
# sobrescreve um valor real que voce ja tenha no ambiente.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("ANTHROPIC_MODEL", "claude-sonnet-5")
os.environ.setdefault("OPENAI_MODEL", "gpt-5.1")
