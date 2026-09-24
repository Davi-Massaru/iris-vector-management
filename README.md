# Flask WSGI

Base mínima para uma nova especificação do projeto.

A única rota é `GET /`, que retorna `Hello, world!`. O servidor WSGI é o Waitress e o ponto de entrada é `wsgi:application`.

## Executar com Docker

```sh
cp .env.example .env
docker compose up -d --build
```

Abra http://localhost:8000.

O Ollama fica disponível em http://localhost:11434. Sua imagem, configuração de serviço e volume `argus-iris_ollama-models` foram preservados. A aplicação ainda não faz chamadas ao Ollama e não baixa modelos automaticamente.

O nome Compose `argus-iris` é mantido para reutilizar o volume existente. Não execute `docker compose down -v` se quiser preservar os modelos.

## Executar localmente

Com Python 3.12 instalado:

```sh
python -m venv .venv
```

Ative o ambiente (`.venv\Scripts\Activate.ps1` no PowerShell ou `source .venv/bin/activate` no Linux/macOS) e execute:

```sh
python -m pip install -r requirements.txt
waitress-serve --host=127.0.0.1 --port=8000 wsgi:application
```

Não há banco de dados, interface adicional, regras de negócio ou especificação herdada. A licença e o histórico Git foram mantidos.
